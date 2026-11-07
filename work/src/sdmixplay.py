"""Play a Rave eJay ``.MIX`` arrangement straight through sounddevice.

    python src/sdmixplay.py TRANCE.MIX --res C:/eJay/disk/RAVE
    python src/sdmixplay.py TRANCE.MIX --list        # print the arrangement

Independent of ``mixplay.py`` and of the ported engine: this module parses the
grid, the sample index and the sample codecs itself, mixes the arrangement in
Python and hands the result to a PortAudio stream
(``sounddevice.RawOutputStream``).  Nothing here imports ``pxd32d5`` or
``pxdsink``, so the engine's play ring, player thread and command queue are
not involved at all.

Formats are documented in ``docs/MIX_FORMAT.md`` (grid, index, record length)
and ``docs/PXD_FORMAT.md`` (``tPxd``); RIFF/WAVE samples are decoded too.
Everything at 44.1 kHz, 16-bit mono - the engine's left channel duplicated to
the right in its ring is silence as far as one speaker is concerned.

A grid record is not a bar but **two** bars: 117 600 frames (2.667 s) at
44.1 kHz.  Nothing in the file says so; it comes from the arrangement, which
places every sample so that it ends exactly when the next one on its track
starts only at that length (``docs/MIX_FORMAT.md`` section 2).  ``--step``
overrides it, ``--bpm``/``--beats`` derive it.
"""

from __future__ import annotations

import argparse
import array
import os
import struct
import sys

MIX_MAGIC = 0x0A07              # header word of every .MIX seen
MIX_TRAILER = 0x0A08            # trailer tag, one higher than the header
RECORD_WORDS = 16               # 8 A cells + 8 B cells
RECORD_BYTES = 32               # 16 words
GRID_OFFSET = 2                 # the grid starts after the header word
TRACKS = 8
ID_OFFSET = 731                 # sample_id - 731 = index record
MIN_SAMPLE_ID = ID_OFFSET       # lower values are padding, not samples

DEFAULT_BPM = 180.0
DEFAULT_BEATS = 8.0             # beats per record (two 4/4 bars)
SAMPLE_RATE = 44100
BAR_FRAMES = 58800              # one bar: the length in every bank PXD comment
RECORD_FRAMES = 2 * BAR_FRAMES  # one grid record = 117 600 frames, 2.667 s
BLOCK_FRAMES = 2048             # mix/write granularity, ~46 ms

BOOK_SIZE = 8100                # sub_1001186B allocates malloc(0x1FA4)
BOOK_SILENCE = (0, 0, 0, 0, 0, -1)   # entry 0, written by sub_10011EFF

__all__ = [
    "MixError",
    "MixFile",
    "MixEvent",
    "SampleEntry",
    "Mixer",
    "read_mix",
    "read_index",
    "sample_for",
    "resolve_sample",
    "find_index",
    "build_events",
    "step_seconds",
    "decode_sample",
    "decode_sample_bytes",
    "open_stream",
    "play",
    "main",
    "BAR_FRAMES",
    "RECORD_FRAMES",
]


class MixError(ValueError):
    """The file is not a readable arrangement/sample, or a value is bad."""


# ---------------------------------------------------------------------------
# C semantics the decoders need
# ---------------------------------------------------------------------------


