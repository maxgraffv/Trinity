"""Read depth and IMU from the robot and send it one command.

    python examples/basic.py                        # uses examples/config.json
    python examples/basic.py --config config.json

Set "server" in the config first. On the first run the operator has to
approve the access request on the server.
"""

import argparse
import os
import time

from trinity import RemoteController

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    args = ap.parse_args()

    with RemoteController.from_config(args.config) as rc:
        rc.login()
        robot = rc.config["entity"]
        print("subscribed to", rc.subscribe(*rc.config["subscribe"]))
        print("status:", rc.command(robot, {"cmd": "status"}))

        for _ in range(10):
            time.sleep(1)
            depth = rc.latest(robot, "depth")
            imu = rc.latest(robot, "imu")
            if depth is not None:
                h, w = depth.data.shape
                print(f"distance at image center: {depth.data[h // 2, w // 2]} mm")
            if imu is not None:
                print("imu:", imu.data.get("head", {}).get("rpy_deg"))


if __name__ == "__main__":
    main()
