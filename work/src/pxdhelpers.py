"""Small C-semantics helpers shared by pxd32d5."""

import struct


def _idiv(a: int, b: int) -> int:
    """C integer division (truncates toward zero, unlike //)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _s16(buf, off: int) -> int:
    return struct.unpack_from("<h", buf, off)[0]


def _put16(buf, off: int, value: int) -> None:
    """``*(_WORD *)p = value`` - silent wrap-around to 16 bits."""
    struct.pack_into("<H", buf, off, value & 0xFFFF)


def _put32(buf, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value & 0xFFFFFFFF)


def _u16(buf, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _u32(buf, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _s32(value: int) -> int:
    """Interpret a 32-bit value as signed (C ``signed int``)."""
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value