def _wrap16(value: int) -> int:
    """``short`` wraparound (the DPCM integrator lives in 16 bits)."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _s16(buf, off: int) -> int:
    return struct.unpack_from("<h", buf, off)[0]


def _put16(buf, off: int, value: int) -> None:
    struct.pack_into("<H", buf, off, value & 0xFFFF)


# ---------------------------------------------------------------------------
# the arrangement file
# ---------------------------------------------------------------------------


class MixFile:
    """A parsed ``.MIX``: 16-word grid records plus the trailer version."""

    def __init__(self, path, header, records, version=""):
        self.path = path
        self.header = header
        self.records = records
        self.version = version

    def used_records(self) -> int:
        """One past the last record that holds a sample.

        The unused tail of the grid is not reliably zero
        (``docs/MIX_FORMAT.md`` section 7), so only values the index can
        resolve count as content.
        """
        for i in range(len(self.records) - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self.records[i]):
                return i + 1
        return 0

    def cells(self):
        """Yield ``(record, lane, track, sample_id)`` for every sample cell."""
        for record, row in enumerate(self.records):
            for column, sample_id in enumerate(row):
                if sample_id < MIN_SAMPLE_ID:
                    continue
                lane = "A" if column < TRACKS else "B"
                yield record, lane, column % TRACKS + 1, sample_id


def read_mix(path: str) -> MixFile:
    """Parse ``path``; raises ``MixError`` for anything that is not a mix.

    The trailer is located the way ``docs/MIX_FORMAT.md`` section 9 does it:
    the first 32-byte-aligned ``0x0A08`` after the header word.  A truncated
    file without the trailer yields as many whole records as it holds.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < GRID_OFFSET + RECORD_BYTES:
        raise MixError("file is too short for an arrangement")
    header = struct.unpack_from("<H", data, 0)[0]
    if header != MIX_MAGIC:
        raise MixError("not a Rave eJay .mix (header 0x%04X)" % header)

    tag = data.find(b"\x08\x0a", GRID_OFFSET)     # 0x0A08 little-endian
    while tag != -1 and (tag - GRID_OFFSET) % RECORD_BYTES:
        tag = data.find(b"\x08\x0a", tag + 1)
    if tag != -1:
        count = (tag - GRID_OFFSET) // RECORD_BYTES
    else:
        count = (len(data) - GRID_OFFSET) // RECORD_BYTES
    if count <= 0:
        raise MixError("the arrangement grid is empty")

    records = [
        struct.unpack_from("<%dH" % RECORD_WORDS, data,
                           GRID_OFFSET + RECORD_BYTES * i)
        for i in range(count)
    ]
    version = ""
    if tag != -1 and tag + 6 <= len(data):
        size = struct.unpack_from("<H", data, tag + 4)[0]
        raw = data[tag + 6:tag + 6 + size]
        version = raw.split(b"\0")[0].decode("latin-1", "replace").strip()
    return MixFile(path, header, records, version)


# ---------------------------------------------------------------------------
# the sample index (``disk/RAVE/EJAY/PXD``)
# ---------------------------------------------------------------------------


class SampleEntry:
    """One six-line record of the eJay sample list."""

    def __init__(self, path, category="", number="", name=""):
        self.path = path                # "bq\\r1bs001.pxd", relative to disk/RAVE
        self.category = category
        self.number = number
        self.name = name


def read_index(path: str):
    """Read the quoted, CRLF, six-lines-per-record sample list."""
    with open(path, "rb") as fh:
        text = fh.read().decode("latin-1")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    entries = []
    for i in range(0, len(lines) - 5, 6):
        fields = [x.strip().strip('"') for x in lines[i:i + 6]]
        if not fields[0]:
            continue
        name = " ".join(x for x in fields[4:] if x)
        entries.append(SampleEntry(fields[0], fields[2], fields[3], name))
    return entries


def sample_for(sample_id: int, index):
    """``sample_id - ID_OFFSET`` (docs/MIX_FORMAT.md section 3)."""
    pos = sample_id - ID_OFFSET
    if 0 <= pos < len(index):
        return index[pos]
    return None


def find_index(mix_path: str):
    """Look for ``EJAY/PXD`` next to the mix, one/two levels up, or in cwd."""
    here = os.path.dirname(os.path.abspath(mix_path))
    candidates = [
        here,
        os.path.join(here, "disk", "RAVE"),
        os.path.dirname(here),
        os.path.dirname(os.path.dirname(here)),
        os.getcwd(),
        os.path.join(os.getcwd(), "disk", "RAVE"),
    ]
    for base in candidates:
        path = os.path.join(base, "EJAY", "PXD")
        if os.path.isfile(path):
            return path
    return None


def resolve_sample(res_root: str, relative: str):
    """Resolve an index path under ``res_root``, ignoring letter case."""
    path = res_root
    for part in relative.replace("\\", "/").split("/"):
        if not part:
            continue
        try:
            names = os.listdir(path)
        except OSError:
            return None
        match = part if part in names else None
        if match is None:
            for name in names:
                if name.lower() == part.lower():
                    match = name
                    break
        if match is None:
            return None
        path = os.path.join(path, match)
    return path if os.path.isfile(path) else None


# ---------------------------------------------------------------------------
# events: runs of one sample ID on one track
# ---------------------------------------------------------------------------


class MixEvent:
    """One sounding: ``span`` records of ``sample_id`` on one track/lane."""

    def __init__(self, record, span, track, lane, sample_id):
        self.record = record
        self.span = span
        self.track = track
        self.lane = lane
        self.sample_id = sample_id

    @property
    def end_record(self):
        return self.record + self.span


