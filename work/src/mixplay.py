"""Play a Rave eJay ``.MIX`` arrangement on the speakers.

    python src/mixplay.py TRANCE.MIX --res C:/eJay/disk/RAVE
    python src/mixplay.py TRANCE.MIX --list        # print the arrangement
    python src/mixplay.py TRANCE.MIX --sink waveout

The format is documented in ``docs/MIX_FORMAT.md``: a ``0x0A07`` header, then
351 records of 16 words (8 A-lane cells, then 8 B-lane cells), then a
``0x0A08`` trailer with the version string.  A non-zero word is a sample ID;
``sample_id - 731`` indexes the plain-text sample list ``EJAY/PXD`` that ships
with the eJay install, whose paths are relative to ``disk/RAVE``.

A sample that spans several records is stored as the same ID repeated in every
record it covers (``docs/MIX_FORMAT.md`` section 2), so runs of one ID become a
single play request that starts at the first record and ends at the last.  The
engine then decodes the sample for that span: a longer run plays the whole
sample, a shorter one truncates it.

The record length is not stored in the file, so it is a command-line
parameter: ``--bpm`` at eight beats per record by default (two 4/4 bars,
2.667 s - see ``docs/MIX_FORMAT.md`` section 2), or ``--step SECONDS`` to set
it directly.

Only the first 79 records of ``TRANCE.MIX`` hold music; the unused tail of the
351-record grid carries stray bytes (``docs/MIX_FORMAT.md`` section 7), so any
cell below ``MIN_SAMPLE_ID`` (731, the lowest ID the index resolves) is treated
as empty.  Without that filter the stray ``1..15`` counter in the padding shows
up as 15 unresolvable samples and stretches the arrangement to 249 records.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

import pxd32d5
import pxdsink

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
SAMPLE_RATE = 44100             # the mix ring's rate (docs/PLAYBACK.md)
BYTES_PER_FRAME = 4             # 16 bit stereo

LEAD_BYTES = 100000             # queue requests this far ahead of the front
POLL = 0.01                     # scheduler interval
END_TIMEOUT_EXTRA = 10.0        # slack after the arrangement's length
TAIL_DRAIN = 1.0                # let the device's queued buffers play out
STALL_SECONDS = 4.0             # the front not moving this long is a stall

__all__ = [
    "MixFile",
    "MixEvent",
    "SampleEntry",
    "MixError",
    "MIN_SAMPLE_ID",
    "read_mix",
    "read_index",
    "sample_for",
    "resolve_sample",
    "find_index",
    "build_events",
    "event_range",
    "step_seconds",
    "play",
    "main",
]


class MixError(ValueError):
    """The file is not a readable arrangement, or a value is nonsensical."""


# ---------------------------------------------------------------------------
# the arrangement file
# ---------------------------------------------------------------------------


@dataclass
class MixFile:
    """A parsed ``.MIX``: 16-word grid records plus the trailer version."""

    path: str
    header: int
    records: List[Tuple[int, ...]]
    version: str = ""

    def used_records(self) -> int:
        """One past the last record that holds a sample.

        The unused tail of the grid is not reliably zero (``section 7``), so
        only values the sample index can resolve count as content.
        """
        for i in range(len(self.records) - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self.records[i]):
                return i + 1
        return 0

    def cells(self) -> Iterator[Tuple[int, str, int, int]]:
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
    return MixFile(path=path, header=header, records=records, version=version)


# ---------------------------------------------------------------------------
# the sample index (``disk/RAVE/EJAY/PXD``)
# ---------------------------------------------------------------------------


@dataclass
class SampleEntry:
    """One six-line record of the eJay sample list."""

    path: str                   # "bq\\r1bs001.pxd", relative to disk/RAVE
    category: str = ""
    number: str = ""
    name: str = ""


def read_index(path: str) -> List[SampleEntry]:
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


def sample_for(sample_id: int, index: Sequence[SampleEntry]
               ) -> Optional[SampleEntry]:
    """``sample_id - ID_OFFSET`` (docs/MIX_FORMAT.md section 3)."""
    pos = sample_id - ID_OFFSET
    if 0 <= pos < len(index):
        return index[pos]
    return None


def find_index(mix_path: str) -> Optional[str]:
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


def resolve_sample(res_root: str, relative: str) -> Optional[str]:
    """Resolve an index path under ``res_root``, ignoring letter case.

    The index was written on a case-insensitive file system and names its
    folders in lower case (``bq\r1bs001.pxd``); the install may hold
    ``BQ/R1BS001.PXD``, and a POSIX copy can be either.
    """
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


@dataclass
class MixEvent:
    record: int                 # first record the cell covers
    span: int                   # number of records it is repeated over
    track: int                  # 1..8
    lane: str                   # "A" = first layer, "B" = second layer
    sample_id: int

    @property
    def end_record(self) -> int:
        return self.record + self.span


def build_events(mix: MixFile) -> List[MixEvent]:
    """Collapse repeated IDs into one event per continuous run.

    ``docs/MIX_FORMAT.md`` section 2: a sample covering several steps is the
    same ID repeated in each of them, so a run is one sounding, not one hit
    per record.
    """
    events: List[MixEvent] = []
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


def step_seconds(args: argparse.Namespace) -> float:
    """Seconds per record: ``--step`` wins, else ``--bpm`` at ``--beats``."""
    if getattr(args, "step", None):
        return float(args.step)
    return 60.0 / float(args.bpm) * float(args.beats)


def event_range(event: MixEvent, step: float) -> Tuple[int, int]:
    """Ring positions (bytes) for ``event``: start and end."""
    first = int(round(event.record * step * SAMPLE_RATE)) * BYTES_PER_FRAME
    last = int(round(event.end_record * step * SAMPLE_RATE)) * BYTES_PER_FRAME
    if last <= first:
        last = first + BYTES_PER_FRAME
    return first, last


# ---------------------------------------------------------------------------
# playback
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mixplay",
        description="Play a Rave eJay .MIX arrangement on the speakers.")
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
    p.add_argument("-s", "--sink", choices=("sounddevice", "waveout"),
                   default="sounddevice",
                   help="audio backend (default: sounddevice)")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device for the sounddevice sink")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="report each sound as it starts to play")
    return p


def open_sink(args: argparse.Namespace) -> pxdsink.OutputSink:
    """Create the requested backend (its device opens immediately)."""
    if args.sink == "waveout":
        return pxdsink.WaveOutSink()
    device = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    return pxdsink.SoundDeviceSink(device=device)


def _any_active(engine: pxd32d5.Engine) -> bool:
    return any(voice.state != 0 for voice in engine.voices)


def _pick_voice(engine: pxd32d5.Engine, cursor: int) -> int:
    """First idle voice from ``cursor``; otherwise the cursor itself."""
    count = len(engine.voices)
    for step in range(count):
        index = (cursor + step) % count
        if engine.voices[index].state == 0:
            return index
    return cursor % count


def _queue_events(engine: pxd32d5.Engine, events: Sequence[MixEvent],
                  paths: dict, names: dict, step: float,
                  queued: int = 0, cursor: int = 0,
                  verbose: bool = False) -> Tuple[int, int]:
    """Queue the next requests; returns ``(queued, next voice cursor)``.

    Requests are armed up to ``LEAD_BYTES`` ahead of the play position.  The
    port's front stops at the last requested end, so a gap in the arrangement
    also needs one request armed beyond it (otherwise the front could never
    reach it); that is the ``not _any_active`` case below.
    """
    total = len(events)
    while queued < total:
        event = events[queued]
        start, end = event_range(event, step)
        front = engine.play_position()
        ahead = start > front + LEAD_BYTES
        if ahead and queued > 0 and _any_active(engine):
            break
        voice = _pick_voice(engine, cursor)
        cursor = (voice + 1) % len(engine.voices)
        pxd32d5.PPlay(paths[event.sample_id], voice, start, 0, end, 0)
        if verbose:
            t = start / float(SAMPLE_RATE * BYTES_PER_FRAME)
            name = names.get(event.sample_id, "")
            print("  %s  T%d %s  %04X  %s"
                  % (_format_time(t), event.track, event.lane,
                     event.sample_id, name))
        queued += 1
        if ahead:
            # Keep the front moving across a gap; one is enough.
            break
    return queued, cursor


def _report_errors(engine: pxd32d5.Engine) -> None:
    """Name the streams the decoder had to drop (port-only bookkeeping)."""
    for message in engine.playback_errors:
        print("mixplay: skipped %s" % message, file=sys.stderr)


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    return "%d:%05.2f" % (minutes, seconds - 60 * minutes)


def _list(mix: MixFile, events: Sequence[MixEvent], paths: dict,
          step: float) -> int:
    used = mix.used_records()
    length = event_range(events[-1], step)[1] / float(
        SAMPLE_RATE * BYTES_PER_FRAME)
    print("%s  %s  %d records  %d events  %s"
          % (mix.path, mix.version or "(no version)", used, len(events),
             _format_time(length)))
    width = max((len(os.path.basename(p)) for p in paths.values()),
                default=8)

    print("    #   time     Tk Ln  ID   filename")
    for event in events:
        start, _ = event_range(event, step)
        print("  %3d  %8s  T%d %s  %04X  %-*s  %s"
              % (event.record,
                 _format_time(start / float(SAMPLE_RATE * BYTES_PER_FRAME)),
                 event.track, event.lane, event.sample_id, width,
                 os.path.basename(paths[event.sample_id]),
                 "x%d" % event.span if event.span > 1 else ""))
    return 0


def play(args: argparse.Namespace, sink: Optional[pxdsink.OutputSink] = None,
         verbose: bool = False) -> int:
    """Parse, resolve and play the arrangement; returns a process status."""
    try:
        mix = read_mix(args.input)
    except OSError as exc:
        print("mixplay: %s: %s" % (args.input, exc), file=sys.stderr)
        return 1
    except MixError as exc:
        print("mixplay: %s: %s" % (args.input, exc), file=sys.stderr)
        return 1

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
        print("mixplay: cannot find the eJay sample index (EJAY/PXD); "
              "pass --res or --index", file=sys.stderr)
        return 1
    try:
        index = read_index(index_path)
    except OSError as exc:
        print("mixplay: %s: %s" % (index_path, exc), file=sys.stderr)
        return 1

    step = step_seconds(args)
    if step <= 0:
        print("mixplay: the record length must be positive", file=sys.stderr)
        return 1

    events = build_events(mix)
    paths = {}
    names = {}
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
            names[event.sample_id] = entry.name if entry else ""
    if missing:
        ids = ", ".join("0x%03X" % sid for sid in sorted(set(missing)))
        if args.strict:
            print("mixplay: %d sample(s) not found: %s"
                  % (len(set(missing)), ids), file=sys.stderr)
            return 1
        if not args.quiet:
            print("mixplay: skipping %d missing sample(s): %s"
                  % (len(set(missing)), ids), file=sys.stderr)
    events = [event for event in events if event.sample_id in paths]
    if not events:
        print("mixplay: nothing to play in %s" % args.input, file=sys.stderr)
        return 1

    if args.list:
        return _list(mix, events, paths, step)

    total_bytes = event_range(events[-1], step)[1]
    seconds = total_bytes / float(SAMPLE_RATE * BYTES_PER_FRAME)

    if sink is None:
        try:
            sink = open_sink(args)
        except (ImportError, OSError) as exc:
            print("mixplay: cannot open the %s sink: %s"
                  % (args.sink, exc), file=sys.stderr)
            return 1

    if not args.quiet:
        print("%s  %s  %d records  %d events  %s  via %s"
              % (os.path.basename(args.input), mix.version or "mix",
                 mix.used_records(), len(events), _format_time(seconds),
                 args.sink))

    pxd32d5.PInit()
    engine = pxd32d5.engine
    engine.sink = sink          # PInit has run, so nothing closes it under us
    try:
        # Same order as the host: queue, then start the player thread.
        queued, cursor = _queue_events(engine, events, paths, names, step,
                                       verbose=verbose)
        pxd32d5.PStart()
        deadline = time.monotonic() + seconds + END_TIMEOUT_EXTRA
        last_front = engine.play_position()
        last_progress = time.monotonic()
        while queued < len(events) or engine.play_position() < total_bytes:
            now = time.monotonic()
            if now > deadline:
                print("mixplay: playback did not finish (timeout)",
                      file=sys.stderr)
                _report_errors(engine)
                return 1
            queued, cursor = _queue_events(engine, events, paths, names, step,
                                           queued, cursor, verbose=verbose)
            front = engine.play_position()
            if front != last_front:
                last_front = front
                last_progress = now
            elif now - last_progress > STALL_SECONDS:
                print("mixplay: playback stalled at %s (event %d of %d, "
                      "%d bytes played)"
                      % (_format_time(front / float(SAMPLE_RATE *
                                                    BYTES_PER_FRAME)),
                         queued, len(events), front), file=sys.stderr)
                if engine.last_error:
                    print("mixplay: last mixer error: %s" % engine.last_error,
                          file=sys.stderr)
                _report_errors(engine)
                return 1
            time.sleep(POLL)
        _report_errors(engine)
        if not isinstance(sink, pxdsink.FileSink):
            time.sleep(TAIL_DRAIN)   # let the device's buffers play out
        if not args.quiet:
            print("done")
        return 0
    except KeyboardInterrupt:
        if not args.quiet:
            print("mixplay: interrupted", file=sys.stderr)
        return 130
    finally:
        pxd32d5.PClose()


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.input is None:
        parser.error("the following arguments are required: MIX")
    return play(args, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
