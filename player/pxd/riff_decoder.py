"""Standalone decoder for RIFF/WAVE PCM sample streams."""

from __future__ import annotations

import array
import struct
import sys

from ..constants import SAMPLE_RATE
from .sample_error import SampleError


class RiffDecoder:
    """Decode PCM WAVE to mono int16 at 44.1 kHz.

    The original engine keeps the left channel of a stereo stream and repeats
    samples to reach 44.1 kHz; this decoder mirrors that behaviour.
    """

    def length(self, data: bytes) -> int:
        """Return the frame count a WAVE stream declares.

        Args:
            data: RIFF file, or enough of it to reach the data chunk.

        Returns:
            Declared mono int16 frames at :data:`SAMPLE_RATE`.

        Raises:
            SampleError: The stream is not supported PCM WAVE, or its data
                chunk extends past the bytes provided.
        """
        fmt, offset, size = self._chunks(data)
        channels, rate, bits = self._format(fmt)
        if offset + size > len(data):
            raise SampleError("RIFF stream is truncated")
        if bits == 8:
            frames = (size + channels - 1) // channels
        else:
            frames = size // ((bits // 8) * channels)
        if rate == SAMPLE_RATE or not frames:
            return frames
        return int(frames * SAMPLE_RATE / rate)

    def decode(self, data: bytes) -> array.array:
        """Decode one RIFF/WAVE stream.

        Args:
            data: Whole RIFF file.

        Returns:
            Mono int16 frames at :data:`SAMPLE_RATE`.

        Raises:
            SampleError: The stream is not supported PCM WAVE.
        """
        fmt, offset, size = self._chunks(data)
        channels, rate, bits = self._format(fmt)
        payload = data[offset:offset + size]

        if bits == 8:
            mono = [(value - 128) << 8 for value in payload[0::channels]]
        else:
            samples = array.array("h")
            usable = len(payload) - len(payload) % (2 * channels)
            samples.frombytes(payload[:usable])
            if sys.byteorder == "big":
                samples.byteswap()
            mono = samples[0::channels]

        if rate == SAMPLE_RATE or not mono:
            return array.array("h", mono)

        step = rate / float(SAMPLE_RATE)
        count = int(len(mono) * SAMPLE_RATE / rate)
        last = len(mono) - 1
        return array.array(
            "h", [mono[min(int(i * step), last)] for i in range(count)])

    @staticmethod
    def _chunks(data: bytes) -> tuple[bytes, int, int]:
        """Return ``(fmt chunk, data offset, data length)`` for a WAVE.

        Raises:
            SampleError: The stream is not RIFF/WAVE or lacks a chunk.
        """
        if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise SampleError("not a RIFF/WAVE stream")

        pos = 12
        fmt = None
        offset = 0
        size = 0
        found = False
        while pos + 8 <= len(data):
            tag = data[pos:pos + 4]
            length = struct.unpack_from("<I", data, pos + 4)[0]
            if tag == b"fmt ":
                fmt = data[pos + 8:pos + 8 + length]
            elif tag == b"data":
                offset = pos + 8
                size = length
                found = True
                break
            pos += 8 + length + (length & 1)

        if fmt is None or len(fmt) < 16:
            raise SampleError("RIFF stream has no fmt chunk")
        if not found:
            raise SampleError("RIFF stream has no data chunk")
        return fmt, offset, size

    @staticmethod
    def _format(fmt: bytes) -> tuple[int, int, int]:
        """Validate ``fmt`` and return ``(channels, rate, bits)``.

        Raises:
            SampleError: The format is not supported PCM WAVE.
        """
        tag, channels, rate = struct.unpack_from("<HHI", fmt, 0)
        bits = struct.unpack_from("<H", fmt, 14)[0]
        if tag != 1:
            raise SampleError(
                "compressed WAV (format %d) is not supported" % tag)
        if channels not in (1, 2):
            raise SampleError("unsupported channel count %d" % channels)
        if bits not in (8, 16):
            raise SampleError("unsupported sample size %d" % bits)
        if rate <= 0:
            raise SampleError("bad sample rate %d" % rate)
        return channels, rate, bits
