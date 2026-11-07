"""Incremental decoder for RIFF/WAVE PCM sample streams."""

from __future__ import annotations

import array
import struct
import sys

from ..binary import s16
from ..constants import SAMPLE_RATE
from .sample_error import SampleError
from .stream_source import StreamSource


class RiffStreamDecoder:
    """Decode PCM WAVE block by block from the loaded source bytes.

    The left channel is kept and samples are repeated to reach 44.1 kHz,
    matching :class:`~player.pxd.riff_decoder.RiffDecoder`.  At the native
    rate the frames are copied from the source with slices; only resampling
    needs a per-frame loop.

    Attributes:
        frames: Number of output frames to produce.
    """

    def __init__(self, source: StreamSource, frames: int) -> None:
        self.frames = max(0, frames)
        self._source = source
        self._prepared = False
        self._data = b""
        self._offset = 0
        self._size = 0
        self._available = 0
        self._rate = SAMPLE_RATE
        self._bits = 16
        self._channels = 1
        self._frame_bytes = 2
        self._step = 1.0
        self._out_index = 0
        self._produced = 0
        self._done = False

    def _prepare(self) -> None:
        """Read the chunk headers and locate the data payload.

        Raises:
            SampleError: The stream is not supported PCM WAVE.
        """
        data = self._source.data
        if (len(data) < 12 or data[0:4] != b"RIFF"
                or data[8:12] != b"WAVE"):
            raise SampleError("not a RIFF/WAVE stream")

        pos = 12
        fmt = None
        data_offset = None
        data_size = None
        while pos + 8 <= len(data):
            tag = data[pos:pos + 4]
            size = struct.unpack_from("<I", data, pos + 4)[0]
            body = pos + 8
            if tag == b"fmt ":
                fmt = data[body:body + size]
            elif tag == b"data":
                data_offset = body
                data_size = size
                if fmt is not None:
                    break
            pos = body + size + (size & 1)

        if fmt is None or len(fmt) < 16:
            raise SampleError("RIFF stream has no fmt chunk")
        if data_offset is None or data_size is None:
            raise SampleError("RIFF stream has no data chunk")

        tag, channels, rate = struct.unpack_from("<HHI", fmt, 0)
        bits = struct.unpack_from("<H", fmt, 14)[0]
        if tag != 1:
            raise SampleError(
                "compressed WAV (format %d) is not supported" % tag)
        if channels not in (1, 2):
            raise SampleError(
                "unsupported channel count %d" % channels)
        if bits not in (8, 16):
            raise SampleError("unsupported sample size %d" % bits)
        if rate <= 0:
            raise SampleError("bad sample rate %d" % rate)

        self._rate = rate
        self._bits = bits
        self._channels = channels
        self._frame_bytes = channels * (bits // 8)
        self._step = rate / float(SAMPLE_RATE)
        self._data = data
        self._offset = data_offset
        self._size = min(data_size, max(0, len(data) - data_offset))
        if bits == 8:
            self._available = (
                (self._size + channels - 1) // channels)
        else:
            self._available = self._size // self._frame_bytes
        self._prepared = True

    def _sample_at(self, index: int) -> int:
        """Return mono input frame ``index`` from the data payload."""
        if self._bits == 8:
            offset = self._offset + index * self._channels
            return (self._data[offset] - 128) << 8
        return s16(self._data, self._offset + index * self._frame_bytes)

    def _copy_native(self, limit: int) -> array.array:
        """Return up to ``limit`` frames at the native sample rate."""
        start = self._out_index
        stop = min(start + limit, self._available, self.frames)
        if stop <= start:
            return array.array("h")
        first = self._offset + start * self._frame_bytes
        last = self._offset + stop * self._frame_bytes
        chunk = self._data[first:last]
        if self._bits == 8:
            return array.array(
                "h",
                ((value - 128) << 8
                 for value in chunk[0::self._channels]))
        out = array.array("h")
        out.frombytes(chunk)
        if sys.byteorder == "big":
            out.byteswap()
        if self._channels == 2:
            return out[0::2]
        return out

    def read(self, count: int) -> array.array:
        """Decode up to ``count`` frames.

        Args:
            count: Maximum frames to produce.

        Returns:
            Mono int16 frames at 44.1 kHz; fewer than ``count`` at end of
            data or at the declared frame count.

        Raises:
            SampleError: The header is unsupported or the source cannot be
                read.
        """
        out = array.array("h")
        if not self._prepared:
            self._prepare()
        if count <= 0 or self._done:
            return out

        if self._rate == SAMPLE_RATE:
            source_frames = self._available
        else:
            source_frames = int(
                self._available * SAMPLE_RATE / float(self._rate))
        limit = min(count, self.frames - self._produced,
                    source_frames - self._produced)
        if limit <= 0:
            self._done = True
            return out

        if self._rate == SAMPLE_RATE:
            out = self._copy_native(limit)
            self._out_index += len(out)
            self._produced += len(out)
        else:
            last = self._available - 1
            end = self._out_index + limit
            while self._out_index < end:
                target = int(self._out_index * self._step)
                if target > last:
                    target = last
                out.append(self._sample_at(target))
                self._out_index += 1
                self._produced += 1

        if (self._produced >= self.frames
                or self._produced >= source_frames):
            self._done = True
        return out

    def reset(self) -> None:
        """Rewind the source and the decoder state."""
        self._source.reset()
        self._prepared = False
        self._data = b""
        self._offset = 0
        self._size = 0
        self._available = 0
        self._out_index = 0
        self._produced = 0
        self._done = False

    def close(self) -> None:
        """Close the underlying source and release its bytes."""
        self._source.close()
        self._data = b""
        self._prepared = False
        self._done = True