def build_events(mix: MixFile):
    """Collapse repeated IDs into one event per continuous run.

    ``docs/MIX_FORMAT.md`` section 2: a sample covering several steps is the
    same ID repeated in each of them, so a run is one sounding, not one hit
    per record.
    """
    events = []
    for column in range(RECORD_WORDS):
        lane = "A" if column < TRACKS else "B"
        track = column % TRACKS + 1
        current = 0
        first = 0
        for record, row in enumerate(mix.records):
            sample_id = row[column]
            if sample_id < MIN_SAMPLE_ID:
                sample_id = 0       # stray padding, not a cell (section 7)
            if sample_id == current:
                continue
            if current:
                events.append(MixEvent(first, record - first, track, lane,
                                       current))
            current = sample_id
            first = record
        if current:
            events.append(MixEvent(first, len(mix.records) - first, track,
                                   lane, current))
    events.sort(key=lambda e: (e.record, e.track, e.lane))
    return events


# ---------------------------------------------------------------------------
# timing
# ---------------------------------------------------------------------------


def step_seconds(args) -> float:
    """Seconds per record: ``--step`` wins, else ``--bpm`` at ``--beats``."""
    if getattr(args, "step", None):
        return float(args.step)
    return 60.0 / float(args.bpm) * float(args.beats)


def event_frames(event: MixEvent, step: float, rate: int = SAMPLE_RATE):
    """``(start, end)`` sample positions of ``event``."""
    start = int(round(event.record * step * rate))
    end = int(round(event.end_record * step * rate))
    if end <= start:
        end = start + 1
    return start, end


# ---------------------------------------------------------------------------
# sample decoding (standalone: tPxd and RIFF/WAVE PCM)
# ---------------------------------------------------------------------------


def _delta_table():
    """``sub_10011EFF``'s 256-entry delta book (``dword_1008E350``).

    A symmetric, roughly logarithmic ladder of DPCM step sizes, built by
    accumulating an exponentially growing increment and mirroring the
    positive half around index 128 (which is 0); doubled, then stored as
    int16.
    """
    v1, v20 = 2.2, 1.0565
    t = [0] * 257
    for j in range(1, 128):
        if j >= 6:
            t[j + 128] = int(v1 - 0.52) + t[j + 127]
        else:
            t[j + 128] = t[j + 127] + 1
        v1 *= v20
        v20 -= 0.00022
    for k in range(1, 129):
        t[128 - k] = -t[k + 128]
    out = []
    for m in range(256):
        v = (t[m] * 2) & 0xFFFF
        out.append(v - 0x10000 if v & 0x8000 else v)
    return out


DELTA_TABLE = _delta_table()


def _decode_tp(data: bytes) -> array.array:
    """``sub_10016361`` - the ``tPxd`` DPCM/code-book decoder.

    At gain 0x10000 the decoder's ``(acc * gain) >> 16`` is ``acc``, so the
    decoded samples are the 16-bit integrator itself; gain is applied by the
    mixer instead.  Exactly the frame count in the header is produced.
    """
    if len(data) < 8:
        raise MixError("tPxd header is truncated")
    comment = data[4]
    offset = 4 + comment + 8
    if comment + 10 > len(data) or offset > len(data):
        raise MixError("tPxd header is truncated")
    frames = struct.unpack_from("<i", data, comment + 6)[0]
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
                acc = _wrap16(acc + table[data[pos + 1]])
                pos += 2
                out.append(acc)
                continue
            if pos + 2 > end:
                break
            idx = data[pos + 1]
            count = code - 0xF3            # (char)(opcode + 13), see notes
            pos += 2
            if pos + count > end:
                break
            base = 16 * idx
            for k in range(count):
                _put16(book, base + 2 * k, table[data[pos + k]])
            _put16(book, base + 2 * count, 0xFFFF)
            pos += count
            entry = base
        else:
            pos += 1
            entry = 16 * code

        # play the entry; an entry is never cut in half by the block bound
        while len(out) < frames:
            delta = _s16(book, entry)
            if delta == -1:
                break
            acc = _wrap16(acc + delta)
            out.append(acc)
            entry += 2

    # RWavToTemp truncates its file to the declared length, so a bytecode that
    # ends early is heard as silence, not as a shorter sample.
    if len(out) < frames:
        out.extend(array.array("h", bytes(2 * (frames - len(out)))))
    return out


