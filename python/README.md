# trinity (Python)

Controller library. It connects to the relay server, receives robot streams
(color, depth, IMU, ...) and sends commands to the robot.

```
controller (trinity)  --DEALER-->  relay server :5558  <--PUB/DEALER--  robot
```

## Install

```sh
pip install -e "python[depth]"
```

`pyzmq` is the only hard dependency. The `depth` extra adds numpy and zstandard
for decoding depth frames, `show` adds OpenCV for the preview windows.

## Configuration

Copy the example and fill in your server address and the rest:

```sh
cp config.example.json config.json
```

```json
{
  "server": "tcp://myserver:5558",
  "name": "my-controller",
  "grants": ["robot-1/*:rw"],
  "token_file": "trinity.token",
  "subscribe": ["robot-1/video", "robot-1/depth", "robot-1/imu"],
  "entity": "robot-1"
}
```

`config.json` is ignored by git, so local addresses never end up in the
repository. Command line options override it, and `TRINITY_SERVER` overrides
the server address.

## Usage

```python
from trinity import RemoteController, depth_to_points

with RemoteController.from_config("config.json") as rc:
    rc.login()  # name and grants from the config
    rc.subscribe(*rc.config["subscribe"])

    depth = rc.latest("robot-1", "depth")  # uint16 array in mm, 0 = no data
    color = rc.latest("robot-1", "video")  # JPEG bytes, or BGR with decode_video=True
    imu = rc.latest("robot-1", "imu")      # dict
    if depth is not None:
        points = depth_to_points(depth.data)

    print(rc.command("robot-1", {"cmd": "head", "yaw": 20}))
```

The first `login()` sends an access request and blocks until the server
operator approves it. The token is saved to `token_file` (mode 600) and used on
later runs. Keep token files out of git, `*.token` is already ignored.

Without a config file, pass the values directly:
`RemoteController("tcp://myserver:5558", token_file="goggles.token")` and
`rc.login(name="goggles", grants=["robot-1/*:rw"])`.

Data only arrives for streams that are both subscribed and granted by the
operator. `latest()` keeps just the newest message per stream.

`command()` needs an `rw` grant for the entity. It raises `RelayError` if the
command is refused and `TimeoutError` if the robot does not answer.

## Examples

`examples/basic.py` reads depth and IMU and sends a `status` command, using
`examples/config.json`. Set the server address there before running it:

```sh
python examples/basic.py
```

`examples/config.json` is tracked by git as a sample, so do not put your real
server address in it. Use your own `config.json` and `--config config.json`.

## Command line

```sh
python -m trinity                     # everything from config.json
python -m trinity --cmd '{"cmd":"status"}' --show
python -m trinity --config other.json --subscribe robot-1/imu
```

After installing, the same tool is available as `trinity-remote`. The default
server can be set with `TRINITY_SERVER`.
