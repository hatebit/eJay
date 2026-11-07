"""Python port of the documented parts of PXD32D4.DLL (1998 eJay engine).

Everything here comes from ``../docs/PXD32D4.md``; the binary is read-only
reference material and was never loaded.  Ported:

* the engine facade - ``ADevice``, ``AInit``, ``AEnd``, ``AStart``,
  ``AStop``, ``AExit``, ``AMemory``, ``AMitte`` and ``RWaveParam``;
* the ``APlay`` request slot and the 16-voice record;
* ``AWaveDauer`` and the ``RWavToTemp`` conversion path (``a3 <= 0``) with
  the ``tP``/RIFF classifier and both decoders;
* ``RWaveLaden``'s load-and-reset step.

The ``tP`` byte code is :class:`tp_codec.TpDecoder`, the reference
implementation of the decoder at ``0x1000759D`` (section 10.3).

Not ported, because the note does not read them: the numbered-sound render
path (``a3 > 0``, its resampler and effects), DirectSound playback
(``DStart`` and the player thread), the tracker sequencer, recording and the
UI helpers.  Playback here stops at the queue: no sink, no mixing.

This module is independent of the later-build port ``pxd32d5``.
"""

from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field

import tp_codec

__all__ = [
    "ADevice",
    "AInit",
    "AEnd",
    "AStart",
    "AStop",
    "AMemory",
    "AMitte",
    "APlay",
    "RWaveParam",
    "RWavToTemp",
    "RWaveLaden",
    "awave_dauer",
    "classify",
    "Engine",
    "Voice",
    "Slot",
    "StreamInfo",
    "UnsupportedCodec",
    "UnsupportedFeature",
    "MAGIC",
]

# ---------------------------------------------------------------------------
# constants from the D4 note
# ---------------------------------------------------------------------------

MAGIC = 0x2A90CB20              # dword_100434A0 - buffers/thread alive
VOICE_COUNT = 16                # word_10022058
VOICE_STRIDE = 0x84             # 0x100429C8
SLOT_STRIDE = 0x108             # 264-byte play-request slot
PLAYER_STRUCT = 0x1FA4          # 8,100-byte player struct per voice
DELTA_TABLE_BYTES = 0x7D0       # 2,000-byte shared ladder
MIX_FRAMES = 75600              # 0x12750 - engine buffer, in frames
BLOCK_FRAMES = 4725             # 0x1275 - half a mixing block
DECODE_BLOCK = 0x12770          # 75,632-byte RWavToTemp session block
WORK_BYTES = 151200             # 0x24EA0 - two wave work buffers
RATE = 44100                    # output rate of the engine and the temp wave
WAV_HEADER = 44                 # RIFF header writer 0x10001A64
TP_GAIN = 1 << 16               # (0x10000 * 0x100) >> 8, unity
STATUS_DEVICE = 0x20            # word_10043480, no 16-bit stereo device

# The ring length was not read out of the D4 post-write code; 30 slots is the
# layout of the later build of the same family (section 6, unverified here).
SLOT_RING = 30


class UnsupportedCodec(Exception):
    """The stream is neither ``tP``-coded nor a RIFF/WAVE file."""


class UnsupportedFeature(Exception):
    """The behaviour was not read out of the D4 binary."""


# ---------------------------------------------------------------------------
# little helpers
# ---------------------------------------------------------------------------


