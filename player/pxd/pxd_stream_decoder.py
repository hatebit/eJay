"""Incremental decoder for the proprietary ``tPxd`` DPCM/code-book stream."""

from __future__ import annotations

import array

from ..binary import wrap16
from .delta_table import DELTA_TABLE
from .sample_error import SampleError
from .stream_source import StreamSource

BOOK_SIZE = 8100
"""Code-book size allocated by ``sub_1001186B`` (``malloc(0x1FA4)``)."""

BOOK_WORDS = BOOK_SIZE // 2
"""Code-book size in 16-bit words."""

BOOK_SILENCE = (0, 0, 0, 0, 0, -1)
"""Entry 0 written by ``sub_10011EFF``: five zero deltas and a stop word."""

WORDS_PER_ENTRY = 8
"""Code-book entries are 16 bytes apart, i.e. eight 16-bit words."""


class PxdStreamDecoder:
    """Decode a ``tPxd`` stream block by block from an open source.

    The DPCM integrator and code book persist across :meth:`read` calls, so
    the decoder produces exactly the same frames as
    :class:`~player.pxd.pxd_decoder.PxdDecoder` while never holding more
    than one block of output.

    The code book is an ``array('h')`` of words, so reading and writing it is
    independent of the host byte order, and the bytecode is indexed straight
    out of :attr:`StreamSource.data` with the position kept in locals for the
    duration of a call.

    Attributes:
        frames: Number of frames to produce.
    """

    def __init__(self, source: StreamSource, frames: int) -> None:
        self.frames = max(0, frames)
        self._source = source
        self._book = array.array("h", bytes(BOOK_SIZE))
        self._prepared = False
        self._done = False
        self._produced = 0
        self._acc = 0
        self._entry: int | None = None
        self._reset_state()

    def _reset_state(self) -> None:
        """Reset the bytecode and DPCM state."""
        self._book[0:len(BOOK_SILENCE)] = array.array("h", BOOK_SILENCE)
        self._done = False
        self._produced = 0
        self._acc = 0
        self._entry = None

    def _prepare(self) -> None:
        """Read the ``tPxd`` header and leave the source at the bytecode.

        Raises:
            SampleError: The header is truncated or malformed.
        """
        self._source.open()
        head = self._source.read(5)
        if len(head) < 5 or head[0:4] != b"tPxD":
            raise SampleError("not a tPxD stream")
        comment = head[4]
        if comment < 2:
            raise SampleError(
                "tPxd comment length %d is too small" % comment)
        rest = self._source.read(comment + 7)
        if len(rest) < comment + 7:
            raise SampleError("tPxd header is truncated")
        self._prepared = True

    def read(self, count: int) -> array.array:
        """Decode up to ``count`` frames.

        Args:
            count: Maximum frames to produce.

        Returns:
            Mono int16 frames; fewer than ``count`` only at end of bytecode
            or at the declared frame count.

        Raises:
            SampleError: The header is malformed or the source cannot be read.
        """
        out = array.array("h")
        if not self._prepared:
            self._prepare()
        limit = min(count, self.frames - self._produced)
        if limit <= 0 or self._done:
            return out

        source = self._source
        data = source.data
        end = len(data)
        pos = source.position
        book = self._book
        table = DELTA_TABLE
        acc = self._acc
        entry = self._entry
        append = out.append
        produced = 0
        done = False

        while produced < limit:
            if entry is None:
                if pos >= end:
                    done = True
                    break
                code = data[pos]
                pos += 1
                if code >= 0xF4:
                    if code == 0xFF:
                        if pos >= end:
                            done = True
                            break
                        acc = ((acc + table[data[pos]] + 0x8000)
                               & 0xFFFF) - 0x8000
                        pos += 1
                        append(acc)
                        produced += 1
                        continue
                    if pos >= end:
                        done = True
                        break
                    index = data[pos]
                    pos += 1
                    deltas = code - 0xF3
                    if pos + deltas > end:
                        pos = end
                        done = True
                        break
                    base = WORDS_PER_ENTRY * index
                    for k in range(deltas):
                        book[base + k] = wrap16(table[data[pos + k]])
                    book[base + deltas] = -1
                    pos += deltas
                    entry = base
                else:
                    entry = WORDS_PER_ENTRY * code

            while produced < limit:
                if entry >= BOOK_WORDS:
                    entry = None
                    break
                delta = book[entry]
                if delta == -1:
                    entry = None
                    break
                acc = ((acc + delta + 0x8000) & 0xFFFF) - 0x8000
                append(acc)
                produced += 1
                entry += 1

        source.position = pos
        self._acc = acc
        self._entry = entry
        self._produced += produced
        if done or self._produced >= self.frames:
            self._done = True
        return out

    def reset(self) -> None:
        """Rewind the source and the decoder state."""
        self._source.reset()
        self._reset_state()
        self._prepared = False

    def close(self) -> None:
        """Release the source's bytes."""
        self._source.close()