def _decode_riff(data: bytes) -> array.array:
    """RIFF/WAVE PCM: 8/16 bit, mono/stereo, any rate (nearest resample).

    The mix engine keeps the left channel of a stereo stream and repeats
    each sample to reach 44.1 kHz, which is what this does as well.
    """
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise MixError("not a RIFF/WAVE stream")
    pos = 12
    fmt = None
    payload = None
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8:pos + 8 + size]
        if tag == b"fmt ":
            fmt = body
        elif tag == b"data":
            payload = body
            break
        pos += 8 + size + (size & 1)
    if fmt is None or len(fmt) < 16:
        raise MixError("RIFF stream has no fmt chunk")
    if payload is None:
        raise MixError("RIFF stream has no data chunk")
    tag, channels, rate = struct.unpack_from("<HHI", fmt, 0)
    bits = struct.unpack_from("<H", fmt, 14)[0]
    if tag != 1:
        raise MixError("compressed WAV (format %d) is not supported" % tag)
    if channels not in (1, 2):
        raise MixError("unsupported channel count %d" % channels)
    if bits not in (8, 16):
        raise MixError("unsupported sample size %d" % bits)
    if rate <= 0:
        raise MixError("bad sample rate %d" % rate)

    if bits == 8:
        mono = [(b - 128) << 8 for b in payload[0::channels]]
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
    return array.array("h", [mono[min(int(i * step), last)]
                             for i in range(count)])


def decode_sample_bytes(data: bytes) -> array.array:
    """Decode a sample stream (``tPxd`` or RIFF/WAVE) to mono int16 at 44.1 kHz."""
    if data[0:2] == b"tP":
        return _decode_tp(data)
    if data[0:4] == b"RIFF":
        return _decode_riff(data)
    raise MixError("unknown sample format")