def _s16(value):
    """Interpret the low 16 bits of ``value`` as a signed int16."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


def _u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def _put16(buf, off, value):
    struct.pack_into("<H", buf, off, value & 0xFFFF)


def _half(value):
    """Halve a sample the way the PCM path does (``0x1000782D``).

    ``s >> 1`` keeps the sign bit, so the shift floors negative values.
    """
    return _s16(value) >> 1


def _trunc_div2(value):
    """C integer division by two, truncated toward zero."""
    if value < 0:
        return -((-value) // 2)
    return value // 2


# ---------------------------------------------------------------------------
# stream classification, duration and decoders (sections 8 and 10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamInfo:
    """What ``0x1000AFC5`` learns about a stream (section 10.1)."""

    kind: str               # "tp", "riff" or "unknown"
    offset: int             # first payload byte
    size: int               # payload bytes (-1: read to the end)
    channels: int
    rate: int
    bits: int
    frames: int             # tP frame count; 0 for RIFF


def _scan_data(head):
    """Find the RIFF ``data`` chunk the way the DLL scans for it."""
    limit = min(0x64, max(len(head) - 4, 0))
    for off in range(0x14, limit + 1, 2):
        if head[off:off + 4] == b"data":
            return off
    return None


def classify(blob):
    """Classify ``blob`` and return its :class:`StreamInfo`.

    Args:
        blob: the complete stream.

    Returns:
        ``StreamInfo`` with ``kind == "unknown"`` when neither magic matches.

    Raises:
        UnsupportedCodec: if a ``tP`` header points past the buffer.
    """
    if len(blob) < 8:
        return StreamInfo("unknown", 0, 0, 0, 0, 0, 0)
    if blob[:2] == b"tP":
        length = blob[4]
        start = 4 + length + 8
        if start > len(blob):
            raise UnsupportedCodec("truncated tPxd header")
        frames = _u32(blob, 4 + length + 2)
        return StreamInfo("tp", start, len(blob) - start, 1, RATE, 16,
                          frames)
    if blob[:2] == b"RI":
        off = _scan_data(blob)
        if off is None:
            return StreamInfo("unknown", 0, 0, 0, 0, 0, 0)
        size = _u32(blob, off + 4)
        channels = _u16(blob, 0x16) if len(blob) >= 0x18 else 0
        rate = _u32(blob, 0x18) if len(blob) >= 0x1C else 0
        bits = _u16(blob, 0x22) if len(blob) >= 0x24 else 0
        return StreamInfo("riff", off + 8, size, channels, rate, bits, 0)
    return StreamInfo("unknown", 0, 0, 0, 0, 0, 0)


def _dauer(head, size):
    """``AWaveDauer`` over the first 270 bytes and the file size."""
    if len(head) < 8:
        return 0
    if head[:2] == b"RI":
        value = size
        riff = _u32(head, 4)
        if riff // 7 + riff > size > riff - riff // 7:
            value = riff
        else:
            off = _scan_data(head)
            if off is not None:
                chunk = _u32(head, off + 4)
                if (3 * chunk > size and chunk > 1000
                        and chunk // 6 < size and chunk < size):
                    value = chunk
        if len(head) >= 0x26:
            if _u16(head, 0x14) != 1:      # wFormatTag
                value = -value
            if _u16(head, 0x16) == 1:      # mono
                value <<= 1
            if _u16(head, 0x22) == 8:      # 8 bit
                value <<= 1
            rate = _u32(head, 0x18)
            if rate == 11025:
                value <<= 2
            elif rate == 22050:
                value <<= 1
        return value
    if head[:2] == b"tP":
        length = head[4]
        if length + 10 > len(head):
            return 0
        return 4 * _u32(head, length + 6)
    return 0


def awave_dauer(path):
    """Duration of a ``tP``/RIFF file, normalised to 44.1 kHz stereo bytes.

    The DLL reads 270 bytes and returns 0 for a shorter file (section 8).

    Args:
        path: file to inspect.

    Returns:
        int: byte count, or 0 for an unknown stream.
    """
    with open(path, "rb") as fh:
        head = fh.read(270)
    if len(head) < 270:
        return 0
    return _dauer(head, os.path.getsize(path))


def _decode_tp(blob, info, gain):
    """Decode the ``tP`` payload into 4-byte stereo frames (left only)."""
    frames = max(info.frames, 0)
    out = bytearray(4 * frames)
    decoder = tp_codec.TpDecoder(gain=gain)
    decoder.pending = True      # session +0x48 = 1 for the tPxd branch
    decoder.decode(blob[info.offset:], out, frames)
    return out


def _decode_pcm(blob, info):
    """Decode the RIFF/PCM payload (section 10.4), upsampled by repetition."""
    payload = blob[info.offset:info.offset + info.size]
    width = 2 if info.bits >= 16 else 1
    frame = width * max(info.channels, 1)
    repeat = {44100: 1, 22050: 2, 11025: 4}.get(info.rate, 1)
    out = bytearray()
    for pos in range(0, len(payload) - frame + 1, frame):
        if width == 2:
            raw = _s16(_u16(payload, pos))
        else:
            raw = _s16(((payload[pos] + 0x80) & 0xFF) << 8)
        out += (struct.pack("<h", _half(raw)) + b"\x00\x00") * repeat
    return out


def _compact(frames):
    """Drop the unused right word: 4-byte stereo frames to mono int16."""
    out = bytearray()
    for off in range(0, len(frames) - 3, 4):
        out += frames[off:off + 2]
    return out


def _tail(pcm):
    """128-sample de-click ramp and padding to whole 9,450-byte blocks."""
    data = bytearray(pcm)
    count = len(data) // 2
    for j in range(min(128, count)):
        index = count - 1 - j
        value = _s16(_u16(data, 2 * index))
        _put16(data, 2 * index, (j * value) >> 7)
    blocks = len(data) // (2 * BLOCK_FRAMES) + 1
    blocks = min(blocks, 16)
    target = max(blocks * 2 * BLOCK_FRAMES, len(data))
    data += bytes(target - len(data))
    return data


def _header(data_size):
    """The 44-byte mono 16-bit 44.1 kHz RIFF header (section 6.8 layout)."""
    block = 2
    return (b"RIFF" + struct.pack("<I", data_size + 36)
            + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * block,
                          block, 16)
            + b"data" + struct.pack("<I", data_size))


# ---------------------------------------------------------------------------
# engine facade and play queue
# ---------------------------------------------------------------------------


@dataclass
class Slot:
    """One 264-byte ``APlay`` request (section 6).

    The DLL writes the marker at ``+0x10``, the name at ``+0x12`` (220
    bytes), ``a6`` at ``+0xF0``, ``a4`` at ``+0xF4``, ``a5`` at ``+0xF8``,
    ``a2`` at ``+0xFC``, ``a3`` at ``+0x100`` and ``a12`` at ``+0x104``.
    The position stores at ``+0x38``/``+0x3C``/``+0x40`` were not read for
    D4; they follow the later family layout (unverified).
    """

    marker: int = 0
    mode: int = 0
    a2: int = 0
    a3: int = 0
    a4: int = 0
    a5: int = 0
    a12: int = 0
    start: int = 0
    time: int = 0
    end: int = 0
    name: str = ""


@dataclass
class Voice:
    """A 132-byte voice record (``0x100429C8``, stride ``0x84``)."""

    slots: list = field(
        default_factory=lambda: [Slot() for _ in range(SLOT_RING)])
    cursor: int = 0                 # +0x6A, word
    level: int = 0x100              # +0x44, 8.8
    pan: int = 0                    # +0x4A
    gain: int = 0x10000             # +0x7C, 16.16


class Engine:
    """The documented D4 engine state; no device, thread or mixing."""

    def __init__(self):
        self.started = False        # dword_1004336C
        self.magic = 0              # dword_100434A0
        self.status = 0             # word_10043480
        self.command = 0            # dword_1004342C
        self.mix_size = 0           # dword_1003A3A0
        self.exit_requested = False  # dword_1003A074
        self.device_class = 0       # word_1003B158
        self.device_id = -1         # dword_10022068, -1 = mapper
        self.low_memory = 0         # word_10043418
        self.params = [0] * 199     # dword_1003A3E8
        self.voices = [Voice() for _ in range(VOICE_COUNT)]
        self.delta_table = []
        self.temp_path = os.path.join(tempfile.gettempdir(),
                                      "pxd32d4.tmp")
        self.loaded = bytearray()
        self.work_a = bytearray()
        self.work_b = bytearray()

    # -- device and lifecycle ------------------------------------------------

    def ADevice(self, device=0):
        """Pick the output device; the port records the mapper and class 0."""
        self.device_class = 0
        self.device_id = -1
        if self.device_class:
            self.status |= STATUS_DEVICE
        return self.device_class

    def AInit(self, a1=0.0, mix_rate=RATE):
        """Reset the engine, build the ladder and the 16 voice records."""
        self.status = 0
        self.command = 0
        self.mix_size = 0
        self.exit_requested = False
        self.params = [0] * 199
        self.params[19] = 0x7FFF        # 0x1003A434
        self.delta_table = tp_codec.d4_delta_table()
        self.voices = [Voice() for _ in range(VOICE_COUNT)]
        self.init_arg = a1              # 0x1003D8F0, role unread
        self.mix_rate = mix_rate
        self.started = True
        self.magic = MAGIC
        return self.status

    def AEnd(self):
        """Tear the engine down; returns the status word."""
        if self.magic != MAGIC:
            return self.status
        self.AStop()
        self.magic = 0
        self.started = False
        self.loaded = bytearray()
        self.work_a = bytearray()
        self.work_b = bytearray()
        return self.status

    def AStart(self, a1=0):
        """Record the requested mix size and the start command."""
        self.mix_size = a1
        self.command = 2
        return self.status

    def AStop(self):
        """Clear the transport counters and post the reset command."""
        self.command = 1
        self.mix_size = 0
        for voice in self.voices:
            voice.cursor = 0
        return 1

    def AExit(self):
        """Ask the player thread to leave (``0x10008C3A``)."""
        self.exit_requested = True
        return 1

    def AMemory(self, total_bytes=0):
        """``0x10009885``: low-memory flag for 4-16 MB machines."""
        self.low_memory = 1 if 4_000_000 <= total_bytes <= 16_000_000 else 0
        return self.low_memory

    # -- mixer parameters ----------------------------------------------------

    def AMitte(self, voice, pan):
        """Set one voice's pan word (``0x100025F0``)."""
        self.voices[voice].pan = pan & 0xFFFF
        return 1

    def RWaveParam(self, a, value):
        """``0x10008EAB``: store a parameter, map 60..75 onto voice gain."""
        self.params[a] = value
        if 60 <= a < 60 + VOICE_COUNT:
            x = value / 32767.0 * 1.33
            if x > 1:
                x = x * x * x
            self.voices[a - 60].gain = int(x * 65536)
        return 0

    # -- play queue ----------------------------------------------------------

    def APlay(self, a1=0, a2=0, a3=0, a4=0, a5=0, a6=0, name="",
              a8=0, a9=0, a10=0, a11=0, a12=0):
        """Queue one request in voice ``a8``'s ring (``0x100089D0``).

        The argument order follows the 12-argument call: ``name`` is the
        seventh argument and ``a8`` the voice, as in the later ``PPlay``
        wrapper.  Positions are masked to 4-byte units.

        Returns:
            int: 0, or 0 without writing when the engine is not alive.
        """
        if self.magic != MAGIC:
            return 0
        if not 0 <= a8 < len(self.voices):
            raise IndexError("voice %r out of range" % (a8,))
        voice = self.voices[a8]
        slot = voice.slots[voice.cursor % SLOT_RING]
        slot.marker = a1 & 0xFFFF
        slot.mode = a6
        slot.a2 = a2
        slot.a3 = a3
        slot.a4 = a4
        slot.a5 = a5
        slot.a12 = a12
        slot.start = a9 & ~3
        slot.time = a10 & ~3
        slot.end = a11 & ~3
        slot.name = name
        voice.cursor = (voice.cursor + 1) % SLOT_RING
        return 0

    # -- wave path -----------------------------------------------------------

    def RWavToTemp(self, name, out=None, a3=0, a4=None, a5=0, length=0,
                   a7=0):
        """Convert a stream to the canonical mono temp wave (section 7).

        Args:
            name: input file, or "" when ``a4`` supplies the stream.
            out: output path; defaults to :attr:`temp_path`.
            a3: > 0 selects the numbered-sound render path, which is not
                ported.
            a4: open file object or descriptor to copy a slice from.
            a5: slice offset.
            length: slice length.
            a7: non-zero adds the de-click tail and block padding.

        Returns:
            int: 0 on success, 1 on a read failure, 0 while the engine is
            not started (the DLL's guard at ``0x10010A0B``).

        Raises:
            UnsupportedFeature: for the ``a3 > 0`` render path.
            UnsupportedCodec: for an unknown stream type.
        """
        if not self.started:
            return 0
        if a3 > 0:
            raise UnsupportedFeature(
                "the numbered-sound render path (a3 > 0) was not read")
        blob = self._read_input(name, a4, a5, length)
        if blob is None:
            return 1
        info = classify(blob)
        if info.kind == "unknown":
            raise UnsupportedCodec("unknown stream type")
        head = blob[:270]
        target = _dauer(head, len(blob)) if len(head) >= 270 else 0
        target = max(_trunc_div2(target), 0)
        if info.kind == "tp":
            pcm = _decode_tp(blob, info, TP_GAIN)
        else:
            pcm = _decode_pcm(blob, info)
        pcm = _compact(pcm)[:target]
        if len(pcm) < target:
            pcm += bytes(target - len(pcm))
        if a7:
            pcm = _tail(pcm)
        dst = out if out is not None else self.temp_path
        if not pcm:
            with open(dst, "wb"):
                pass
            return 0
        with open(dst, "wb") as fh:
            fh.write(_header(len(pcm)))
            fh.write(pcm)
        return 0

    def RWaveLaden(self, name, a2=0, a4=None, a5=0, a6=0):
        """Convert and map a wave, then reset the two work buffers."""
        if not self.started:
            return 0
        if a2 != 0x7B:
            rc = self.RWavToTemp(name, self.temp_path, 0, a4, a5, a6, 0)
            if rc:
                return 1
        with open(self.temp_path, "rb") as fh:
            self.loaded = bytearray(fh.read())
        self.work_a = bytearray(WORK_BYTES)
        self.work_b = bytearray(WORK_BYTES)
        return 0

    @staticmethod
    def _read_input(name, a4, a5, length):
        """Read the whole file, or ``length`` bytes at ``a5`` from ``a4``."""
        if a4 is not None:
            if hasattr(a4, "seek") and hasattr(a4, "read"):
                a4.seek(a5)
                return a4.read(length)
            return os.pread(a4, length, a5)
        try:
            with open(name, "rb") as fh:
                return fh.read()
        except OSError:
            return None


