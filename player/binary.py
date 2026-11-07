"""Small C-semantics and PCM helpers used by the sample codecs."""

from __future__ import annotations

import array
import struct
import sys


def wrap16(value: int) -> int:
    """Wrap ``value`` into the signed 16-bit range.

    Args:
        value: Any integer.

    Returns:
        The value as a C ``short`` would hold it.
    """
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def s16(buf: bytes | bytearray, offset: int) -> int:
    """Read a little-endian signed 16-bit word.

    Args:
        buf: Buffer holding the word.
        offset: Byte offset of the word.

    Returns:
        The signed value.
    """
    return struct.unpack_from("<h", buf, offset)[0]


def put16(buf: bytearray, offset: int, value: int) -> None:
    """Write a little-endian 16-bit word, masking the value.

    Args:
        buf: Mutable destination buffer.
        offset: Byte offset of the word.
        value: Value to store.
    """
    struct.pack_into("<H", buf, offset, value & 0xFFFF)


def clamp16(value: int) -> int:
    """Clamp ``value`` to the signed 16-bit range.

    Args:
        value: Any integer.

    Returns:
        ``value`` limited to -32768..32767.
    """
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return value


def pcm_bytes(samples: array.array) -> bytes:
    """Serialise int16 samples as little-endian bytes.

    Args:
        samples: An ``array('h')`` of native-order samples.

    Returns:
        The samples in little-endian byte order, whatever the host order.
    """
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()
