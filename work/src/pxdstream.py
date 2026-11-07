"""Stream a PXD32D5 stream (.pxd / RIFF-WAVE) as it is played.

    python src/pxdstream.py data/hyper-test.pxd
    python src/pxdstream.py song.pxd -d Speakers --block 2048 --gain 2.0

Unlike ``sdpxdplay.py`` (which decodes the whole file up front through
``sdmixplay.decode_sample``) this module keeps the file handle open and decodes
incrementally, one block at a time, so a large ``.pxd`` never needs to reside
fully in memory.  It is engine-free (like ``sdpxdplay.py``) and talks to
sounddevice directly; nothing here imports the ported engine except the shared
delta table and C-semantics helpers from ``pxd32d5``.

Formats
-------
tPxd (``.pxd``): ``tPxD`` + len byte + comment + NUL + 2 pad bytes + i32 frame
count + 2 pad bytes, then the DPCM/code-book bytecode.  The frame count is the
i32 at offset ``len + 6`` (``h[4] + 6``) and the bytecode starts at
``4 + len + 8`` (verified against ``data/hyper-test.pxd``: len=42, frames at
48, data at 54).  The decoder reproduces ``sub_10016361``: the DPCM integrator
and the code book persist across blocks, exactly as they persist across blocks
in the ported engine (pxd32d5.py invariants 6/7).

RIFF/WAVE PCM: 8 or 16 bit, mono or stereo, 11025 / 22050 / 44100 Hz; the
left channel is kept and each sample is repeated to reach 44.1 kHz, matching
the engine's PCM path (pxd32d5.py ``_decode_pcm``) and ``sdmixplay``.

The tPxd decoder is strictly sequential: the read cursor only moves forward and
nothing is read from disk until the decoder consumes it
(pxd32d5.py ``_decode_tp`` loops on ``pos < end`` with ``pos`` only
increasing).  ``test_tp_real_files`` confirms the decoder consumes the input to
its last byte, so a streaming reader that stops at EOF is behaviourally
equivalent to decoding the whole file ahead of time.

``read_frames(n)`` returns up to ``n`` mono int16 frames (little-endian bytes)
at 44.1 kHz, decoding only as much of the file as needed.
"""

from __future__ import annotations

import argparse
import array
import os
import struct
import sys

# Shared, single-source-of-truth constants from the ported engine.
from pxd32d5 import DELTA_TABLE, _put16, _s16, _wrap16

SAMPLE_RATE = 44100
BLOCK_FRAMES = 2048          # write granularity, ~46 ms

# Engine gains: the file (PPlay) path uses pan=256 -> unity (0x10000);
# RWavToTemp uses pan=512 -> (512 * 0x10000) >> 8 = 0x20000 (2x).
UNITY_GAIN = 0x10000
ENGINE_GAIN = 0x20000

BOOK_SIZE = 8100             # sub_1001186B allocates malloc(0x1FA4)
BOOK_SILENCE = (0, 0, 0, 0, 0, -1)   # entry 0, written by sub_10011EFF

__all__ = [
    "PXDError",
    "PXDStream",
    "SAMPLE_RATE",
    "BLOCK_FRAMES",
    "UNITY_GAIN",
    "ENGINE_GAIN",
    "build_parser",
    "list_devices",
    "open_stream",
    "play",
    "main",
]


class PXDError(ValueError):
    """The file is not a readable .pxd / RIFF stream, or a value is bad."""


# ---------------------------------------------------------------------------
# sequential file reader: nothing is read until the decoder consumes it
# ---------------------------------------------------------------------------


class _FileReader:
    """Read sequentially from an open file.

    The read cursor only moves forward, so bytes already consumed are never
    re-read and the decoder never pulls more from disk than it consumes.
    """

    def __init__(self, fh) -> None:
        self._fh = fh

    def read(self, n: int) -> bytes:
        return self._fh.read(n)

    def read1(self):
        """Return one byte as an int, or None at EOF."""
        b = self._fh.read(1)
        if not b:
            return None
        return b[0]


# ---------------------------------------------------------------------------
# the streaming decoder
# ---------------------------------------------------------------------------


