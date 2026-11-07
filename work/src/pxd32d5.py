"""Python re-implementation of several exports of PXD32D5-D4.DLL.

Recovered by disassembling ``pxd32d5_d4.dll`` (not checked in) with
``work/tools/pxd_dis.py`` (addresses below are image VAs; ``AStop`` needed an
address-range disassembly because the decompiler omitted its body):

    int __usercall PInit@<eax>(double a1@<st0>);          // 0x10022318
    int __stdcall  RWavToTemp(LPCSTR, LPCSTR, int, HANDLE,
                              LONG, LONG, int);           // 0x10020290
    int            PClose();                              // 0x10022339
    int __stdcall  PPlay(LPCSTR, int, int, int, int, int);// 0x10022370
    int __stdcall  APlay(int,int,int,int,int,int,LPCSTR,
                         int,int,int,int,int);            // 0x1001775B
    int            AStop();                               // 0x10014516

See ``RWavToTemp.md`` for the reverse-engineering notes these names/offsets
come from.

The DLL splits naturally into three layers:

    PInit / PClose  - thin wrappers around the "A..." sound engine
    RWavToTemp      - file bookkeeping: it turns any supported input
                      (a RIFF/WAVE file, a "tP"-coded file, or a slice of an
                      already opened stream) into the canonical temp file the
                      rest of the DLL plays, or renders one numbered sound
                      into a temp file.
    the "replay"/"effect" cores (sub_10016361, sub_100165A9, sub_1000E3E0)

Everything of the first two layers is reproduced here, plus both decoders used
by ``RWavToTemp``: the RIFF/PCM path and the proprietary "tP" DPCM/code-book
codec (``_decode_tp``).  The only stage left as a hook is the echo/chorus/
reverb chain ``sub_1000E3E0`` used by the ``a3 > 0`` render path - see
``Engine._effects_chain``.

``PPlay`` / ``APlay`` fill a per-voice playback queue; ``AStart`` starts the
player loop (or ``Engine.pump`` drives it synchronously) and the drain/mixer
feeds an ``OutputSink`` from ``pxdsink`` (``FileSink`` or a stdlib ``ctypes``
waveOut sink).  See ``docs/PLAYBACK.md``.
"""

from __future__ import annotations

import array
import os
import struct
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

import pxdsink

from tp_codec import d4_delta_table

__all__ = [
    "PInit",
    "PClose",
    "PStart",
    "PPlay",
    "RWavePause1",
    "RWavePause2",
    "RWaveStop",
    "RWaveLaden",
    "RWavToTemp",
    "APlay",
    "Engine",
    "Session",
    "PlaySlot",
    "Voice",
    "awave_dauer",
    "parse_pxd_comment",
    "PxdComment",
    "PxdCommentError",
    "UnsupportedCodec",
    "engine",
]

# ---------------------------------------------------------------------------
# constants taken from the decompilation
# ---------------------------------------------------------------------------

BUFFER_SAMPLES = 75600          # dword_1004B2EC   - engine buffer, in frames
BLOCK_ALIGN = 4725              # dword_1004B2D0   - block size / 2
DECODE_BLOCK = 75632            # session.block_size initial value (v34[12])
SCRATCH_CLEAR = 0x127B0         # 75696 - bytes zeroed before every decode
DECODER_SLACK = 1024            # safety headroom for a decoder entry overrun
DECODE_TAIL = 220               # 0xDC  - bytes of input header the DLL keeps
WAV_HEADER_SIZE = 44            # v25 when dword_10096CD8 == 4
INIT_MAGIC = 714132256          # dword_10096DFC - "engine buffers alive"

# APlay / PPlay play-request queue (see ../pxd/PXD32D5-D4-engine.md 3.2)
VOICE_COUNT = 32                # word_1004B2FA - voices in dword_10095108
SLOTS_PER_VOICE = 30            # APlay's ring length (the "% 30" wrap)
PLAY_FLAG_MASK = 0xFFFFFFFC     # a9/a10/a11 are rounded down to 4-byte units
PLAY_START_SENTINEL = 1763823600   # dword_10095144's "no start time" value
PLAY_MODE_FILE = 99             # low word of unk_1004B304 (0x1004B304), PPlay's a6

# Playback (docs/PLAYBACK.md).  dword_1004B314 is the mix ring that
# sub_1001186B allocates as GlobalAlloc(size + 512) + 44, dword_1004B2EC the
# per-voice engine buffer and dword_1008E418 / dword_100826FC the guards used
# by sub_10016FD5 / sub_10015907.
RING_BYTES = 907200             # dword_1004B314 - 226800 stereo frames (5.14 s)
PLAY_RATE = 44100               # dword_10093ECA in DStart
PLAY_CHANNELS = 2               # word_10093ED4 = 16 bit, stereo
PLAY_BITS = 16
PLAY_LOOKAHEAD = 163840         # dword_100826FC - max decode window
PLAY_GUARD = 120                # sub_10015907 subtracts 120 from its window
PLAY_OVERRUN = 64 * 4           # _decode_tp may finish an entry up to 64
                                # frames past max_frames (hard = frames + 64)
PLAY_DUP_GUARD = 64             # sub_10016C77 duplicates up to front - 64
PLAY_END = 705600               # dword_1008E630 - "playback has run out"
PLAY_DEFER = 125000             # sub_10015B6C defers starts further out
PLAY_TICK = 0.010               # thread interval (the DLL loops ~6 ms)
PLAY_QUIET_TICK = 0.030


# dword_100668F0 .. dword_10066950: 25-entry pitch -> playback-rate table that
# AInit installs.  0x4000 (index 12) is unity.
PERIOD_TABLE = [
    0x8000, 31097, 29188, 27553, 26020, 24540, 23162, 21862, 20640,
    19479, 18393, 17357, 0x4000, 15548, 14594, 13777, 13010, 12270,
    11581, 10931, 10320, 9739, 9196, 8678, 0x2000,
]

# dword_100668EC is the same table, but starts one entry earlier (it is the
# dword immediately in front of dword_100668F0).  RWavToTemp indexes it with
# (13 - pitch); index 13 therefore gives 0x4000 == unity, which confirms the
# layout.  Index 0 is not visible in the decompilation - extrapolated here
# from the neighbouring ratio (~1.0537).
RATIO_TABLE = [34528] + PERIOD_TABLE


# dword_1008E350: sub_10011EFF's 256-entry int16 DPCM step ladder, symmetric
# around index 128 = 0.  The D4 builder (0x10003252) decodes to the same table
# value for value, so the port imports that one implementation instead of
# repeating the recurrence.
DELTA_TABLE = d4_delta_table()
BOOK_SIZE = 8100                # sub_1001186B allocates malloc(0x1FA4)
BOOK_SILENCE = (0, 0, 0, 0, 0, -1)   # entry 0, written by sub_10011EFF


class UnsupportedCodec(RuntimeError):
    """Raised for input streams whose decoder is not present in this port."""


from pxdhelpers import (_idiv, _s16, _put16, _put32, _u16, _u32, _s32)


# ---------------------------------------------------------------------------
# session struct: the 132-byte head of the global PLAYER struct dword_1008E380
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """dword_1008E380 - the stream the DLL renders from.

    Only the first 132 bytes are relevant to RWavToTemp (its stereo split
    helper qmemcpy's exactly that much).  Field comments give the original
    ``a1[n]`` dword index and byte offset.
    """

    codebook: int = 0              # +0    a1[0]   waveform/code book pointer
    chan_state: int = 0            # +4    a1[1]   per-channel state pointer
    vol_word: int = 0              # +8    a1[4]   (word) volume word
    read_offset: int = 0           # +12   a1[3]   read position in the source
    data_offset: int = 0           # +20   a1[5]   (word) offset of audio data
    stream_end: int = 0            # +36   a1[9]   end of stream (file size)
    stream_type: int = 0           # +40   a1[10]  stream format/flags
    has_riff: bool = False         #       the RIFF branch of sub_10019DEE ran
    length: int = 0                # +44   a1[11]  bytes still to render
    block_size: int = DECODE_BLOCK  # +48   a1[12]  decode block size
    produced: int = 0              # +52   a1[13]  bytes produced by the last decode
    write_offset: int = 0          # +56   a1[14]  write position in the destination
    pan: int = 512                 # +68   a1[17]  panning / gain word
    chan_mode: int = 0             # +72   a1[18]  hi word: 0 = normal, 1/2 = split
    subtype: int = 0               # +74   a1[37]  (word) stream subtype
    field21: int = 0               # +84   a1[21]
    header: bytes = b""            # +112  a1[28]  first 220 bytes of the input
    out_ptr: int = 0               # +116  a1[29]  destination data pointer
    src_base: int = 0              # +120  a1[30]  source mapping base pointer
    volume: int = 0x10000          # +124  a1[31]  volume, 16.16 fixed point
    region: int = 0                # +128  a1[32]  destination region size
    gain: int = 0                  #       dword_10093A78 = (pan * volume) >> 8
    src: bytes = b""               #          the mapped source file
    book: bytearray = None         #       dword_1008B750, 8100-byte code book

    def __post_init__(self):
        self.book = bytearray(BOOK_SIZE)
        struct.pack_into("<6h", self.book, 0, *BOOK_SILENCE)