def ADevice(device=0):
    """Module-level ``ADevice`` on a fresh engine."""
    return Engine().ADevice(device)


def AInit(a1=0.0, mix_rate=RATE):
    """Module-level ``AInit`` on a fresh engine."""
    return Engine().AInit(a1, mix_rate)


def AEnd(engine=None):
    """Module-level ``AEnd``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).AEnd()


def AStart(a1=0, engine=None):
    """Module-level ``AStart``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).AStart(a1)


def AStop(engine=None):
    """Module-level ``AStop``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).AStop()


def AMemory(total_bytes=0, engine=None):
    """Module-level ``AMemory``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).AMemory(total_bytes)


def AMitte(voice, pan, engine=None):
    """Module-level ``AMitte``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).AMitte(voice, pan)


def APlay(*args, engine=None, **kwargs):
    """Module-level ``APlay``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).APlay(*args, **kwargs)


def RWaveParam(a, value, engine=None):
    """Module-level ``RWaveParam``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).RWaveParam(a, value)


def RWavToTemp(name, out=None, a3=0, a4=None, a5=0, length=0, a7=0,
               engine=None):
    """Module-level ``RWavToTemp``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).RWavToTemp(name, out, a3, a4, a5, length,
                                           a7)


def RWaveLaden(name, a2=0, a4=None, a5=0, a6=0, engine=None):
    """Module-level ``RWaveLaden``; ``engine`` defaults to a fresh engine."""
    return (engine or Engine()).RWaveLaden(name, a2, a4, a5, a6)