class PXDStream:
    """Decode a ``.pxd`` (tPxd) or RIFF/WAVE file incrementally.

    ``read_frames(n)`` returns up to ``n`` mono int16 frames as little-endian
    bytes at 44.1 kHz.  The file stays open and is read sequentially; ``close``
    releases it.

    ``gain`` is the engine-style emit gain applied while decoding:
    * ``UNITY_GAIN`` (0x10000) - the decoder output is the integrator itself,
      matching the PPlay file path (pan=256) and ``sdmixplay``.
    * ``ENGINE_GAIN`` (0x20000) - matches ``RWavToTemp`` (pan=512, 2x).
    """

    def __init__(self, gain: int = UNITY_GAIN) -> None:
        self._gain = int(gain)
        self._fh = None
        self._reader = None
        self._kind = None          # "tp" or "riff"
        self._declared = 0         # tPxd: total frames to produce
        self._produced = 0         # tPxd: frames produced so far
        self._done = False
        # tPxd decoder state, persisted across read_frames calls (invariant 7)
        self._book = bytearray(BOOK_SIZE)
        struct.pack_into("<6h", self._book, 0, *BOOK_SILENCE)
        self._acc = 0              # DPCM integrator (session[4])
        self._entry = None         # current code-book offset mid-entry, or None
        self._tp_eof = False       # bytecode stream hit EOF
        # PCM streaming state: the current input mono sample and how many
        # output repetitions of it remain (each input sample is repeated
        # ``mult`` times to reach 44.1 kHz).
        self._pcm_sample = 0
        self._pcm_repeats = 0
        self._pcm_eof = False

    # -- open ----------------------------------------------------------------

    def open(self, path: str) -> "PXDStream":
        """Open ``path`` and parse its header; the bytecode/data is not read."""
        if self._fh is not None:
            self.close()
        try:
            fh = open(path, "rb")
        except OSError as exc:
            raise PXDError("%s: %s" % (path, exc)) from exc
        self._fh = fh
        self._reader = _FileReader(fh)
        head = fh.read(270)      # enough for any tPxd header (max 267 bytes)
        if len(head) < 5:
            fh.close()
            self._fh = None
            self._reader = None
            raise PXDError("%s: file is too short" % path)
        if head[0:4] == b"tPxD":
            self._open_tp(head)
        elif head[0:4] == b"RIFF" and head[8:12] == b"WAVE":
            self._open_riff(head)
        else:
            fh.close()
            self._fh = None
            self._reader = None
            raise PXDError("%s: unknown stream format" % path)
        return self

    def _open_tp(self, head: bytes) -> None:
        length = head[4]
        if length < 2:
            raise PXDError("tPxd comment length %d is too small" % length)
        end = 4 + length
        if end + 8 > len(head):
            raise PXDError("tPxd header is truncated")
        if head[end - 1] != 0:
            raise PXDError("tPxd comment is not NUL-terminated")
        # frame count is the i32 at h[4] + 6 == end + 2
        frames = struct.unpack_from("<i", head, end + 2)[0]
        self._kind = "tp"
        self._declared = frames if frames > 0 else 0
        self._produced = 0
        self._done = False
        self._acc = 0
        self._entry = None
        self._book = bytearray(BOOK_SIZE)
        struct.pack_into("<6h", self._book, 0, *BOOK_SILENCE)
        # position the file at the start of the bytecode
        self._fh.seek(end + 8)   # == 4 + length + 8

    def _open_riff(self, head: bytes) -> None:
        """Locate the fmt and data chunks in the header already in memory."""
        pos = 12
        fmt = None
        data_off = None
        data_size = None
        limit = len(head)
        while pos + 8 <= limit:
            tag = head[pos:pos + 4]
            size = struct.unpack_from("<I", head, pos + 4)[0]
            if tag == b"fmt ":
                fmt = head[pos + 8:pos + 8 + size]
            elif tag == b"data":
                data_off = pos + 8
                data_size = size
                break
            pos += 8 + size + (size & 1)
        if fmt is None or len(fmt) < 16:
            self._fh.close()
            self._fh = None
            self._reader = None
            raise PXDError("RIFF stream has no fmt chunk")
        if data_off is None or data_size is None:
            self._fh.close()
            self._fh = None
            self._reader = None
            raise PXDError("RIFF stream has no data chunk")
        tag, channels, rate = struct.unpack_from("<HHI", fmt, 0)
        bits = struct.unpack_from("<H", fmt, 14)[0]
        if tag != 1:
            raise PXDError("compressed WAV (format %d) is not supported" % tag)
        if channels not in (1, 2):
            raise PXDError("unsupported channel count %d" % channels)
        if bits not in (8, 16):
            raise PXDError("unsupported sample size %d" % bits)
        if rate <= 0:
            raise PXDError("bad sample rate %d" % rate)
        mult = 44100 // rate
        if mult not in (1, 2, 4):
            raise PXDError("unsupported sample rate %d" % rate)
        frame_bytes = (1 if channels == 1 else 2) if bits == 8 else \
            (2 if channels == 1 else 4)
        self._fh.seek(data_off)
        self._kind = "riff"
        self._declared = 0
        self._produced = 0
        self._done = False
        self._pcm_sample = 0
        self._pcm_repeats = 0
        self._pcm_eof = False
        self._riff = {
            "channels": channels, "bits": bits, "rate": rate,
            "mult": mult, "frame_bytes": frame_bytes,
        }

    # -- decode --------------------------------------------------------------

    def read_frames(self, n: int) -> bytes:
        """Return up to ``n`` mono int16 frames as little-endian bytes.

        Returns ``b""`` when the stream is exhausted.  For tPxd the declared
        frame count is honoured: if the bytecode ends early the remainder is
        silence, exactly as the ported engine truncates/pads its output.
        """
        if n <= 0 or self._done:
            return b""
        limit = n
        if self._kind == "tp":
            remaining = self._declared - self._produced
            if remaining <= 0:
                self._done = True
                return b""
            limit = min(n, remaining)
        out = array.array("h")
        if self._kind == "tp":
            out.extend(self._decode_tp(limit))
        else:
            out.extend(self._decode_pcm(limit))
        got = len(out)                       # frames produced
        if self._kind == "tp" and got < limit and self._at_eof():
            # bytecode ended early: pad silence to the declared length
            out.extend(array.array("h", bytes(2 * (limit - got))))
            got = limit
        self._produced += got
        if self._kind == "tp" and self._produced >= self._declared:
            self._done = True
        elif self._kind == "riff" and self._at_eof():
            self._done = True
        return out.tobytes()

    def _at_eof(self) -> bool:
        """True if the underlying file has no more data to offer."""
        return self._tp_eof or self._pcm_eof

    @staticmethod
    def _emit_sample(acc: int, gain: int) -> int:
        """One engine-style decode step: ``(acc * gain) >> 16``, saturated.

        Equivalent to ``emit()`` with a silent destination, returning a signed
        int16.
        """
        prod = acc * gain
        if prod > 0x7FFFFFFF or prod < -0x80000000:
            s = 0x7FFF if prod > 0 else 0x8000
        else:
            s = (prod >> 16) & 0xFFFF
        return s - 0x10000 if s & 0x8000 else s

    def _decode_tp(self, limit: int) -> array.array:
        """Streaming sub_10016361: DPCM/code-book, one block at a time.

        ``self._entry`` persists mid-entry across calls so an entry is never
        cut in half arbitrarily; the integrator ``self._acc`` and code book
        ``self._book`` persist across blocks (invariant 7).
        """
        out = array.array("h")
        book = self._book
        table = DELTA_TABLE
        gain = self._gain
        reader = self._reader
        acc = self._acc
        entry = self._entry
        frames = 0
        while frames < limit:
            if entry is None:
                c = reader.read1()
                if c is None:
                    self._tp_eof = True
                    break
                if c >= 0xF4:
                    if c != 0xFF:
                        idx = reader.read1()
                        if idx is None:
                            self._tp_eof = True
                            break
                        count = c - 0xF3
                        ops = reader.read(count)
                        if len(ops) < count:
                            self._tp_eof = True
                            break
                        base = 16 * idx
                        for k in range(count):
                            _put16(book, base + 2 * k, table[ops[k]])
                        _put16(book, base + 2 * count, 0xFFFF)
                        entry = base
                    else:
                        b = reader.read1()
                        if b is None:
                            self._tp_eof = True
                            break
                        acc = _wrap16(acc + table[b])
                        out.append(self._emit_sample(acc, gain))
                        frames += 1
                        continue
                else:
                    entry = 16 * c
            # play the current code-book entry
            while frames < limit:
                if entry + 2 > len(book):
                    entry = None        # malformed entry: stop playing it
                    break
                delta = _s16(book, entry)
                if delta == -1:
                    entry = None
                    break
                acc = _wrap16(acc + delta)
                out.append(self._emit_sample(acc, gain))
                frames += 1
                entry += 2
        self._acc = acc
        self._entry = entry
        return out

    def _read_input_sample(self) -> int | None:
        """Read one input frame (left channel) and return it as a mono int16.

        Returns None at EOF.  Reads are strictly sequential, so the decoder
        never pulls more than one frame ahead of what it plays.
        """
        r = self._riff
        raw = self._reader.read(r["frame_bytes"])
        if len(raw) < r["frame_bytes"]:
            self._pcm_eof = True
            return None
        if r["bits"] == 16:
            return _s16(raw, 0)          # left channel = first sample
        return (raw[0] - 128) << 8       # 8 bit, left channel

    def _decode_pcm(self, limit: int) -> array.array:
        """Streaming RIFF/PCM: mono left channel, repeated to 44.1 kHz.

        Each input sample is repeated ``mult`` times (mult = 44100 / rate,
        i.e. 4/2/1 for 11025/22050/44100 Hz).  This is exactly
        ``sdmixplay``'s ``mono[min(int(i * step), last)]`` resampling, but
        driven sequentially from disk one frame at a time.
        """
        out = array.array("h")
        mult = self._riff["mult"]
        while len(out) < limit:
            if self._pcm_repeats <= 0:
                src = self._read_input_sample()
                if src is None:
                    break
                self._pcm_sample = src
                self._pcm_repeats = mult
            out.append(self._pcm_sample)
            self._pcm_repeats -= 1
        return out

    # -- lifecycle -----------------------------------------------------------

    def done(self) -> bool:
        return self._done

    def frames(self) -> int:
        """Frames produced so far (tPxd: not past the declared count)."""
        return self._produced

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self._fh = None
        self._reader = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------------