def decode_sample(path: str) -> array.array:
    """Decode the sample file ``path`` to mono int16 at 44.1 kHz."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise MixError("%s: %s" % (path, exc)) from exc
    try:
        return decode_sample_bytes(data)
    except MixError as exc:
        raise MixError("%s: %s" % (path, exc)) from exc


# ---------------------------------------------------------------------------
# the mixer
# ---------------------------------------------------------------------------


class Mixer:
    """Adds the arrangement's samples into successive blocks of mono PCM.

    ``mix`` must be called with increasing, contiguous ranges.  A run longer
    than its sample repeats it to fill the run: every sample in the real bank
    is a whole number of bars long (half a record), and a one-bar bass placed
    over 30 records is that bar repeated 30 times.  A run shorter than its
    sample still plays the whole sample - mid-song samples are never cut.  The
    one structural stop is the arrangement's final record: earlier samples stop
    when it begins, while placements in that record are the ending and ring out
    past it.  A sample shorter than one record is a one-shot: it plays once and
    leaves the rest of its run silent.
    """

    def __init__(self, events, samples, step, gain=1.0,
                 rate=SAMPLE_RATE, on_start=None):
        self.rate = rate
        self.gain = float(gain)
        self.samples = samples
        self.on_start = on_start
        self.spans = []
        record_frames = int(round(step * rate))
        positions = []
        for event in events:
            pcm = samples.get(event.sample_id)
            if not pcm:
                continue
            start, end = event_frames(event, step, rate)
            positions.append((start, end, event, len(pcm)))
        positions.sort(key=lambda span: span[0])

        last_end = max(end for _, end, _, _ in positions) if positions else 0
        final_start = (min(start for start, end, _, _ in positions
                           if end == last_end) if positions else 0)

        total = 0
        for start, end, event, length in positions:
            loop = end - start > length and length >= record_frames
            if loop:
                audio_end = end
            else:
                natural = start + length
                if end >= last_end:
                    audio_end = natural
                else:
                    audio_end = min(natural, final_start)
            self.spans.append((start, audio_end, event, loop))
            # the run keeps the mix going even when a one-shot ends early
            if audio_end > total:
                total = audio_end
            if end > total:
                total = end
        self.total = total
        self._next = 0
        self._active = []

    def mix(self, start: int, count: int) -> array.array:
        """Return ``count`` frames starting at ``start`` (int16, mono)."""
        out = array.array("h", bytes(2 * count))
        end = start + count
        while self._next < len(self.spans) and self.spans[self._next][0] < end:
            ev_start, ev_end, event, loop = self.spans[self._next]
            self._next += 1
            if ev_end <= start:
                continue
            self._active.append((ev_start, ev_end, event, loop))
            if self.on_start is not None:
                self.on_start(event)

        alive = []
        gain = self.gain
        for ev_start, ev_end, event, loop in self._active:
            pcm = self.samples[event.sample_id]
            length = len(pcm)
            limit = ev_end
            lo = ev_start if ev_start > start else start
            hi = end if end < limit else limit
            if hi > lo:
                src = lo - ev_start
                if loop:
                    src %= length
                dst = lo - start
                n = hi - lo
                if gain == 1.0:
                    for i in range(n):
                        if loop and src >= length:
                            src -= length
                        total = out[dst + i] + pcm[src]
                        src += 1
                        if total > 32767:
                            total = 32767
                        elif total < -32768:
                            total = -32768
                        out[dst + i] = total
                else:
                    for i in range(n):
                        if loop and src >= length:
                            src -= length
                        value = int(pcm[src] * gain)
                        src += 1
                        if value > 32767:
                            value = 32767
                        elif value < -32768:
                            value = -32768
                        total = out[dst + i] + value
                        if total > 32767:
                            total = 32767
                        elif total < -32768:
                            total = -32768
                        out[dst + i] = total
            if limit > end:
                alive.append((ev_start, ev_end, event, loop))
        self._active = alive
        return out


def pcm_bytes(samples: array.array) -> bytes:
    """Little-endian int16 bytes, whatever the host byte order."""
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()


# ---------------------------------------------------------------------------
# playback
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sdmixplay",
        description="Play a Rave eJay .MIX arrangement through sounddevice, "
                    "without the ported engine.")
    p.add_argument("input", nargs="?", metavar="MIX",
                   help=".mix file to play")
    p.add_argument("-r", "--res", default=None, metavar="DIR",
                   help="eJay install folder holding EJAY/PXD and the sample "
                        "folders (default: search next to the mix)")
    p.add_argument("-i", "--index", default=None, metavar="FILE",
                   help="sample list (default: <res>/EJAY/PXD)")
    p.add_argument("-b", "--bpm", type=float, default=DEFAULT_BPM,
                   help="tempo used to time the records (default: 180)")
    p.add_argument("--beats", type=float, default=DEFAULT_BEATS,
                   help="beats per record (default: 8, i.e. two 4/4 bars = "
                        "2.667 s at 180 bpm)")
    p.add_argument("--step", type=float, default=None, metavar="SECONDS",
                   help="length of one record; overrides --bpm/--beats")
    p.add_argument("-l", "--list", action="store_true",
                   help="print the resolved arrangement and exit")
    p.add_argument("--strict", action="store_true",
                   help="fail instead of skipping unresolvable samples")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device (index or name substring)")
    p.add_argument("--block", type=int, default=BLOCK_FRAMES, metavar="N",
                   help="mix/write block in frames (default: %d)"
                        % BLOCK_FRAMES)
    p.add_argument("-g", "--gain", type=float, default=1.0,
                   help="mix gain (default: 1.0)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="report each sound as it starts to play")
    return p


def open_stream(device=None, frames: int = BLOCK_FRAMES,
                channels: int = 1):
    """Open a blocking PortAudio stream for int16 audio at 44.1 kHz."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise MixError("this player needs the 'sounddevice' package "
                       "('pip install sounddevice')") from exc
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    try:
        stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE, channels=channels, dtype="int16",
            blocksize=frames, device=device)
        stream.start()
    except sd.PortAudioError as exc:
        raise MixError("cannot open the output device: %s" % exc) from exc
    return stream


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    return "%d:%05.2f" % (minutes, seconds - 60 * minutes)


def _summary(mix: MixFile, events, paths: dict, step: float,
             frames=None) -> str:
    """One-line description; ``frames`` is the mixed length (ring-out)."""
    if frames is None:
        frames = max(event_frames(event, step)[1] for event in events)
    length = frames
    return ("%s  %s  %d records  %d events  %s"
            % (os.path.basename(mix.path), mix.version or "mix",
               mix.used_records(), len(events),
               _format_time(length / float(SAMPLE_RATE))))


def _list(mix: MixFile, events, paths: dict, step: float) -> int:
    print(_summary(mix, events, paths, step))
    width = max((len(os.path.basename(p)) for p in paths.values()), default=8)
    print("    #   time     Tk Ln  ID   filename")
    for event in events:
        start, _ = event_frames(event, step)
        print("  %3d  %8s  T%d %s  %04X  %-*s  %s"
              % (event.record, _format_time(start / float(SAMPLE_RATE)),
                 event.track, event.lane, event.sample_id, width,
                 os.path.basename(paths[event.sample_id]),
                 "x%d" % event.span if event.span > 1 else ""))
    return 0


