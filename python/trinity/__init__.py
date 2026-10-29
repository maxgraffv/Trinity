"""Trinity controller library: talks to the relay server, receives robot streams
(color, depth, IMU, ...) and sends commands."""

from .client import DEFAULT_SERVER, Frame, RelayError, RemoteController
from .config import load_config
from .depth import D435_DEPTH, decode_depth, depth_to_points

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_SERVER",
    "D435_DEPTH",
    "Frame",
    "RelayError",
    "RemoteController",
    "decode_depth",
    "depth_to_points",
    "load_config",
]