# gain helpers
# ---------------------------------------------------------------------------


def apply_gain(samples: array.array, gain: float) -> None:
    """Scale int16 ``samples`` in place, clipping to the int16 range."""
    if gain == 1.0:
        return
    for i, value in enumerate(samples):
        scaled = int(value * gain)
        if scaled > 0x7FFF:
            scaled = 0x7FFF
        elif scaled < -0x8000:
            scaled = -0x8000
        samples[i] = scaled


# ---------------------------------------------------------------------------
# playback (sounddevice, lazy import)
# ---------------------------------------------------------------------------


def open_stream(device=None, frames: int = BLOCK_FRAMES):
    """Open a blocking PortAudio stream for mono int16 at 44.1 kHz."""
    try:
        import sounddevice as sd
    except ImportError as exc:                      # pragma: no cover
        raise PXDError(
            "playback needs the optional 'sounddevice' package "
            "('pip install sounddevice')") from exc
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    try:
        stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=frames, device=device)
        stream.start()
    except sd.PortAudioError as exc:
        raise PXDError("cannot open the output device: %s" % exc) from exc
    return stream


def list_devices() -> int:
    try:
        import sounddevice
    except ImportError as exc:
        print("pxdstream: %s" % exc, file=sys.stderr)
        return 1
    try:
        print(sounddevice.query_devices())
    except sounddevice.PortAudioError as exc:
        print("pxdstream: %s" % exc, file=sys.stderr)
        return 1
    return 0


