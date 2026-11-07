"""The 256-entry DPCM delta ladder used by the ``tPxd`` codec."""

from __future__ import annotations


def build_delta_table() -> list[int]:
    """Build the codec's symmetric, roughly logarithmic step ladder.

    This reproduces ``sub_10011EFF``'s ``dword_1008E350`` table: an
    exponentially growing increment is accumulated and mirrored around index
    128, then each value is doubled and stored as a signed 16-bit word.

    Returns:
        A list of 256 signed delta values.
    """
    v1, v20 = 2.2, 1.0565
    table = [0] * 257
    for j in range(1, 128):
        if j >= 6:
            table[j + 128] = int(v1 - 0.52) + table[j + 127]
        else:
            table[j + 128] = table[j + 127] + 1
        v1 *= v20
        v20 -= 0.00022
    for k in range(1, 129):
        table[128 - k] = -table[k + 128]

    out = []
    for m in range(256):
        value = (table[m] * 2) & 0xFFFF
        out.append(value - 0x10000 if value & 0x8000 else value)
    return out


DELTA_TABLE = build_delta_table()
