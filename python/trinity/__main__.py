"""Command line client, run as `python -m trinity` or `trinity-remote`.

First run, asks the server operator for access:
    trinity-remote --server tcp://myserver:5558 --name goggles --grants "robot-1/*:rw"

Later runs log in with the saved token:
    trinity-remote --subscribe robot-1/video robot-1/depth robot-1/imu --cmd '{"cmd":"status"}' --show
"""

import argparse
import time

from .client import DEFAULT_SERVER, RelayError, RemoteController
from .depth import np


def print_stats(rc, entity):
    line = "  ".join(f"{e}/{c} {hz:.1f} Hz {size / 1024:.0f} kB"
                     for (e, c), (hz, size) in sorted(rc.stats().items()))
    print(line or "no data")
    d = rc.latest(entity, "depth")
    if d is not None and np is not None and isinstance(d.data, np.ndarray):
        valid = d.data[d.data > 0]
        median = int(np.median(valid)) if valid.size else 0
        print(f"  depth {d.data.shape[1]}x{d.data.shape[0]} "
              f"valid {100 * valid.size / d.data.size:.0f}% median {median} mm")


def show(rc, entity):
    """Draw color and depth windows. Returns False when the user closes them."""
    import cv2
    v = rc.latest(entity, "video")
    if v is not None and not isinstance(v.data, bytes):
        cv2.imshow("video", v.data)
    d = rc.latest(entity, "depth")
    if d is not None and np is not None and isinstance(d.data, np.ndarray):
        scaled = np.clip(d.data / 4000 * 255, 0, 255).astype(np.uint8)
        colored = cv2.applyColorMap(scaled, cv2.COLORMAP_JET)
        colored[d.data == 0] = 0
        cv2.imshow("depth", colored)
    return cv2.waitKey(30) & 0xFF not in (ord("q"), 27)


def main():
    ap = argparse.ArgumentParser(prog="trinity-remote", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=DEFAULT_SERVER, help="relay address (or TRINITY_SERVER)")
    ap.add_argument("--name", default="trinity", help="name shown to the operator")
    ap.add_argument("--grants", nargs="+", default=["robot-1/*:rw"], help="permissions to ask for")
    ap.add_argument("--token-file", default="trinity.token")
    ap.add_argument("--subscribe", nargs="+", default=["robot-1/video", "robot-1/depth", "robot-1/imu"])
    ap.add_argument("--cmd", action="append", default=[], help="JSON command to send, can repeat")
    ap.add_argument("--entity", default="robot-1", help="target of --cmd and --show")
    ap.add_argument("--show", action="store_true", help="OpenCV windows for color and depth, q or Esc quits")
    args = ap.parse_args()

    rc = RemoteController(args.server, args.token_file, decode_video=args.show).start()
    try:
        rc.login(args.name, args.grants)
        print(f"logged in as {rc.consumer_id}, grants: {' '.join(rc.grants)}")
        print(f"streams: {' '.join(rc.subscribe(*args.subscribe))}")
        for cmd in args.cmd:
            try:
                print(f"-> {cmd}\n<- {rc.command(args.entity, cmd)}")
            except (RelayError, TimeoutError) as err:
                print(f"-> {cmd}\n<- error: {err}")

        last_print = 0.0
        while True:
            if time.time() - last_print >= 2:
                last_print = time.time()
                print_stats(rc, args.entity)
            if args.show:
                if not show(rc, args.entity):
                    break
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        rc.close()


if __name__ == "__main__":
    main()