# ---------------------------------------------------------------------------
# the play-request queue: one entry of a voice's 30-slot ring
# ---------------------------------------------------------------------------


@dataclass
class PlaySlot:
    """One 264-byte request in a voice's ring (what ``APlay`` writes).

    Offsets are from the slot base (../pxd/PXD32D5-D4-engine.md section
    3.2).  The name is the 220-byte file-name field ``lstrcpyA`` fills
    from ``lpString2``.
    """

    # Despite the historical names these are ring positions/clock values:
    # sub_10015B6C copies them into dword[14] (play position), [15] (start
    # time) and [16] (end position) verbatim.
    flags: int = 0        # +0    a9  - ring start position
    start: int = 0        # +4    a10 + a9 - start time, or the sentinel
    duration: int = 0     # +8    a11 - ring end position
    marker: int = 0       # +16   (word) a1, matched against the voice's id
    name: str = ""        # +18   220-byte file name (lstrcpyA)
    source: int = 0       # +240  a6 - mode/source pointer (PLAY_MODE_FILE)
    length: int = 0       # +244  a4
    offset: int = 0       # +248  a5
    primary: int = 0      # +252  a2 (a zero takes a3)
    secondary: int = 0    # +256  a3 (a zero takes a2)
    extra: int = 0        # +260  a12


@dataclass
class Voice:
    """``dword_10095108[33 * v]`` - one of the 32 voice control blocks.

    ``APlay`` uses the high word of ``[26]`` as the ring's write cursor;
    ``_drain`` (``sub_10015B6C``) uses the low word as the read cursor and
    ``word[48]`` as the voice state.
    """

    slots: list = None      # dword_10095108[33*v + 25], 30 * 264 bytes
    write_index: int = 0    # HIWORD(dword_10095108[33*v + 26])
    read_index: int = 0     # LOWORD(dword_10095108[33*v + 26])
    state: int = 0          # word[48]: -2 new, -1 streaming, 0 idle
    source_name: str = ""   # the file the open slot points at (port only)
    error: str = None       # why the voice was given up (port only)

    # -- the rest of the 33-dword control block (docs/PLAYBACK.md) --------
    session: object = None  # the per-voice 132-byte decode state
    src: bytes = b""        # the opened file, held instead of a HANDLE
    play_pos: int = 0       # dword[14] - play position in the ring (bytes)
    slot_end: int = 0       # dword[15] - slot start/end cursor
    total: int = 0          # dword[16] - bytes to play
    extra: int = 0          # dword[17] - loop/limit
    volume: int = 0x10000   # dword[31] - 16.16 volume
    marker_word: int = 0    # word[54] - matched against the slot marker
    handle: object = None   # dword[21] - the open file object

    def __post_init__(self):
        if self.slots is None:
            self.slots = [PlaySlot() for _ in range(SLOTS_PER_VOICE)]


# ---------------------------------------------------------------------------
# AWaveDauer - 0x100125A5
# ---------------------------------------------------------------------------


def awave_dauer(path: str) -> int:
    """Length of ``path`` normalised to 44100 Hz / 16 bit / stereo.

    Returns a *byte* count except for the "tP" branch (which returns a sample
    count times four).  Non-PCM RIFF files come back negative - callers use
    that to detect "cannot be turned into a plain wave".  Returns 0 on any
    failure.
    """
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            buf = fh.read(0x10E)
    except OSError:
        return 0
    if len(buf) < 270:
        return 0
    if buf[0:2] == b"RI":
        v5 = struct.unpack_from("<i", buf, 4)[0]
        v10 = struct.unpack_from("<i", buf, 40)[0]
        v6 = _s16(buf, 20)             # wFormatTag
        v7 = _s16(buf, 22)             # nChannels
        v8 = _s16(buf, 24)             # nSamplesPerSec
        v9 = _s16(buf, 34)             # wBitsPerSample

        if _idiv(v5, 7) + v5 > size and v5 > 0 and v5 - _idiv(v5, 7) < size:
            size = v5
        if (3 * v10 > size and v10 > 0 and _idiv(v10, 6) < size
                and v10 < size):
            size = v10
        if v6 != 1:
            size = -size
        if v7 == 1:
            size *= 2
        if v9 == 8:
            size *= 2
        if v8 == 11025:
            size *= 4
        elif v8 == 22050:
            size *= 2
        return size
    if buf[0:2] == b"tP":
        # dword at an offset encoded in the low byte of the length field
        off = (_u32(buf, 4) & 0xFF) + 6
        if off + 4 > len(buf):
            return 0
        return 4 * struct.unpack_from("<i", buf, off)[0]
    return 0


# ---------------------------------------------------------------------------
# tPxd comment field - docs/PXD_FORMAT.md
# ---------------------------------------------------------------------------

PXD_MAGIC = b"tPxD"


class PxdCommentError(ValueError):
    """Raised when a tPxD comment field is malformed."""


@dataclass(frozen=True)
class PxdComment:
    """The validated comment of a tPxD stream.

    ``length`` is the byte at offset 0x04 (which counts itself); ``text`` is
    the ``length - 2`` ASCII bytes before the trailing NUL, and ``lines`` is
    the text split on CR/LF.  The line layout is application metadata, not
    part of the container format, so it is not validated.
    """

    length: int
    text: str
    lines: tuple[str, ...]


