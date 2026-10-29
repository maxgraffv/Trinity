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

## Usage

```python
from trinity import RemoteController, depth_to_points

with RemoteController("tcp://myserver:5558", token_file="goggles.token") as rc:
    rc.login(name="goggles", grants=["robot-1/*:rw"])
    rc.subscribe("robot-1/video", "robot-1/depth", "robot-1/imu")

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

Data only arrives for streams that are both subscribed and granted by the
operator. `latest()` keeps just the newest message per stream.

`command()` needs an `rw` grant for the entity. It raises `RelayError` if the
command is refused and `TimeoutError` if the robot does not answer.

## Command line

```sh
python -m trinity --server tcp://myserver:5558 --name goggles --grants "robot-1/*:rw"
python -m trinity --subscribe robot-1/video robot-1/depth --cmd '{"cmd":"status"}' --show
```

After installing, the same tool is available as `trinity-remote`. The default
server can be set with `TRINITY_SERVER`.
