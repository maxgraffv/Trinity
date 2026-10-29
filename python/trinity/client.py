"""Controller side of the relay: login, stream subscriptions and commands.

The relay server (ROUTER socket, port 5558 by default) checks what each
controller is allowed to see and forwards only the streams it subscribed to.
"""

import collections
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import zmq

from .depth import decode_depth, np

DEFAULT_SERVER = os.environ.get("TRINITY_SERVER", "tcp://127.0.0.1:5558")


@dataclass
class Frame:
    data: Any  # JPEG bytes or BGR image for video, uint16 array for depth, dict for JSON
    size: int  # message size in bytes
    received: float  # local receive time, time.time()
    stamp: float | None = None  # robot clock in seconds, if the message carries one


class RelayError(RuntimeError):
    """The server refused: missing permission, rejected request, undelivered command."""


class RemoteController:
    """Client for the relay.

    ZeroMQ sockets are not thread safe, so a single I/O thread owns the DEALER
    socket. Public methods can be called from any thread.
    """

    def __init__(self, server=DEFAULT_SERVER, token_file="trinity.token", decode_video=False):
        self.server = server
        self.token_file = token_file
        self.decode_video = decode_video
        self.consumer_id = None
        self.grants = []
        self.streams = []
        self._ctx = zmq.Context.instance()
        self._outbox = queue.Queue()
        self._wake_addr = f"inproc://trinity-{id(self)}"
        self._wake_lock = threading.Lock()
        self._latest = {}
        self._rates = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()
        self._pending = collections.defaultdict(collections.deque)  # entity -> commands awaiting a reply
        self._control = queue.Queue()  # replies to auth/request/subscribe
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    def start(self):
        wake_in = self._ctx.socket(zmq.PULL)
        wake_in.bind(self._wake_addr)
        self._wake = self._ctx.socket(zmq.PUSH)
        self._wake.connect(self._wake_addr)
        self._thread = threading.Thread(target=self._loop, args=(wake_in,), name="trinity-io", daemon=True)
        self._thread.start()
        return self

    def close(self):
        if self._thread is None:
            return
        self._send([b"bye"])
        time.sleep(0.1)
        self._stop.set()
        self._thread.join(timeout=2)
        self._wake.close()
        self._thread = None

    def _send(self, parts):
        self._outbox.put([p if isinstance(p, bytes) else str(p).encode() for p in parts])
        with self._wake_lock:
            self._wake.send(b"")

    def _loop(self, wake_in):
        sock = self._ctx.socket(zmq.DEALER)
        sock.setsockopt(zmq.LINGER, 100)
        sock.connect(self.server)
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        poller.register(wake_in, zmq.POLLIN)
        while not self._stop.is_set():
            events = dict(poller.poll(200))
            if wake_in in events:
                while wake_in.poll(0):
                    wake_in.recv()
                while not self._outbox.empty():
                    sock.send_multipart(self._outbox.get())
            if sock in events:
                while sock.poll(0):
                    self._on_message(sock.recv_multipart())
        sock.close()
        wake_in.close()

    def _on_message(self, parts):
        verb = parts[0].decode(errors="replace")
        if verb == "data" and len(parts) >= 4:
            self._on_data(parts[1].decode(), parts[2].decode(), parts[3])
        elif verb == "reply" and len(parts) >= 3:
            self._resolve(parts[1].decode(), result=parts[2])
        elif verb == "command" and len(parts) >= 3:
            # "ok" only means delivered, the robot's answer comes later as "reply".
            if parts[2] == b"error":
                self._resolve(parts[1].decode(), error=b" ".join(parts[3:]).decode(errors="replace"))
        else:
            self._control.put([p.decode(errors="replace") for p in parts])

    def _on_data(self, entity, channel, payload):
        now = time.time()
        stamp = None
        data = payload
        try:
            if channel == "depth":
                data, stamp = decode_depth(payload)
            elif channel == "video" and self.decode_video:
                import cv2
                data = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
            elif payload[:1] in (b"{", b"["):
                data = json.loads(payload)
                stamp = data.get("stamp") if isinstance(data, dict) else None
        except Exception:
            data = payload  # keep the raw bytes if decoding fails
        with self._lock:
            self._latest[(entity, channel)] = Frame(data, len(payload), now, stamp)
            times = self._rates[(entity, channel)]
            times.append(now)
            while times and now - times[0] > 2.0:
                times.popleft()

    def _resolve(self, entity, result=None, error=None):
        with self._lock:
            waiting = self._pending[entity]
            slot = waiting.popleft() if waiting else None
        if slot is None:
            return
        if error is not None:
            slot.put(RelayError(error))
        else:
            try:
                slot.put(json.loads(result))
            except ValueError:
                slot.put(result.decode(errors="replace"))

    def _expect(self, verbs, timeout):
        deadline = time.time() + timeout
        while (left := deadline - time.time()) > 0:
            try:
                msg = self._control.get(timeout=left)
            except queue.Empty:
                break
            if msg[0] in verbs:
                return msg
            if msg[0] == "error":
                raise RelayError(" ".join(msg[1:]))
        raise TimeoutError(f"no {'/'.join(sorted(verbs))} from {self.server}")

    def login(self, name="trinity", grants=("*/*:r",), timeout=None):
        """Log in with the saved token, or ask the server operator for access.

        A new request waits until the operator approves it (timeout=None waits
        forever). The token is then saved to token_file with mode 600.
        """
        if os.path.exists(self.token_file):
            with open(self.token_file) as f:
                token = f.read().strip()
            self._send([b"auth", token])
            msg = self._expect({"ok", "denied"}, 10)
            if msg[0] == "ok":
                self.consumer_id, self.grants = msg[1], msg[2:]
                return self
            print(f"token in {self.token_file} was rejected ({' '.join(msg[1:])}), requesting access again")

        self._send([b"request", name, *grants])
        msg = self._expect({"pending"}, 10)
        print(f"waiting for the operator to approve request {msg[1]}")
        msg = self._expect({"granted", "rejected"}, timeout if timeout is not None else 10**9)
        if msg[0] == "rejected":
            raise RelayError("the operator rejected the request")
        self.consumer_id, token, self.grants = msg[1], msg[2], msg[3:]
        with open(self.token_file, "w") as f:
            f.write(token + "\n")
        os.chmod(self.token_file, 0o600)
        return self

    def subscribe(self, *topics):
        """Subscribe to "entity/channel" streams, "*" matches anything.

        Data only arrives for streams that are both subscribed and granted.
        Returns the full list of subscriptions.
        """
        self._send([b"subscribe", *topics])
        self.streams = self._expect({"subscribed"}, 10)[1:]
        return self.streams

    def unsubscribe(self, *topics):
        """Drop the given streams, or all of them when called without arguments."""
        self._send([b"unsubscribe", *topics])
        self.streams = self._expect({"subscribed"}, 10)[1:]
        return self.streams

    def command(self, entity, cmd, timeout=5.0):
        """Send a command (dict or str) and return the robot's reply.

        Needs an rw grant for the entity. Raises RelayError when the command is
        refused or not delivered, TimeoutError when the robot does not answer.
        """
        slot = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[entity].append(slot)
        payload = cmd if isinstance(cmd, (str, bytes)) else json.dumps(cmd)
        self._send([b"command", entity, payload])
        try:
            result = slot.get(timeout=timeout)
        except queue.Empty:
            with self._lock:
                if slot in self._pending[entity]:
                    self._pending[entity].remove(slot)
            raise TimeoutError(f"{entity} did not answer {payload}")
        if isinstance(result, Exception):
            raise result
        return result

    def latest(self, entity, channel):
        """Most recent Frame of a stream, or None. Older messages are not kept."""
        with self._lock:
            return self._latest.get((entity, channel))

    def stats(self):
        """Map (entity, channel) to (rate in Hz over the last 2 s, last message size)."""
        now = time.time()
        with self._lock:
            return {k: (sum(1 for t in v if now - t <= 2.0) / 2.0, self._latest[k].size)
                    for k, v in self._rates.items() if k in self._latest}
