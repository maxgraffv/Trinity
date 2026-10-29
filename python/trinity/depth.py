"""Depth frames: the SDZ1 wire format and conversion to 3D points."""

import struct

try:
    import numpy as np
    import zstandard
except ImportError:  # depth stays as raw SDZ1 bytes without them
    np = zstandard = None

# "SDZ1", uint16 width, uint16 height, uint64 robot timestamp in ns, little endian.
# A single zstd frame with uint16 millimetres follows, row by row.
SDZ1_HEADER = struct.Struct("<4sHHQ")

# Intel RealSense D435, left IR camera at 640x480, no distortion.
D435_DEPTH = {"fx": 384.637, "fy": 384.637, "ppx": 321.812, "ppy": 241.691}


def has_depth_support():
    return np is not None and zstandard is not None


def decode_depth(payload):
    """Return (depth, stamp) from an SDZ1 message.

    depth is a HxW uint16 array in millimetres, 0 means no data. stamp is the
    robot clock in seconds. Without numpy/zstandard the raw payload is returned
    instead of the array.
    """
    magic, w, h, stamp_ns = SDZ1_HEADER.unpack_from(payload)
    if magic != b"SDZ1":
        raise ValueError("not an SDZ1 frame")
    if not has_depth_support():
        return payload, stamp_ns / 1e9
    raw = zstandard.ZstdDecompressor().decompress(payload[SDZ1_HEADER.size:], max_output_size=w * h * 2)
    return np.frombuffer(raw, np.uint16).reshape(h, w), stamp_ns / 1e9


def depth_to_points(depth_mm, fx=D435_DEPTH["fx"], fy=D435_DEPTH["fy"],
                    ppx=D435_DEPTH["ppx"], ppy=D435_DEPTH["ppy"]):
    """Deproject a depth image to an Nx3 array of points in metres.

    Pixels without data are skipped. Camera frame: x right, y down, z forward.
    """
    v, u = np.nonzero(depth_mm)
    z = depth_mm[v, u].astype(np.float32) / 1000.0
    return np.stack([(u - ppx) * z / fx, (v - ppy) * z / fy, z], axis=1)
