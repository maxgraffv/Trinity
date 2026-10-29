"""Settings from config.json.

config.example.json in the repository lists every key. Copy it to config.json
and fill in your values, config.json itself is not tracked by git.

Precedence, highest first: explicit arguments, the TRINITY_SERVER environment
variable (server only), config.json, built-in defaults.
"""

import json
import os

DEFAULTS = {
    "server": "tcp://127.0.0.1:5558",
    "name": "trinity",
    "grants": ["robot-1/*:rw"],
    "token_file": "trinity.token",
    "subscribe": ["robot-1/video", "robot-1/depth", "robot-1/imu"],
    "entity": "robot-1",
}

DEFAULT_PATH = "config.json"


def load_config(path=DEFAULT_PATH):
    """Return the merged settings. A missing file at the default path is fine,
    a missing file that was asked for explicitly is an error."""
    config = dict(DEFAULTS)
    if path is not None:
        if os.path.exists(path):
            with open(path) as f:
                loaded = json.load(f)
            unknown = set(loaded) - set(DEFAULTS)
            if unknown:
                raise ValueError(f"{path}: unknown keys {', '.join(sorted(unknown))}")
            config.update(loaded)
        elif path != DEFAULT_PATH:
            raise FileNotFoundError(path)
    if os.environ.get("TRINITY_SERVER"):
        config["server"] = os.environ["TRINITY_SERVER"]
    return config