def play(args, stream=None) -> int:
    """Stream-decode and play ``args.input``; returns a process status."""
    src = args.input
    if not os.path.isfile(src):
        print("pxdstream: %s: no such file" % src, file=sys.stderr)
        return 1
    try:
        pxd = PXDStream(gain=UNITY_GAIN).open(src)
    except PXDError as exc:
        print("pxdstream: %s" % exc, file=sys.stderr)
        return 1
    if stream is None:
        try:
            stream = open_stream(args.device, args.block)
        except PXDError as exc:
            print("pxdstream: %s" % exc, file=sys.stderr)
            pxd.close()
            return 1
        owned = True
    else:
        owned = False

    frames = 0
    try:
        block = max(64, int(args.block))
        while True:
            data = pxd.read_frames(block)
            if not data:
                break
            samples = array.array("h")
            samples.frombytes(data)
            apply_gain(samples, args.gain)
            stream.write(samples.tobytes())
            frames += len(samples)
    except KeyboardInterrupt:
        if not args.quiet:
            print("pxdstream: interrupted", file=sys.stderr)
        pxd.close()
        if owned:
            try:
                stream.stop()
            finally:
                stream.close()
        return 130
    finally:
        pxd.close()
        if owned:
            try:
                stream.stop()
            finally:
                stream.close()

    seconds = frames / float(SAMPLE_RATE)
    if not args.quiet:
        print("%s  %d frames  %.2f s  via sounddevice"
              % (src, frames, seconds))
        print("done")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxdstream",
        description="Stream a PXD32D5 stream (.pxd / RIFF-WAVE) as it is "
                    "played, decoding incrementally instead of up front.")
    p.add_argument("input", nargs="?", metavar="INPUT",
                   help="source file to play")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device (index or name substring); see "
                        "--list-devices")
    p.add_argument("--block", type=int, default=BLOCK_FRAMES, metavar="N",
                   help="write block in frames (default: %d)" % BLOCK_FRAMES)
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="sample gain applied after decode (default: 1.0)")
    p.add_argument("-l", "--list-devices", action="store_true",
                   help="list sounddevice output devices and exit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_devices:
        return list_devices()
    if args.input is None:
        parser.error("the following arguments are required: INPUT")
    if args.gain <= 0:
        parser.error("--gain must be positive")
    if args.block <= 0:
        parser.error("--block must be positive")
    return play(args)


if __name__ == "__main__":
    sys.exit(main())