def parse_pxd_comment(head: bytes) -> PxdComment:
    """Parse and validate the comment field of a ``tPxD`` header.

    ``head`` only needs to contain the whole comment field (``4 + len``
    bytes); a full file or the 220-byte header buffer works.  The layout is
    ``"tPxD" + len + (len - 2) ASCII bytes + 0x00``, where ``len`` counts
    itself (docs/PXD_FORMAT.md).

    Raises :class:`PxdCommentError` when the magic, length, terminator or
    encoding is wrong.
    """
    if len(head) < 5:
        raise PxdCommentError("header is too short for a tPxD comment")
    if head[0:4] != PXD_MAGIC:
        raise PxdCommentError(
            "not a tPxD stream (magic %r)" % (bytes(head[0:4]),))

    length = head[4]
    if length < 2:
        raise PxdCommentError(
            "comment length %d is too small (minimum 2)" % length)
    end = 4 + length
    if end > len(head):
        raise PxdCommentError(
            "comment length %d needs %d bytes, only %d available"
            % (length, end, len(head)))
    if head[end - 1] != 0:
        raise PxdCommentError("comment is not NUL-terminated")

    raw = bytes(head[5:end - 1])
    if 0 in raw:
        raise PxdCommentError("comment contains an embedded NUL")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise PxdCommentError("comment is not ASCII: %s" % exc) from exc

    lines = tuple(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return PxdComment(length=length, text=text, lines=lines)


# ---------------------------------------------------------------------------
# the engine
# ---------------------------------------------------------------------------


class Engine:
    """Global state + behaviour of the DLL.

    The exported functions are written against one process-wide instance
    (``engine``), exactly like the DLL's globals.  Instantiate a separate
    ``Engine`` to get isolated state.
    """

    def __init__(self) -> None:
        tmp = tempfile.gettempdir()
        self.session = Session()

        # --- engine globals -------------------------------------------------
        self.started = False           # dword_10096CC8 - rendering allowed
        self.magic = 0                 # dword_10096DFC - buffers allocated
        self.status = 0                # word_10096DE0  - error/status bits
        self.device_class = 0          # word_1008BBE0  - waveOut capability
        self.output_kind = 0           # dword_10096CD8  4 => write RIFF header
        self.path_name = tmp + os.sep  # PathName - directory for temp files
        self.temp_stream = os.path.join(tmp, "pxd32d5_stream.tmp")  # byte_1008BAE8
        self.temp_wave = os.path.join(tmp, "pxd32d5_wave.tmp")      # byte_1008E64C
        self.stream_size = 0           # dword_10096D9C - size of the input
        self.stream_cache = (None, 0, 0)  # dword_10096D24/D28/D2C
        self.half_rate = False         # word_10096D7C == 2

        # per-sound tables, index 65 * (sound - 1) (dword_1008E828/30/2C)
        self.sound_volume: list[int] = []
        self.sound_pitch: list[int] = []
        self.sound_loop: list[int] = []

        # RWaveParam() state: 300 entries because AInit() zeroes 299 of them
        # although the symbol is only declared as dword_10082B1C[19].
        self.wave_param = [0] * 300    # dword_10082B1C
        self.wave_curve = [0] * 204    # dword_10095184

        # effect parameters (dword_10090758, 75C, 760, 764, 768, 770, 774, 778)
        self.fx_params = [0] * 8
        self.fx = {
            "dword_10093A8C": 0,
            "dword_100823F0": 0,
            "dword_1008BAB0": 0,
            "dword_10082FD0": 0,
            "dword_10082FD4": 0,
            "dword_10082708": 0,
            "dword_1008270C": 0,
            "dword_10082FE0": 0,
            "dword_10082FE4": 0,
            "dword_10082FE8": 0,
            "dword_10082FEC": 0,
            "dword_1008353C": 0,
            "dword_10083540": 0,
            "dword_10083544": 0,
            "dword_10083548": 0,
            "dword_1008354C": 0,
            "dword_10082FDC": 0,
        }
        self.history = [0] * 2520      # dword_1008BBF0[2520]
        self.history_pos = 0           # dword_10082660
        self.mix_a = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)  # 10096D90
        self.mix_b = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)  # 1008BBE8
        self.mix_c = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)  # 1008BBEC

        # 32 voice control blocks (dword_10095108; see docs section 4.5)
        self.voices = [Voice() for _ in range(VOICE_COUNT)]
        self.dword_10096D88 = 0        # player-thread command register

        # -- playback state (docs/PLAYBACK.md) -------------------------------
        self.ring = bytearray(RING_BYTES)  # dword_1008E410
        self.dword_10082710 = 0        # stereo-ready front of the ring
        self.dword_100950D4 = 0        # zeroed/mixed front of the ring
        self.dword_1008E414 = 0        # play position handed to the sink
        self.dword_1008E630 = PLAY_END     # "playback has run out" threshold
        self.dword_1008E418 = 0x4000   # guard used by sub_10015907
        self.dword_100826FC = PLAY_LOOKAHEAD
        self.dword_1008BBD8 = 0        # play limit set by sub_10017632
        self.dword_100829F0 = 0        # AStart's argument
        self.dword_10082BEC = 0
        self.dword_1008BBC8 = 0
        self.word_10083528 = 0         # end-of-play flag
        self.word_10096E04 = 0         # "thread should mix" flag
        self.dword_10096CB4 = 0        # "play finished" status for REffekt
        self._play_end = 0             # highest requested end position
        self.laden_wave = b""          # RWaveLaden's mapped temp wave

        self.sink = None               # pxdsink.OutputSink, created lazily
        self.sink_failed = False
        self.autostart_thread = True   # AStart spawns the player thread
        self.paused = False
        self._sink_lock = threading.RLock()
        self._lock = threading.RLock()
        self._thread = None
        self._thread_stop = threading.Event()
        self._thread_wake = threading.Event()

        # decoder hook: (session, out_buffer, base_offset) -> bytes produced
        self.decode_hook = None

        # Port only: the DLL cannot raise, so a decoder failure has to be
        # recorded and skipped instead of freezing the mix fronts.
        self.playback_errors = []      # "file: reason", one per lost voice
        self.last_error = None         # last exception out of a mix tick

    # -- PInit() dependencies ------------------------------------------------

    def ADevice(self, a1: int = 0) -> int:
        """0x10012AEA - pick a waveOut device.

        The original walks waveOutGetNumDevs()/waveOutGetDevCapsA() looking for
        16 bit stereo 44.1 kHz, then for progressively simpler formats, and
        records the result in word_1008BBE0 (0 = 16 bit stereo, 1 = 16 bit
        mono, 2 = 8 bit mono 44.1k, 3 = 8 bit mono 22.05k).  Rendering into a
        file does not need the device, so the probe is reduced to "assume a
        44.1 kHz stereo capable card" (class 0).
        """
        self.device_class = 0
        return 0

    def AInit(self, a1: float = 1.0, a2: int = 0) -> int:
        """0x1001149F - reset the mixer and allocate its buffers."""
        self._stop_thread()
        if self.sink is not None:
            self.sink.close()
            self.sink = None
        self.sink_failed = False
        self.session = Session()
        self.magic = 0
        self.counters = {}              # dword_10096CE8/CEC/CF0/CF8, Number...
        self.volume_state = a2          # dword_1008E378
        self.wave_param = [0] * 300     # zeroed up to index 298 by AInit
        self.wave_curve = [0] * 204
        self.rate_params = [0] * 60     # dword_1008B774
        self.gain = float(a1)           # dbl_10066968/70/78/80
        # dword_100826C4 = 32000 (29400 when word_10096D7C == 2)
        self.sample_rate = 29400 if self.half_rate else 32000
        self.period_table = list(PERIOD_TABLE)
        if self.device_class != 0:
            self.status |= 0x20         # word_10096DE0 |= 0x20
        self.mix_a = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)
        self.mix_b = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)
        self.mix_c = bytearray(4 * BUFFER_SAMPLES + DECODER_SLACK)
        self.history = [0] * 2520
        self.history_pos = 0
        self.voices = [Voice() for _ in range(VOICE_COUNT)]
        self.ring = bytearray(RING_BYTES)
        self.dword_10082710 = 0
        self.dword_100950D4 = 0
        self.dword_1008E414 = 0
        self.dword_1008BBD8 = 0
        self.dword_100829F0 = 0
        self.dword_10082BEC = 0
        self.dword_1008BBC8 = 0
        self.word_10083528 = 0
        self.word_10096E04 = 0
        self.dword_10096CB4 = 0
        self._play_end = 0
        self.playback_errors = []
        self.last_error = None
        self.paused = False
        self.stream_size = 0
        self.stream_cache = (None, 0, 0)
        # sub_1001186B() allocates the player structs and sets the magic.
        self.magic = INIT_MAGIC
        if self.magic == INIT_MAGIC:
            # sub_100178D4(0): create the critical sections and the mixer
            # thread, set dword_10096CC8 = 1 (rendering allowed).
            self.started = True
        return self.status

    def RWaveParam(self, a1: int, a2: int) -> int:
        """RWaveParam - set one wave parameter plus its 16.16 curve value."""
        if 0 <= a1 < len(self.wave_param):
            self.wave_param[a1] = a2
        if 60 <= a1 < 129:
            v3 = a2 / 32767.0 * 1.33
            if v3 > 1.0:
                v3 = v3 * v3 * v3
            idx = 33 * a1 - 1980
            if 0 <= idx < len(self.wave_curve):
                self.wave_curve[idx] = int(v3 * 65536.0)
        return self.status

    def AStop(self) -> int:
        """0x10014516 - stop playback and clear the stop counters.

        The decompiler omitted this body; it was disassembled from the
        binary at ``0x10014516``.  It zeroes ten playback globals, sets
        ``dword_10096D88 = 1`` - the player thread's "full reset" command
        (``sub_10014589``) - then waits for the thread (``sub_100144C9``)
        and returns 1 (not the status word).
        """
        self.dword_10096D30 = 0        # 0x10096D30
        self.dword_10096D34 = 0        # 0x10096D34
        self.dword_10082BEC = 0        # 0x10082BEC
        self.dword_10096D88 = 1        # 0x10096D88 - stop command
        self.dword_10093A7C = 0        # 0x10093A7C
        self.dword_100826B8 = 0        # 0x100826B8
        self.dword_1008B764 = 0        # 0x1008B764
        self.dword_100835A8 = 0        # 0x100835A8
        self.dword_10096D18 = 0        # 0x10096D18
        self.dword_1008E63C = 0        # 0x1008E63C
        self._thread_wake.set()
        if self._thread is not None and self._thread.is_alive():
            self._wait_play_command()  # sub_100144C9
        # With no thread the command stays pending, exactly as the DLL leaves
        # it when its player thread is absent.
        return 1

    def _wait_play_command(self) -> None:
        """``sub_100144C9`` - wait until the player thread consumes the
        command register ``dword_10096D88``.

        The DLL sleeps 8 ms at a time until ``StartAddress`` has run
        ``sub_10014589`` (command 1) or ``sub_10017632`` (command 2) and
        cleared the register.  The wait is capped at the DLL's ~2 s
        (20 x 100 ms here) so a dead thread cannot hang the caller.
        """
        deadline = time.monotonic() + 2.0
        while self.dword_10096D88 and time.monotonic() < deadline:
            time.sleep(0.002)

    # -- playback: start, thread and the queue drain -------------------------

    def AStart(self, a1: int = 176223600) -> int:
        """0x10017603 - ask the player thread to start.

            dword_10082BEC = 0;
            dword_10096D88 = 2;
            dword_100829F0 = a1;
            sub_100144C9();
            return word_10096DE0;

        ``PStart`` passes 176223600 (= 44100 * 3996).  The DLL's thread
        exists from ``AInit``; the port starts it on the first ``AStart`` so
        an engine that never plays has no thread (and no device).  With
        ``autostart_thread`` cleared the command is consumed synchronously,
        which is what the tests use to pump the mixer deterministically.
        """
        self.dword_10082BEC = 0
        self.dword_10096D88 = 2
        self.dword_100829F0 = a1
        if self.autostart_thread:
            self._ensure_thread()
            self._thread_wake.set()
            self._wait_play_command()
        else:
            self._consume_command()
        return self.status

    def _ensure_thread(self) -> None:
        """Start the ``StartAddress`` equivalent if it is not running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread_stop.clear()
        self._thread = threading.Thread(target=self._player_loop,
                                        name="pxd-player", daemon=True)
        self._thread.start()

    def _stop_thread(self) -> None:
        self._thread_stop.set()
        self._thread_wake.set()
        if self.sink is not None:
            # unblock a writer waiting for a device buffer
            self.sink.stop()
        thread = self._thread
        if thread is not None:
            thread.join(2.0)
        self._thread = None

    def _player_loop(self) -> None:
        """0x10017AB4 (``StartAddress``) without the message pump.

        The DLL loop runs ``sub_10017255``, ``RTimer`` and ``DPlayUpdate`` and
        consumes commands 1/2.  Here one iteration is ``_consume_command``
        plus ``_mix_tick``; the sink replaces ``DPlayUpdate``.

        A tick is guarded: a Python exception would otherwise end the thread
        and leave the fronts frozen (the DLL has nothing that can raise).
        """
        while not self._thread_stop.is_set():
            self._consume_command()
            try:
                self._mix_tick()
            except Exception as exc:      # port only, see _mix_voices
                self.last_error = "%s: %s" % (type(exc).__name__, exc)
            interval = (PLAY_TICK if self.word_10096E04
                        else PLAY_QUIET_TICK)
            self._thread_wake.wait(interval)
            self._thread_wake.clear()

    def _consume_command(self) -> int:
        """Run the command ``StartAddress`` would have consumed."""
        cmd = self.dword_10096D88
        if cmd == 1:
            self.sub_10014589()
            self.dword_10096D88 = 0
        elif cmd == 2:
            self.sub_10017632(self.dword_100829F0)
            self.dword_10096D88 = 0
        return cmd

    def sub_10017632(self, a1: int) -> int:
        """0x10017632 - reset the mix fronts and start decoding.

        When the previous run has already finished (``dword_1008BBD8 <= 0``)
        it clears the error bit, the ring fronts and every voice marker,
        drains the queue, records the new play limit in ``dword_1008BBD8``
        and finally sets ``word_10096E04`` - the flag the mix tick tests.
        """
        if self.magic != INIT_MAGIC:
            return self.status
        with self._lock:
            if self.dword_1008BBD8 <= 0 and a1 > 0:
                self.dword_1008BBC8 = 0
                self.status &= ~8
                self.dword_10082710 = 0
                self.dword_100950D4 = 0
                self.dword_1008E414 = 0
                self.ring[:] = bytes(RING_BYTES)
                self.word_10083528 = 0
                self._play_end = 0
                for voice in self.voices:
                    voice.marker_word = 0
            self.dword_1008BBD8 = a1
            while self._drain():
                pass
            self.word_10096E04 = 1
            self._ensure_sink()
        return self.status

    def sub_10014589(self) -> int:
        """0x10014589 - full reset: stop the device, close the voices,
        clear the ring and re-arm the decoders."""
        if self.magic != INIT_MAGIC:
            return self.status
        with self._lock:
            for voice in self.voices:
                self._finish_voice(voice)
                voice.read_index = 0
                voice.write_index = 0
                voice.marker_word = 0
                voice.play_pos = 0
                voice.total = 0
                voice.slot_end = 0
                voice.session = None
            self.dword_100950D4 = 0
            self.dword_10082710 = 0
            self.dword_1008E414 = 0
            self.ring[:] = bytes(RING_BYTES)
            self.word_10083528 = 0
            self.word_10096E04 = 0
            self._play_end = 0
            self.paused = False
            if self.sink is not None:
                self.sink.stop()          # sub_1001B0FF(1)
        return self.status

    def _ensure_sink(self) -> None:
        """Open the waveOut sink once; stay silent if there is no device."""
        with self._sink_lock:
            if self.sink is not None or self.sink_failed:
                return
            try:
                self.sink = pxdsink.WaveOutSink()
            except Exception:
                # The DLL sets status bit 2 when the device is unusable and
                # carries on; playback then only advances the ring.
                self.sink = None
                self.sink_failed = True
                self.status |= 2

    def _drain(self) -> int:
        """``sub_10015B6C`` - start the next queued request, one per call.

        This keeps the file branch and its selection rule: the voice with the
        lowest slot start time wins, and a request is deferred only after
        playback has finished (``word_10083528``), never before.  The
        memory-source branch and the marker re-sync path are not ported.
        """
        if self.magic != INIT_MAGIC:
            return 0
        best = None
        best_slot = None
        best_start = None
        for voice in self.voices:
            if voice.state != 0 or voice.read_index == voice.write_index:
                continue
            slot = voice.slots[voice.read_index]
            if slot.source != PLAY_MODE_FILE or not slot.name:
                continue
            start = _s32(slot.start)
            if (self.word_10083528 > 0
                    and start > self.dword_1008E414 + PLAY_DEFER):
                continue
            if best is None or start < best_start:
                best, best_slot, best_start = voice, slot, start
        if best is None:
            return 0
        best.read_index = (best.read_index + 1) % SLOTS_PER_VOICE
        if best_slot.duration <= 0:
            return 1                    # sub_10015B6C gives up on v13[16] <= 0
        self._open_slot(best, best_slot)
        return 1

    def _open_slot(self, voice: Voice, slot) -> bool:
        """The file branch of ``sub_10015B6C``: open, sniff, arm a voice."""
        # Slot +0 is APlay's a9 (ring start position), +4 is a10 + a9 (start
        # time, used only for ordering) and +8 is a11 (ring end position);
        # sub_10015B6C copies them into dword[14]/[15]/[16] verbatim.
        voice.marker_word = slot.marker
        voice.play_pos = slot.flags
        voice.slot_end = slot.start
        voice.total = slot.duration
        voice.source_name = slot.name
        voice.error = None
        voice.extra = slot.extra
        voice.volume = 0x10000
        try:
            with open(slot.name, "rb") as fh:
                data = fh.read()
        except OSError:
            voice.state = 0
            return False
        sess = Session()
        sess.src = data
        sess.header = data[:DECODE_TAIL]
        sess.stream_end = len(data)
        sess.read_offset = 0
        sess.volume = 0x10000      # 16.16 unity
        sess.pan = 256             # unity gain: (256 * 0x10000) >> 8
        sess.block_size = DECODE_BLOCK
        self._parse_header(sess)   # sub_10019DEE / sub_10014D10(1)
        if not sess.has_riff and sess.stream_type != 1:
            voice.state = 0
            return False
        voice.src = data
        voice.session = sess
        voice.state = -1           # word[48] = -2, then streaming
        if voice.total > self._play_end:
            self._play_end = voice.total
        return True

    @staticmethod
    def _finish_voice(voice: Voice) -> None:
        if voice.handle is not None:
            try:
                voice.handle.close()
            except OSError:
                pass
        voice.handle = None
        voice.src = b""
        voice.session = None
        voice.state = 0

    # -- the mix tick (sub_10015666) -----------------------------------------

    def _mix_tick(self) -> int:
        """One ``RTimer``/``sub_10015666`` iteration.

        Order matches the DLL: zero ahead of the write front
        (``sub_10016FD5``), decode every active voice into the ring
        (``sub_10015907`` + ``sub_10016237``), duplicate left to right
        (``sub_10016C77`` + ``sub_10016325``), then hand the finished range
        to the device (``DPlayUpdate``/``sub_1001B464``).
        """
        if self.magic != INIT_MAGIC:
            return self.status
        if not self.word_10096E04:
            return self.status
        with self._lock:
            self._drain()
            self._zero_ahead()
            self._mix_voices()
            self._stereo_ready()
            self._feed_sink()
            if self._all_idle():
                self._feed_sink()
                # The DLL waits for the fronts to pass dword_1008E630; the
                # port's fronts stop at the requested end, so reaching it is
                # the equivalent test.  Without any request there is nothing
                # to finish (AStart alone must not latch the end flag).
                if (self._play_end > 0
                        and self.dword_1008E414 >= self._play_end
                        and not self.word_10083528):
                    self.word_10083528 = 1
                    self.dword_10096CB4 = 1
        return self.status

    def _all_idle(self) -> bool:
        for voice in self.voices:
            if voice.state != 0:
                return False
            if voice.read_index != voice.write_index:
                return False
        return True

    def _zero_ahead(self) -> None:
        """``sub_10016FD5`` - zero the ring ahead of the mixed front."""
        target = self.dword_10082710 + PLAY_LOOKAHEAD
        cap = self.dword_1008E414 + RING_BYTES - 0x4000
        if target > cap:
            target = cap
        if self._play_end > 0 and target > self._play_end:
            target = self._play_end
        if target <= self.dword_100950D4:
            return
        self._ring_zero(self.dword_100950D4, target)
        self.dword_100950D4 = target

    def _ring_zero(self, start: int, end: int) -> None:
        while start < end:
            idx = start % RING_BYTES
            n = min(end - start, RING_BYTES - idx)
            self.ring[idx:idx + n] = bytes(n)
            start += n

    def _mix_voices(self) -> None:
        """``sub_10015907``/``sub_10016237`` - decode the active voices."""
        limit = self.dword_100950D4 - PLAY_GUARD - PLAY_OVERRUN
        if self._play_end > 0 and self.dword_100950D4 >= self._play_end:
            # The zero-ahead stops at the requested end, so the guard must go
            # too or the last 120 bytes would never be decoded.
            limit = self._play_end
        if limit <= 0:
            return
        for voice in self.voices:
            if voice.state != -1 or voice.session is None:
                continue
            end = limit
            if voice.total > 0:
                end = min(end, voice.total)
            if (0 < voice.slot_end < PLAY_START_SENTINEL
                    and voice.slot_end < end):
                end = voice.slot_end
            sess = voice.session
            while voice.play_pos + 4 <= end:
                idx = voice.play_pos % RING_BYTES
                # leave room for the decoder's entry overrun
                room = RING_BYTES - idx - DECODER_SLACK
                chunk = min(end - voice.play_pos, room, DECODE_BLOCK)
                frames = chunk // 4
                if frames <= 0:
                    break
                try:
                    produced = self._decode_block(sess, self.ring, idx,
                                                  frames)
                except Exception as exc:
                    # A stream the decoder cannot render must not hold the
                    # front: the voice is given up and the failure recorded.
                    voice.error = "%s: %s" % (type(exc).__name__, exc)
                    produced = 0
                if produced <= 0:
                    if voice.error is None:
                        voice.error = "the decoder produced no samples"
                    self.playback_errors.append(
                        "%s (%s)" % (voice.source_name or "?", voice.error))
                    self._finish_voice(voice)
                    break
                voice.play_pos += produced
                if sess.read_offset >= sess.stream_end:
                    # The ring is already zeroed up to the requested end; the
                    # DLL keeps playing that tail, so run the cursor out too.
                    if voice.total > 0:
                        voice.play_pos = voice.total
                    break
            ended = voice.total > 0 and voice.play_pos >= voice.total
            if ended or sess.read_offset >= sess.stream_end:
                self._finish_voice(voice)

    def _stereo_ready(self) -> None:
        """``sub_10016C77`` - turn the mono mix into stereo in place.

        The front may only run up to the least advanced voice (minus the
        64-byte guard), never up to the zero-ahead frontier: otherwise the
        duplicator would publish samples the decoder has not produced yet.
        """
        ready = self.dword_100950D4
        for voice in self.voices:
            if voice.state == -1:
                ready = min(ready, voice.play_pos)
        if self._all_idle():
            guard = 0
        else:
            guard = PLAY_DUP_GUARD
            ready -= guard
        if self._play_end > 0 and ready > self._play_end:
            ready = self._play_end
        if ready <= self.dword_10082710:
            return
        self._duplicate(self.dword_10082710, ready)
        self.dword_10082710 = ready

    def _duplicate(self, start: int, end: int) -> None:
        """``sub_10016325`` - copy every left sample into the right channel."""
        while start < end:
            idx = start % RING_BYTES
            n = min(end - start, RING_BYTES - idx)
            n -= n % 4
            if n <= 0:
                break
            seg = self.ring[idx:idx + n]
            out = bytearray(n)
            out[0::4] = seg[0::4]
            out[1::4] = seg[1::4]
            out[2::4] = seg[0::4]
            out[3::4] = seg[1::4]
            self.ring[idx:idx + n] = out
            start += n

    def _feed_sink(self) -> None:
        """``DPlayUpdate``/``sub_1001B464`` - Lock/copy/Unlock."""
        if self.paused or self.sink is None:
            return
        start = self.dword_1008E414
        end = self.dword_10082710
        if end <= start:
            return
        try:
            while start < end:
                idx = start % RING_BYTES
                n = min(end - start, RING_BYTES - idx)
                self.sink.write(bytes(self.ring[idx:idx + n]))
                start += n
            self.dword_1008E414 = end
        except OSError:
            self.sink = None
            self.sink_failed = True
            self.status |= 2

    # -- synchronous helpers (tests / CLI) ----------------------------------

    def pump(self, ticks: int = 1) -> "Engine":
        """Run the player loop by hand, without the thread."""
        for _ in range(ticks):
            self._consume_command()
            self._mix_tick()
        return self

    def wait_for_end(self, timeout: float = 10.0) -> bool:
        """Pump until ``word_10083528`` or ``timeout``"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if self.word_10083528:
                return True
            time.sleep(0.001)
        return False

    # -- transport ----------------------------------------------------------

    def play_position(self) -> int:
        """Current ring position in bytes (``dword_1008E414``).

        Pass this as ``a9`` (and ``a9 + length`` as ``a11``) when queueing a
        request while the mixer is already running.
        """
        return self.dword_1008E414

    def RWavePause1(self) -> int:
        """Stop the device buffers, keep the ring position."""
        self.paused = True
        if self.sink is not None:
            self.sink.pause()
        return 1

    def RWavePause2(self) -> int:
        """Resume the device buffers."""
        self.paused = False
        if self.sink is not None:
            self.sink.resume()
        return 1

    def RWaveStop(self) -> int:
        """0x10017BC8 - stop and release the playback state."""
        if not self.started:
            return 0
        if self.sink is not None:
            self.sink.stop()
        with self._lock:
            self.paused = True
            for voice in self.voices:
                self._finish_voice(voice)
            self.dword_100950D4 = 0
            self.dword_10082710 = 0
            self.dword_1008E414 = 0
            self.ring[:] = bytes(RING_BYTES)
            self.word_10083528 = 0
            self.word_10096E04 = 0
            self._play_end = 0
        return 1

    def RWavePlay(self) -> int:
        """0x10017B86 - the DLL only reports the status word."""
        return self.status

    def RWaveLaden(self, lpString2, a2: int = 123, a3=None, a4: int = 0,
                   lDistanceToMove: int = 0) -> int:
        """0x1001A152 - convert a file into the temp wave and map it.

        ``a2 == 123`` skips the conversion (the DLL's "already converted"
        marker).  The mapping is held in ``laden_wave``; the DirectSound
        hand-off (``sub_1001CA3B(4)``) is not ported, so this does not start
        playback by itself.
        """
        if not self.started:
            return 0
        if a2 != 123:
            if self.RWavToTemp(lpString2, self.temp_wave, 0, a3, a4,
                               lDistanceToMove, 0) != 0:
                return 1
        try:
            with open(self.temp_wave, "rb") as fh:
                self.laden_wave = fh.read()
        except OSError:
            return 1
        self.paused = False
        return 0

    def APlay(self, a1: int, a2: int, a3: int, a4: int, a5: int, a6: int,
              lpString2, a8: int, a9: int, a10: int, a11: int,
              a12: int) -> int:
        """0x1001775B - queue one play request on voice ``a8``.

        Faithful to the DLL: it only appends a 264-byte entry to the voice's
        30-slot ring and advances the write cursor.  ``sub_10015B6C`` (the
        player thread, ``Engine._drain``) later opens ``lpString2`` and decodes
        it.  ``a9`` is the ring start position and ``a11`` the ring end
        position, so a request queued during playback must carry the current
        position (``Engine.play_position()``).

        ``a9``/``a10``/``a11`` are rounded down to 4-byte units
        (``& 0xFFFFFFFC``); ``a2``/``a3`` are normalised so a zero one takes
        the other.  ``a6`` is the mode/source pointer - ``PPlay`` passes the
        ``PLAY_MODE_FILE`` marker (``&unk_1004B304``, whose word value is
        99).  Returns 0, also when the engine is down.
        """
        if self.magic != INIT_MAGIC:               # dword_10096DFC
            return 0
        if not 0 <= a8 < len(self.voices):         # the DLL does not check
            return 0
        flags = a9 & PLAY_FLAG_MASK                # LOBYTE(v12) = a9 & 0xFC
        v16 = _s32(a10 & PLAY_FLAG_MASK)           # compared as signed
        v17 = a11 & PLAY_FLAG_MASK
        if a3 == 0:
            a3 = a2
        if a2 == 0:
            a2 = a3
        voice = self.voices[a8]
        slot = voice.slots[voice.write_index]
        slot.marker = _wrap16(a1)                  # *(_WORD *)(v14 + 16)
        slot.primary = a2                           # +252
        slot.secondary = a3                         # +256
        slot.extra = a12                            # +260
        slot.length = a4                            # +244
        slot.offset = a5                            # +248
        slot.source = a6                            # +240
        slot.name = lpString2                       # lstrcpyA(v14 + 18, ...)
        slot.flags = flags                          # +0
        slot.start = (PLAY_START_SENTINEL if v16 <= 0
                      else (v16 + flags) & 0xFFFFFFFF)   # +4 (dword store)
        slot.duration = v17                         # +8
        voice.write_index = (voice.write_index + 1) % SLOTS_PER_VOICE
        return 0

    def AEnd(self) -> int:
        """AEnd - tear the engine down again."""
        if self.magic != INIT_MAGIC:
            return self.status
        self.AStop()
        self._stop_thread()
        if self.dword_10096D88:
            # no thread to consume the stop command: run the reset here
            self.sub_10014589()
            self.dword_10096D88 = 0
        if self.sink is not None:
            self.sink.close()           # mixerClose in the DLL
            self.sink = None
        self.laden_wave = b""
        self.started = False            # sub_100179FD(0) clears dword_10096CC8
        self.magic = 0
        self.mix_a = bytearray()
        self.mix_b = bytearray()
        self.mix_c = bytearray()
        self.history = [0] * 2520
        # AEnd() closes FileName, byte_1008E64C, byte_10082310 and
        # byte_1008BAE8 with OpenFile(..., 0x200) - OF_DELETE, i.e. it removes
        # the temp files it may have produced.
        for path in (self.temp_stream, self.temp_wave):
            try:
                os.remove(path)
            except OSError:
                pass
        self.session = Session()
        self.stream_cache = (None, 0, 0)
        return self.status

    # -- RWavToTemp() --------------------------------------------------------

    def RWavToTemp(self, lpString2, a2, a3, a4=None, a5=0,
                   lDistanceToMove=0, a7=0) -> int:
        """0x10020290 - see RWavToTemp.md.

        lpString2       input file name (ignored when a4 is given)
        a2              output file name, used when a3 <= 0
        a3              > 0: render sound #a3; <= 0: convert lpString2
        a4              open handle to cache a slice of a stream from
        a5              offset of that slice
        lDistanceToMove length of that slice
        a7              != 0: append the de-click tail and block padding
        Returns 0 on success, 1 on failure.
        """
        if not self.started:                       # dword_10096CC8 == 0
            return 0
        if lpString2 is None:
            return 0
        if len(lpString2) == 0 and a4 is None:
            return 0

        self.stream_size = 0                       # dword_10096D9C
        sess = self.session
        header_size = WAV_HEADER_SIZE if self.output_kind == 4 else 0   # v25
        sess.field21 = 0
        sess.volume = 0x10000
        sess.pan = 512

        # -- where does the audio come from? --------------------------------
        if a4 is None:
            source = lpString2
        else:
            if self.stream_cache != (a4, a5, lDistanceToMove):
                if self._materialise_stream(a4, a5, lDistanceToMove) != 0:
                    return 1
            source = self.temp_stream

        # -- how long is it? (frames of 16 bit, i.e. bytes / 2) --------------
        v14 = _idiv(awave_dauer(source), 2)        # may be negative

        try:
            with open(source, "rb") as fh:
                fsize = os.fstat(fh.fileno()).st_size
                head = fh.read(DECODE_TAIL)
        except OSError:
            self.stream_size = 0
            return 1

        self.stream_size = fsize
        sess.header = head
        sess.vol_word = 0
        sess.block_size = DECODE_BLOCK
        sess.write_offset = 0
        sess.read_offset = 0
        sess.remaining = fsize
        sess.subtype = 0
        sess.stream_end = fsize
        self._parse_header(sess)                   # sub_10019DEE
        sess.length = sess.stream_end - sess.read_offset

        # -- the source is mapped read-only for the decoder -----------------
        try:
            with open(source, "rb") as fh:
                sess.src = fh.read()
        except OSError:
            return 1

        # -- destination name and preallocation -----------------------------
        if a3 <= 0:
            out_name = a2
        else:
            out_name = "%spxd32p%c.tmp" % (self.path_name,
                                           chr((a3 + 99) & 0xFF))
            if v14 > 2 * BUFFER_SAMPLES:
                v14 = 2 * BUFFER_SAMPLES
            idx = 65 * a3 - 65
            sess.volume = 2 * self._table(self.sound_volume, idx)
            sess.pan = 256

        if a3 <= 0:
            file_size = v14 + DECODE_BLOCK + header_size + 64
        else:
            file_size = 4 * BUFFER_SAMPLES + 64
        file_size += DECODER_SLACK
        file_size = max(file_size, 0)

        out = bytearray(file_size)                 # the mapped destination
        sess.src_base = 0
        sess.out_ptr = header_size
        sess.region = (v14 + DECODE_BLOCK + 64 if a3 <= 0
                       else 4 * BUFFER_SAMPLES + 64)

        # -- render ----------------------------------------------------------
        if self.stream_size > 0:
            if a3 <= 0:
                v14 = self._convert_stream(sess, out, v14, header_size)
            else:
                v14 = self._render_sound(sess, out, a3, header_size)
        else:
            v14 = 0

        # -- de-click tail and block padding (a7 only) -----------------------
        if v14 > 0 and a7 > 0:
            v14 = self._append_tail(out, header_size, v14)

        # -- finish the file --------------------------------------------------
        if v14 > 0:
            if header_size > 0:
                self._write_riff_header(out, sess, v14, header_size)
            final = header_size + v14
        else:
            final = file_size                      # left at its preallocated size

        try:
            with open(out_name, "wb") as fh:
                fh.write(out)
                fh.truncate(final)
        except OSError:
            return 1
        return 0

    # -- RWavToTemp internals -------------------------------------------------

    @staticmethod
    def _table(tbl: list[int], idx: int) -> int:
        return tbl[idx] if 0 <= idx < len(tbl) else 0

    def _materialise_stream(self, a4, a5: int, length: int) -> int:
        """Copy ``length`` bytes at ``a5`` of ``a4`` into the temp file."""
        try:
            if hasattr(a4, "seek") and hasattr(a4, "read"):
                a4.seek(a5)
                data = a4.read(length)
            else:
                pos = os.lseek(a4, a5, os.SEEK_SET)
                chunks = []
                left = length
                while left > 0:
                    chunk = os.read(a4, left)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    left -= len(chunk)
                data = b"".join(chunks)
            with open(self.temp_stream, "wb") as fh:
                fh.truncate(length)         # SetFilePointer + SetEndOfFile
                fh.seek(0)
                fh.write(data)
        except OSError:
            self.stream_cache = (None, 0, 0)
            return 1
        self.stream_cache = (None, 0, 0)
        if len(data) != length:            # NumberOfBytesRead != lDistanceToMove
            return 1
        self.stream_cache = (a4, a5, length)
        return 0

    def _parse_header(self, sess: Session) -> None:
        """sub_10019DEE - classify the stream from its first 220 bytes."""
        h = sess.header
        sess.stream_type = 2                       # "unknown"
        # The original reads 270 bytes into a 220-byte buffer (a real overrun);
        # here the truncated read is treated as "not enough header".
        if len(h) < 44 or sess.stream_end <= 0:
            return

        if _u16(h, 0) == 0x5074:                   # 't','P'
            sess.stream_type = 1
            p = 4
            p += h[p]
            p += 2
            p += 4
            p += 2
            sess.read_offset = min(p, len(h))
            return

        if _u16(h, 0) != 0x4952:                   # 'R','I'
            return

        sess.stream_type = 0
        sess.has_riff = True
        v11 = struct.unpack_from("<i", h, 4)[0]
        end = sess.stream_end
        if (_idiv(v11, 9) + v11 > end and v11 > _idiv(end, 4)
                and v11 - _idiv(v11, 9) < end):
            end = v11

        w = _u16(h, 16)                            # fmt chunk size
        if w < 16:
            w = 16
        if w > 64:
            w = 16
        v7 = (w + 28) & 0xFFFF                     # data offset
        v8 = (w + 20) & 0xFFFF                     # where to scan for "data"
        while v8 < (w + 100) & 0xFFFF and v8 + 4 <= len(h):
            if _u16(h, v8) == 24932 and _u16(h, v8 + 2) == 24948:   # "data"
                v7 = (v8 + 8) & 0xFFFF
                v11 = struct.unpack_from("<i", h, (v8 + 4) & 0xFFFF)[0]
                if (3 * v11 > end and v11 > 1000 and v11 + 9000 > end
                        and v11 < end):
                    end = v11
                    end += v7
                break
            v8 += 2

        if sess.stream_end > end:
            sess.data_offset = end
            sess.stream_end = end

        if _u16(h, 22) == 2:                       # nChannels
            sess.stream_type |= 0x20
        if _u16(h, 34) == 8:                       # wBitsPerSample
            sess.stream_type |= 0x10
        rate = _u16(h, 24)                         # nSamplesPerSec
        if rate == 11025:
            sess.stream_type |= 0x08
        elif rate == 22050:
            sess.stream_type |= 0x04
        else:
            sess.stream_type |= 0x02

        sess.read_offset = v7
        sess.data_offset = v7

    def _convert_stream(self, sess: Session, out: bytearray, v14: int,
                        header_size: int) -> int:
        """The ``a3 <= 0`` loop: decode to stereo 16 bit, keep the left
        channel, repeat until the input or the destination is exhausted."""
        max_frames = sess.block_size // 4            # 75632 bytes -> 18908
        while True:
            base = header_size + sess.write_offset
            # memset(lpBuffer + v25 + v34[14], 0, 0x127B0)
            stop = min(base + SCRATCH_CLEAR, len(out))
            out[base:stop] = bytes(stop - base)
            sess.produced = 0
            self._decode_block(sess, out, base, max_frames)
            j = sess.produced // 4
            # for (i...) *v22 = *v18, v22 += 2, v18 += 4  -> left channel only
            _compact_left_channel(out, base, j)
            sess.write_offset += 2 * j
            if not (j != 0 and sess.write_offset < v14
                    and sess.read_offset < sess.stream_end):
                break
        return v14

    def _render_sound(self, sess: Session, out: bytearray, a3: int,
                      header_size: int) -> int:
        """The ``a3 > 0`` path: render one numbered sound and resample it."""
        idx = 65 * a3 - 65
        sess.block_size = 4 * BUFFER_SAMPLES
        sess.out_ptr = 0
        self.mix_a[:] = bytes(len(self.mix_a))
        sess.produced = 0
        self._decode_block(sess, self.mix_a, 0, BUFFER_SAMPLES)
        frames = sess.produced // 4

        pitch = self._table(self.sound_pitch, idx)
        step = self._pitch_step(pitch)
        count = frames << 14
        if step != 0:
            count = _idiv(count, step)
        if count > BUFFER_SAMPLES:
            count = BUFFER_SAMPLES

        # linear interpolation with 14 fraction bits (sub_10021272's inputs)
        reversed_flag = self._table(self.sound_loop, idx) != 0
        frac = 0
        dst = self.mix_c
        # NOTE: in the DLL v18 is an __int16*, so "v18 += 2 * (v26 >> 14)"
        # moves two *samples* = four bytes = one stereo frame.
        if reversed_flag:
            src_pos = 4 * (frames - 1)
            for i in range(count):
                frac &= 0x3FFF
                cur = _s16(self.mix_a, src_pos)
                prev = _s16(self.mix_a, src_pos - 4)
                _put16(dst, 2 * i, ((0x3FFF - frac) * cur + frac * prev) >> 14)
                frac += step
                src_pos -= 4 * (frac >> 14)
        else:
            src_pos = 0
            for i in range(count):
                frac &= 0x3FFF
                cur = _s16(self.mix_a, src_pos)
                nxt = _s16(self.mix_a, src_pos + 4)
                _put16(dst, 2 * i, ((0x3FFF - frac) * cur + frac * nxt) >> 14)
                frac += step
                src_pos += 4 * (frac >> 14)

        self._update_effect_params()
        tail = self.fx["dword_10082FE0"]
        if tail > 0 and self.fx["dword_10083540"] != 0:
            j = count
            count = count + tail + self.fx_params[3]     # dword_10090764
            if count > BUFFER_SAMPLES:
                count = BUFFER_SAMPLES
            dst[2 * j:2 * count + 40] = bytes(2 * (count - j) + 40)

        v14 = 2 * count
        # reset of the mixer state that sub_1000E3E0() expects
        self.mix_b[:] = bytes(len(self.mix_b))
        self.history = [0] * 2520
        self.history_pos = 0
        for name in ("dword_10096D94", "dword_10082660", "dword_100836E4",
                     "dword_10082684", "dword_100836F4", "dword_100836F8",
                     "dword_100836FC", "dword_10083704", "dword_1008B714",
                     "dword_1008B720", "dword_1008B734", "dword_1008B744"):
            setattr(self, name, 0)
        self.dword_10082694 = 512                      # memset(0x200) default

        # sub_1000E3E0(lpBuffer, lpBuffer + 2 * v21, 0, dword_1008BBEC)
        self._effects_chain(out, header_size, dst, v14)
        return v14

    def _decode_block(self, sess: Session, out, base: int,
                      max_frames: int) -> int:
        """Fill ``out[base:]`` with stereo 16-bit frames, update ``sess``.

        Mirrors what sub_100149E0() does around the actual decoder: it sets the
        source window, calls the decoder and stores back the new read position.
        """
        # sub_100149E0() publishes this gain right before calling the decoder.
        sess.gain = (sess.pan * sess.volume) >> 8
        hook = self.decode_hook or self._decode_default
        produced = hook(sess, out, base, max_frames)
        sess.produced = produced
        return produced

    def _decode_default(self, sess: Session, out, base: int,
                        max_frames: int) -> int:
        if sess.has_riff:
            return self._decode_pcm(sess, out, base, max_frames)
        if sess.stream_type == 1:
            return self._decode_tp(sess, out, base, max_frames)
        raise UnsupportedCodec("unknown stream format (type %d)"
                               % (sess.stream_type & 0x0F))

    def _decode_tp(self, sess: Session, out, base: int,
                   max_frames: int) -> int:
        """sub_10016361 - the "tP" DPCM/codebook decoder.

        Byte code:
          ``0x00..0xF3``  play code-book entry ``byte`` (delays until 0xFFFF)
          ``0xFF``        one step from the shared delta table
          ``0xF4..0xFE``  (re)define entry: ``[index]`` + ``opcode-0xF3`` bytes,
                          each a delta-table index, then play that entry
        Entry ``n`` lives at ``book + 16*n`` and holds int16 deltas terminated
        by 0xFFFF; the deltas are integrated into a 16-bit accumulator that is
        scaled by the gain and *added* to the (memset-zeroed) destination.
        """
        book = sess.book if sess.book is not None else bytearray(BOOK_SIZE)
        sess.book = book
        table = DELTA_TABLE
        src = sess.src
        pos = sess.read_offset
        end = min(sess.stream_end, len(src))
        acc = sess.vol_word                 # 16-bit integrator, kept in a1[4]
        gain = sess.gain
        hard = max_frames + 64              # safety net, well past one entry
        frames = 0
        off = base
        if sess.chan_mode & 0xFFFF:         # word_10082658: repeat last sample
            emit(out, off, acc, gain)
            off += 4
            frames += 1
            sess.chan_mode &= ~0xFFFF

        while frames < max_frames and pos < end:
            c = src[pos]
            if c >= 0xF4:
                if c != 0xFF:
                    pos += 1
                    idx = src[pos]
                    count = c - 0xF3            # (char)(opcode + 13)
                    e = (16 * idx) & 0xFFFF
                    pos += 1
                    for k in range(count):
                        _put16(book, (e + 2 * k) & 0xFFFF, table[src[pos]])
                        pos += 1
                    _put16(book, (e + 2 * count) & 0xFFFF, 0xFFFF)
                else:
                    pos += 1
                    acc = _wrap16(acc + table[src[pos]])
                    pos += 1
                    emit(out, off, acc, gain)
                    off += 4
                    frames += 1
                    continue
            else:
                e = (16 * c) & 0xFFFF
                pos += 1

            # play one book entry; the DLL only re-checks the bounds when the
            # entry is finished, so an entry is never cut in half.
            while True:
                d = _s16(book, e & 0xFFFF)
                if d == -1:
                    break
                acc = _wrap16(acc + d)
                emit(out, off, acc, gain)
                off += 4
                frames += 1
                e += 2
                if frames >= hard:
                    break
                d = _s16(book, e & 0xFFFF)
                if d == -1:
                    break
                acc = _wrap16(acc + d)
                emit(out, off, acc, gain)
                off += 4
                frames += 1
                e += 2
                if frames >= hard:
                    break
            if frames >= hard:
                break

        sess.vol_word = acc
        sess.read_offset = pos
        return 4 * frames

    def _decode_pcm(self, sess: Session, out, base: int,
                    max_frames: int) -> int:
        """RIFF/WAVE PCM: 8 or 16 bit, mono or stereo, 11025/22050/44100 Hz."""
        flags = sess.stream_type
        stereo = bool(flags & 0x20)
        eight_bit = bool(flags & 0x10)
        rate = 11025 if flags & 0x08 else 22050 if flags & 0x04 else 44100
        mult = 44100 // rate                     # 4, 2 or 1

        frame_bytes = (1 if not stereo else 2) if eight_bit else \
                      (2 if not stereo else 4)
        src = sess.src
        pos = sess.read_offset
        end = min(sess.stream_end, len(src))
        frames_written = 0
        samples = array.array("h")

        while pos + frame_bytes <= end and frames_written < max_frames:
            room = (max_frames - frames_written) // mult
            if room <= 0:
                break
            n = min(room, (end - pos) // frame_bytes)
            if n <= 0:
                break
            chunk = src[pos:pos + n * frame_bytes]
            pos += n * frame_bytes
            if eight_bit:
                raw = array.array("B")
                raw.frombytes(chunk)
                vals = [(b - 128) << 8 for b in raw[0::(2 if stereo else 1)]]
                del raw
            else:
                a16 = array.array("h")
                a16.frombytes(chunk)
                if sys.byteorder == "big":
                    a16.byteswap()
                vals = a16[0::(2 if stereo else 1)]
            if mult == 1:
                for v in vals:
                    samples.append(v)
                    samples.append(v)
            else:
                for v in vals:
                    for _ in range(mult):
                        samples.append(v)
                        samples.append(v)
            frames_written = len(samples) // 2

        if samples and sys.byteorder == "big":
            samples.byteswap()
        blob = samples.tobytes()
        # The destination is a mix buffer, not a scratch area: add the samples
        # (with 16-bit saturation) so a second PCM voice does not overwrite
        # the first.  RWavToTemp zeroes its buffer before every block, so this
        # is identical to an assignment there.
        seg = array.array("h")
        seg.frombytes(bytes(out[base:base + len(blob)]))
        if sys.byteorder == "big":
            seg.byteswap()
        for i in range(len(samples)):
            total = seg[i] + samples[i]
            if total > 0x7FFF:
                total = 0x7FFF
            elif total < -0x8000:
                total = -0x8000
            seg[i] = total
        if sys.byteorder == "big":
            seg.byteswap()
        out[base:base + len(blob)] = seg.tobytes()
        sess.read_offset = pos
        return len(blob)

    def _pitch_step(self, pitch: int) -> int:
        """dword_100668EC[13 - pitch] - playback rate, 0x4000 = unity."""
        idx = 13 - pitch
        if idx < 0:
            idx = 0
        if idx >= len(RATIO_TABLE):
            idx = len(RATIO_TABLE) - 1
        return RATIO_TABLE[idx]

    def _update_effect_params(self) -> int:
        """sub_10021272 - derive the effect coefficients from the parameters."""
        p = self.fx_params + [0] * 8
        f = self.fx

        v7 = (1.0 - p[0] / 32767.0) * 1.3
        v6 = int(v7 * v7 * v7 * 113.7915339098771)
        if v6 > 350:
            v6 = 350
        if v6 < 1:
            v6 = 1
        f["dword_10093A8C"] = v6
        f["dword_100823F0"] = (v6 - 1) // 2 + 0x4000 // v6
        f["dword_1008BAB0"] = 0
        v1 = self.history_pos
        for _ in range(v6):
            v1 = v1 - 1 + (0x5EB if v1 - 1 < 0 else 0)
            f["dword_1008BAB0"] += self.history[v1]

        v8 = ((1.0 - p[1] / 32767.0) * 0.85 + 0.15) * 1.4
        v9 = 1.0 - v8 * v8 * v8 / 2.743999999999999
        if v9 >= 1.0:
            v9 = 0.9999999999
        v12 = -v9 * 0.0499 - 0.95
        f["dword_10082FD0"] = int(v12 * 4096.0)
        v4 = ((1.0 - p[1] / 32767.0) * 0.285 + 0.5) * 1.4
        v5 = 1.0 - v4 * v4 * v4 / 2.743999999999999
        if v5 >= 1.0:
            v5 = 0.9999999999
        f["dword_10082FD4"] = int((1.0 - v12 - (0.11 - v5 * 0.1)) * 4096.0)
        v3 = (1.0 - ((1.0 - p[1] / 32767.0) * 0.285 + 0.5)) * 1.6
        f["dword_10082708"] = int((1.0 - p[1] / 32767.0) * 0.5 * 8192.0)
        f["dword_1008270C"] = int(
            (0x2000 - f["dword_10082708"])
            / ((1.0 - ((1.0 - p[1] / 32767.0) * 0.285 + 0.5)) * 14.0
               + 4.0
               + v3 * v3 * v3 / 4.096000000000001 * 3.0
               + (1.0 - ((1.0 - p[1] / 32767.0) * 0.85 + 0.15)) * 6.0))

        v10 = (BUFFER_SAMPLES // 2) * (p[2] / 32810.0)
        if BUFFER_SAMPLES // 2 <= v10:
            v10 = float(BUFFER_SAMPLES // 2)
        if BUFFER_SAMPLES // 64 > v10:
            v10 = float(BUFFER_SAMPLES // 64)
        f["dword_10082FE0"] = int(v10)
        f["dword_10082FE4"] = int(p[3] / 32767.0 * 988.0)
        f["dword_10082FE8"] = int((p[3] / 32767.0 * 0.5 + 0.35) * 714.0)
        v11 = (1.0 - ((1.0 - p[4] / 32767.0) * 0.4 + 0.6)) * 1.4
        f["dword_10082FEC"] = int(v11 * v11 / 1.96 * 4096.0 * 0.72)
        f["dword_1008353C"] = p[5]
        f["dword_10083540"] = p[6]
        f["dword_10083544"] = p[7]
        f["dword_10083548"] = 0
        f["dword_1008354C"] = 0
        f["dword_10082FDC"] = 0
        return p[7]

    def _effects_chain(self, out: bytearray, header_size: int,
                       src: bytearray, length: int) -> None:
        """sub_1000E3E0 - the echo/chorus/reverb chain.

        Not ported: the routine is ~700 lines of fixed-point arithmetic that
        consumes the coefficient state computed by sub_10021272 and several
        codebook/delay tables from .data.  Until it is ported this is a plain
        copy so that the a3 > 0 path still yields a playable file.
        """
        out[header_size:header_size + length] = src[0:length]

    @staticmethod
    def _append_tail(out: bytearray, header_size: int, v14: int) -> int:
        """sub_10020290 tail: 128-sample de-click ramp, then block padding."""
        end = header_size + v14
        for j in range(128):
            pos = end - 2 * (j + 1)
            if pos < header_size:
                break
            _put16(out, pos, (j * _s16(out, pos)) >> 7)
        blocks = _idiv(v14, 2 * BLOCK_ALIGN) + 1
        if blocks > 16:
            blocks = 16
        target = blocks * 2 * BLOCK_ALIGN
        if header_size + target > len(out):
            out.extend(bytes(header_size + target - len(out)))
        out[end:header_size + target] = bytes(target - v14)
        return target

    @staticmethod
    def _write_riff_header(out: bytearray, sess: Session, data_len: int,
                           header_size: int = WAV_HEADER_SIZE) -> None:
        """sub_10013198 - the 44-byte mono 16-bit/44.1 kHz RIFF header.

        The DLL sets word_100823F8 = 2 right before calling it, which selects
        mono (channels = 1, block align 2, 88200 bytes/s); with
        word_100823F8 >= 2 the "stereo" variant would use 2 channels.
        """
        if header_size < WAV_HEADER_SIZE:
            return
        channels = 1
        rate = 44100
        align = 2
        bits = 16
        body = data_len + 36
        out[0:4] = b"RIFF"
        _put32(out, 4, body)
        out[8:12] = b"WAVE"
        out[12:16] = b"fmt "
        _put32(out, 16, 16)
        _put16(out, 20, 1)                     # WAVE_FORMAT_PCM
        _put16(out, 22, channels)
        _put32(out, 24, rate)
        _put32(out, 28, rate * channels * align)
        _put16(out, 32, align)
        _put16(out, 34, bits)
        out[36:40] = b"data"
        _put32(out, 40, data_len)


def _wrap16(v: int) -> int:
    """int16 wrap-around (the DLL's DPCM integrator lives in a 16-bit reg)."""
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def emit(buf, off: int, acc: int, gain: int) -> None:
    """One decoder step: out[off] += (acc * gain) >> 16, with saturation.

    The ``add word [esi], ax`` overflow handler in the DLL picks the clamp from
    the sign of the *wrapped* sum, so a positive overflow becomes 0x8000 - a
    quirk of the original that is reproduced here.
    """
    prod = acc * gain
    if prod > 0x7FFFFFFF or prod < -0x80000000:
        sample = 0x7FFF if prod > 0 else 0x8000
    else:
        sample = (prod >> 16) & 0xFFFF
    cur = _u16(buf, off)
    a = cur - 0x10000 if cur & 0x8000 else cur
    b = sample - 0x10000 if sample & 0x8000 else sample
    total = a + b
    if -0x8000 <= total <= 0x7FFF:
        _put16(buf, off, total)
    else:
        _put16(buf, off, 0x8000 if total & 0x8000 else 0x7FFF)


def _compact_left_channel(buf: bytearray, base: int, frames: int) -> None:
    """``for (i) *v22 = *v18; v22 += 2; v18 += 4`` - keep every other sample."""
    if frames <= 0:
        return
    a = array.array("h")
    a.frombytes(bytes(buf[base:base + 4 * frames]))
    if sys.byteorder == "big":
        a.byteswap()
    mono = a[0::2]
    if sys.byteorder == "big":
        mono.byteswap()
    buf[base:base + 2 * frames] = mono.tobytes()


# ---------------------------------------------------------------------------
# the exported API (one process-wide engine, like the DLL)
# ---------------------------------------------------------------------------

engine = Engine()


def PInit(a1: float = 1.0) -> int:
    """0x10022318 - initialise the sound engine.

        ADevice(0);
        AInit(a1, 0);
        RWaveParam(60, 32000);
        return 0;
    """
    engine.ADevice(0)
    engine.AInit(a1, 0)
    engine.RWaveParam(60, 32000)
    return 0


def PClose() -> int:
    """0x10022339 - stop playback and release everything.

        AStop();
        AEnd();
        return 0;
    """
    engine.AStop()
    engine.AEnd()
    return 0


def PStart() -> int:
    """0x1002234A - start the player.

        AStart(176223600);
        RWaveParam(50, 1);
        return 0;

    This is what makes ``PPlay`` audible: ``AStart`` sets
    ``dword_10096D88 = 2`` and the player thread / ``pump`` loop then drains
    the request queue and feeds the sink.
    """
    engine.AStart(176223600)
    engine.RWaveParam(50, 1)
    return 0


def RWavePause1() -> int:
    """0x100184E9 - pause all playing streams."""
    return engine.RWavePause1()


def RWavePause2() -> int:
    """0x1001858C - resume all paused streams."""
    return engine.RWavePause2()


def RWaveStop() -> int:
    """0x10017BC8 - stop playback and release the stream state."""
    return engine.RWaveStop()


def RWaveLaden(lpString2, a2: int = 123, a3=None, a4: int = 0,
               lDistanceToMove: int = 0) -> int:
    """0x1001A152 - convert + map a wave for the host player."""
    return engine.RWaveLaden(lpString2, a2, a3, a4, lDistanceToMove)


def APlay(a1: int, a2: int, a3: int, a4: int, a5: int, a6: int, lpString2,
          a8: int, a9: int, a10: int, a11: int, a12: int) -> int:
    """0x1001775B - queue a play request (see ``Engine.APlay``)."""
    return engine.APlay(a1, a2, a3, a4, a5, a6, lpString2,
                        a8, a9, a10, a11, a12)


def PPlay(lpString2, a2: int, a3: int, a4: int, a5: int, a6: int) -> int:
    """0x10022370 - queue "play file ``lpString2``" on voice ``a2``.

        APlay(0, 0, 0, 0, 0, (int)&unk_1004B304, lpString2, a2, a3, a4,
              a5, a6);
        return 0;

    This only queues the request (see ``Engine.APlay``).  ``PStart`` must run
    first and ``a5`` (the ring end position) must be greater than ``a3``; a
    request queued while playing should use ``engine.play_position()`` as
    ``a3`` and ``a3 + length`` as ``a5``.
    """
    engine.APlay(0, 0, 0, 0, 0, PLAY_MODE_FILE, lpString2,
                 a2, a3, a4, a5, a6)
    return 0


def RWavToTemp(lpString2, a2, a3, a4=None, a5: int = 0,
               lDistanceToMove: int = 0, a7: int = 0) -> int:
    """0x10020290 - see the module docstring / RWavToTemp.md."""
    return engine.RWavToTemp(lpString2, a2, a3, a4, a5, lDistanceToMove, a7)