def _resolve(args):
    """Parse the mix and resolve its samples; returns the working set."""
    try:
        mix = read_mix(args.input)
    except OSError as exc:
        print("sdmixplay: %s: %s" % (args.input, exc), file=sys.stderr)
        return None
    except MixError as exc:
        print("sdmixplay: %s: %s" % (args.input, exc), file=sys.stderr)
        return None

    if args.index:
        index_path = args.index
        res_root = args.res or os.path.dirname(
            os.path.dirname(os.path.abspath(index_path)))
    elif args.res:
        index_path = os.path.join(args.res, "EJAY", "PXD")
        res_root = args.res
    else:
        index_path = find_index(args.input)
        res_root = (os.path.dirname(os.path.dirname(index_path))
                    if index_path else "")
    if not index_path or not os.path.isfile(index_path):
        print("sdmixplay: cannot find the eJay sample index (EJAY/PXD); "
              "pass --res or --index", file=sys.stderr)
        return None
    try:
        index = read_index(index_path)
    except OSError as exc:
        print("sdmixplay: %s: %s" % (index_path, exc), file=sys.stderr)
        return None

    step = step_seconds(args)
    if step <= 0:
        print("sdmixplay: the record length must be positive", file=sys.stderr)
        return None

    events = build_events(mix)
    paths = {}
    missing = []
    for event in events:
        if event.sample_id in paths:
            continue
        entry = sample_for(event.sample_id, index)
        path = resolve_sample(res_root, entry.path) if entry else None
        if path is None:
            missing.append(event.sample_id)
        else:
            paths[event.sample_id] = path
    if missing:
        ids = ", ".join("0x%03X" % sid for sid in sorted(set(missing)))
        if args.strict:
            print("sdmixplay: %d sample(s) not found: %s"
                  % (len(set(missing)), ids), file=sys.stderr)
            return None
        if not args.quiet:
            print("sdmixplay: skipping %d missing sample(s): %s"
                  % (len(set(missing)), ids), file=sys.stderr)
    events = [event for event in events if event.sample_id in paths]
    if not events:
        print("sdmixplay: nothing to play in %s" % args.input,
              file=sys.stderr)
        return None
    return mix, events, paths, step


def play(args, stream=None) -> int:
    """Play the arrangement; returns a process status."""
    resolved = _resolve(args)
    if resolved is None:
        return 1
    mix, events, paths, step = resolved

    if args.list:
        return _list(mix, events, paths, step)

    samples = {}
    failed = []
    print("Decoding samples...")
    for sample_id in sorted({event.sample_id for event in events}):
        path = paths[sample_id]
        try:
            samples[sample_id] = decode_sample(path)
        except MixError as exc:
            failed.append(str(exc))
    if failed:
        for message in failed:
            print("sdmixplay: skipped %s" % message, file=sys.stderr)
        events = [event for event in events
                  if event.sample_id in samples]
        if not events:
            print("sdmixplay: no playable samples left", file=sys.stderr)
            return 1


    verbose = args.verbose and not args.quiet

    def announce(event):
        if verbose:
            print("  %8s  T%d %s  %04X  %s"
                  % (_format_time(event_frames(event, step)[0] /
                                  float(SAMPLE_RATE)),
                     event.track, event.lane, event.sample_id,
                     os.path.basename(paths[event.sample_id])))

    print("Decoded!")
    mixer = Mixer(events, samples, step, gain=args.gain, on_start=announce)
    if mixer.total <= 0:
        print("sdmixplay: the arrangement is empty", file=sys.stderr)
        return 1

    if stream is None:
        try:
            stream = open_stream(args.device, args.block)
        except MixError as exc:
            print("sdmixplay: %s" % exc, file=sys.stderr)
            return 1
        owned = True
    else:
        owned = False

    if not args.quiet:
        print(_summary(mix, events, paths, step, mixer.total)
              + "  via sounddevice")

    try:
        block = max(64, int(args.block))
        for start in range(0, mixer.total, block):
            count = min(block, mixer.total - start)
            stream.write(pcm_bytes(mixer.mix(start, count)))
    except KeyboardInterrupt:
        if not args.quiet:
            print("sdmixplay: interrupted", file=sys.stderr)
        return 130
    finally:
        if owned:
            try:
                stream.stop()
            finally:
                stream.close()

    if not args.quiet:
        print("done")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input is None:
        parser.error("the following arguments are required: MIX")
    if args.gain <= 0:
        parser.error("--gain must be positive")
    if args.block <= 0:
        parser.error("--block must be positive")
    return play(args)


if __name__ == "__main__":
    sys.exit(main())
