"""Standalone decoder for the proprietary ``tPxd`` DPCM/code-book stream."""

from __future__ import annotations

import array
import struct

from ..binary import put16, s16, wrap16
from .delta_table import DELTA_TABLE
from .sample_error import SampleError

BOOK_SIZE = 8100
"""Code-book size allocated by ``sub_1001186B`` (``malloc(0x1FA4)``)."""

BOOK_SILENCE = (0, 0, 0, 0, 0, -1)
"""Entry 0 written by ``sub_10011EFF``: five zero deltas and a stop word."""


class PxdDecoder:
    """Decode a ``tPxd`` stream to mono int16 at its declared length."""

    def length(self, data: bytes) -> int:
        """Return the frame count the ``tPxd`` header declares.

        Args:
            data: ``tPxd`` record, or at least its header.

        Returns:
            Declared frames; zero when the header declares none.

        Raises:
            SampleError: The header is truncated.
        """
        frames, _ = self._header(data)
        return frames if frames > 0 else 0

    def decode(self, data: bytes) -> array.array:
        """Decode one ``tPxd`` stream.

        Args:
            data: Whole ``tPxd`` record, header included.

        Returns:
            Exactly the number of frames the header declares.  A bytecode
            that ends early is padded with silence, mirroring
            ``RWavToTemp``'s truncation to the declared length.

        Raises:
            SampleError: The header is truncated.
        """
        frames, offset = self._header(data)
        out = array.array("h")
        if frames <= 0:
            return out

        book = bytearray(BOOK_SIZE)
        struct.pack_into("<6h", book, 0, *BOOK_SILENCE)
        table = DELTA_TABLE
        end = len(data)
        pos = offset
        acc = 0

        while pos < end and len(out) < frames:
            code = data[pos]
            if code >= 0xF4:
                if code == 0xFF:
                    if pos + 2 > end:
                        break
                    acc = wrap16(acc + table[data[pos + 1]])
                    pos += 2
                    out.append(acc)
                    continue
                if pos + 2 > end:
                    break
                index = data[pos + 1]
                count = code - 0xF3
                pos += 2
                if pos + count > end:
                    break
                base = 16 * index
                for k in range(count):
                    put16(book, base + 2 * k, table[data[pos + k]])
                put16(book, base + 2 * count, 0xFFFF)
                pos += count
                entry = base
            else:
                pos += 1
                entry = 16 * code

            while len(out) < frames:
                delta = s16(book, entry)
                if delta == -1:
                    break
                acc = wrap16(acc + delta)
                out.append(acc)
                entry += 2

        if len(out) < frames:
            out.extend(array.array("h", bytes(2 * (frames - len(out)))))
        return out

    @staticmethod
    def _header(data: bytes) -> tuple[int, int]:
        """Return ``(frames, bytecode offset)`` from a ``tPxd`` header.

        Raises:
            SampleError: The header is truncated.
        """
        if len(data) < 8:
            raise SampleError("tPxd header is truncated")
        comment = data[4]
        offset = 4 + comment + 8
        if comment + 10 > len(data) or offset > len(data):
            raise SampleError("tPxd header is truncated")
        frames = struct.unpack_from("<i", data, comment + 6)[0]
        return frames, offset
