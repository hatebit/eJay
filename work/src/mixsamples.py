#!/usr/bin/env python3
"""List the samples a Techno eJay ``.MIX`` arrangement references.

Usage:
    python src/mixsamples.py "data/Techno eJay/WAMBAM.MIX"
    python src/mixsamples.py "data/Techno eJay" --inf "data/Techno eJay/RAVE20.INF"

The container is described in ``docs/__MIX_FORMAT.md``.  Techno eJay names no
samples inside the mix and has no per-sample ``.pxd`` files: the trailer ends
with a per-track event table whose entries carry a numeric sample reference,
and that number is the first field of a ``RAVE20.INF`` record
(``docs/INF_FORMAT.md``).  The record then points at a ``tPxD`` sample inside
the ``RAVE20`` archive.

The event table is a list of per-track blocks: a track byte, a u32 entry
count, then that many entries.  An entry is 7 bytes normally and 17 bytes when
its time field is non-negative; both carry a sample id.  The time field is a
fixed-point bar position (7 fractional bits), stored negated for the short
form.  ``read_events`` returns those placements; this tool uses them to count
references.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

MIX_MAGIC = 0x0889
MIX_FOOTER = b"\xa9\x7a\x8a\x01"
EVENT_MARKER = b">?~>"       # last trailer marker, before the event table
EVENT_PREFIX = 4             # bytes between the marker and track 1
SHORT_BYTES = 7              # entry without the optional 10 extra bytes
LONG_BYTES = 17              # entry whose time field is non-negative
TRACKS = 17
INF_SECTION = "[SAMPLES]"
INF_RECORD_LINES = 12

__all__ = [
    "MixError",
    "Sample",
    "Event",
    "read_index",
    "read_mix",
    "read_events",
    "count_references",
    "format_report",
    "main",
]


class MixError(Exception):
    """Raised when a mix, its sample index, or the index layout is unusable."""


@dataclass(frozen=True)
class Sample:
    """One ``RAVE20.INF`` record.

    Attributes:
        sample_id: First field of the record, the value the mix references.
        name: Bank name, e.g. ``T1LA030``.
        offset: Byte offset of the ``tPxD`` record inside ``RAVE20``.
        size: Record size in bytes.
        bars: Field 9, the bar length the doc cross-checks against placements.
        category: Field 6, the first half of the display name.
        part1: Field 7, the second half of the display name.
    """

    sample_id: int
    name: str
    offset: int
    size: int
    bars: int
    category: str
    part1: str

    @property
    def label(self) -> str:
        """Human-readable sample name, e.g. ``zap / up 4``."""
        parts = [p for p in (self.category, self.part1) if p]
        return " / ".join(parts)


@dataclass(frozen=True)
class Event:
    """One sample placement in a Techno eJay event table.

    Attributes:
        track: 1-based track number, 1 to 16 (17 is stored, always empty).
        bar: 1-based position, with the entry's 1/128-bar fraction.
        sample_id: ``RAVE20.INF`` record id the entry refers to.
        long: True for the 17-byte entry variant.
    """

    track: int
    bar: float
    sample_id: int
    long: bool


def _unquote(text: str) -> str:
    """Strip the quotes ``RAVE20.INF`` puts around its strings."""
    return text.strip().strip('"')


def read_index(path: Path) -> dict[int, Sample]:
    """Read the ``RAVE20.INF`` sample index.

    Args:
        path: Path to the ``.inf`` file.

    Returns:
        Records keyed by their first field, the id the mix references.

    Raises:
        MixError: The file cannot be read or has no ``[SAMPLES]`` records.
    """
    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError as exc:
        raise MixError(f"{path}: {exc.strerror or exc}") from exc
    try:
        start = lines.index(INF_SECTION) + 1
    except ValueError as exc:
        raise MixError(f"{path}: no {INF_SECTION} section") from exc

    samples: dict[int, Sample] = {}
    end = len(lines) - INF_RECORD_LINES + 1
    for pos in range(start, end, INF_RECORD_LINES):
        rec = lines[pos:pos + INF_RECORD_LINES]
        try:
            sample = Sample(
                sample_id=int(rec[0]),
                name=_unquote(rec[2]),
                offset=int(rec[3]),
                size=int(rec[4]),
                bars=int(rec[8]),
                category=_unquote(rec[5]),
                part1=_unquote(rec[6]),
            )
        except (IndexError, ValueError):
            continue
        samples.setdefault(sample.sample_id, sample)
    if not samples:
        raise MixError(f"{path}: no sample records after {INF_SECTION}")
    return samples


def read_mix(path: Path) -> bytes:
    """Read and sanity-check a Techno eJay ``.MIX`` file.

    Args:
        path: File to read.

    Returns:
        The whole file.

    Raises:
        MixError: The file is unreadable or not a Techno eJay mix.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise MixError(f"{path}: {exc.strerror or exc}") from exc
    if len(data) < 0x14:
        raise MixError(f"{path.name}: too short for a Techno eJay mix")
    magic = struct.unpack_from("<H", data, 0)[0]
    if magic != MIX_MAGIC:
        raise MixError(
            f"{path.name}: header 0x{magic:04X}, expected 0x{MIX_MAGIC:04X}"
            " (Rave eJay mixes are read by src/mixplay.py)")
    if not data.endswith(MIX_FOOTER):
        raise MixError(f"{path.name}: missing 0x018A7AA9 footer")
    return data


def read_events(data: bytes) -> list[Event]:
    """Read the trailer's per-track event table.

    Each track block is ``u8 track, u32 count`` followed by ``count`` entries.
    An entry is 7 bytes (``u8 flag, i16 time, i16, u16 id``) when its time is
    negative, and 17 bytes (ten more parameter bytes) when it is zero or
    positive.  The time is a fixed-point bar index with 7 fraction bits,
    negated for the short form; bar 1 is the start of the mix.

    Args:
        data: Contents of one ``.MIX`` file.

    Returns:
        Placements in stored (track, time) order.

    Raises:
        MixError: The marker, a block header, or the table end is bad.
    """
    marker = data.find(EVENT_MARKER)
    if marker < 0:
        raise MixError(f"event marker {EVENT_MARKER!r} not found")
    end = len(data) - len(MIX_FOOTER)
    pos = marker + len(EVENT_MARKER) + EVENT_PREFIX
    events: list[Event] = []
    for track in range(1, TRACKS + 1):
        if pos + 5 > end:
            raise MixError("event table is truncated")
        found = data[pos]
        count = struct.unpack_from("<I", data, pos + 1)[0]
        if found != track:
            raise MixError(
                f"event table: expected track {track}, got {found}")
        pos += 5
        for _ in range(count):
            if pos + SHORT_BYTES > end:
                raise MixError("event entry is truncated")
            raw = struct.unpack_from("<h", data, pos + 1)[0]
            size = LONG_BYTES if raw >= 0 else SHORT_BYTES
            if pos + size > end:
                raise MixError("event entry is truncated")
            units = abs(raw) - (1 if raw < 0 else 0)
            events.append(Event(
                track=track,
                bar=units / 128.0 + 1.0,
                sample_id=data[pos + 5] | data[pos + 6] << 8,
                long=size == LONG_BYTES,
            ))
            pos += size
    if pos != end:
        raise MixError("event table does not end at the footer")
    return events


def count_references(data: bytes,
                     index: Mapping[int, Sample]) -> dict[int, int]:
    """Count event-table entries per sample id.

    Args:
        data: Contents of one ``.MIX`` file.
        index: Sample index; ids it does not know are ignored.

    Returns:
        Sample ids and how many event entries reference each of them.

    Raises:
        MixError: The event table cannot be read.
    """
    counts: dict[int, int] = {}
    for event in read_events(data):
        if event.sample_id in index:
            counts[event.sample_id] = counts.get(event.sample_id, 0) + 1
    return counts


def format_report(mix: Path, counts: Mapping[int, int],
                  index: Mapping[int, Sample]) -> str:
    """Render one mix's sample list as a table.

    Args:
        mix: The mix file the counts came from.
        counts: Sample ids and their reference counts.
        index: Sample index supplying names, sizes and offsets.

    Returns:
        Text ending in a newline, or a "none" line when nothing matched.
    """
    if not counts:
        return f"{mix.name}: no samples referenced\n"
    rows = []
    for sample_id in sorted(counts):
        sample = index[sample_id]
        rows.append((
            str(sample_id),
            sample.name,
            str(sample.bars),
            str(sample.size),
            str(counts[sample_id]),
            sample.label,
            f"0x{sample.offset:08X}",
        ))
    headers = ("id", "name", "bars", "size", "refs", "category / sample",
               "archive offset")
    widths = [max(len(h), *(len(row[col]) for row in rows))
              for col, h in enumerate(headers)]
    numeric = {0, 2, 3, 4}

    def line(row: Sequence[str]) -> str:
        cells = [cell.ljust(widths[col]) if col not in numeric
                 else cell.rjust(widths[col]) for col, cell in enumerate(row)]
        return "  " + "  ".join(cells).rstrip()

    out = [f"{mix.name}: {len(rows)} samples referenced", line(headers)]
    out.extend(line(row) for row in rows)
    return "\n".join(out) + "\n"


def find_mixes(target: Path) -> list[Path]:
    """Expand a file or folder argument into mix files.

    Args:
        target: A ``.MIX`` file or a folder holding some.

    Returns:
        The mix files, sorted by name; empty when a folder has no mixes.
    """
    if not target.is_dir():
        return [target]
    found = {path for pattern in ("*.MIX", "*.mix")
             for path in target.glob(pattern)}
    return sorted(found, key=lambda path: path.name.upper())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mixsamples",
        description="List the RAVE20.INF samples a Techno eJay .MIX "
                    "arrangement references.")
    parser.add_argument(
        "inputs", nargs="+", metavar="MIX",
        help="a .MIX file or a folder of them")
    parser.add_argument(
        "-i", "--inf", default=None, metavar="FILE",
        help="RAVE20.INF sample index (default: RAVE20.INF next to the mix)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments to parse; ``sys.argv[1:]`` when omitted.

    Returns:
        Zero when every mix was read, one when any of them failed.
    """
    args = build_parser().parse_args(argv)
    failed = False

    mixes: list[Path] = []
    for target in args.inputs:
        found = find_mixes(Path(target))
        if not found:
            print(f"{target}: no .MIX files found", file=sys.stderr)
            failed = True
        mixes.extend(found)

    def inf_for(mix_path: Path) -> Path:
        return Path(args.inf) if args.inf else mix_path.parent / "RAVE20.INF"

    data_by_mix: dict[Path, bytes] = {}
    for mix_path in mixes:
        try:
            data_by_mix[mix_path] = read_mix(mix_path)
        except MixError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failed = True

    indexes: dict[Path, dict[int, Sample]] = {}
    for inf_path in sorted({inf_for(path) for path in data_by_mix}):
        try:
            indexes[inf_path] = read_index(inf_path)
        except MixError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failed = True

    for mix_path, data in data_by_mix.items():
        index = indexes.get(inf_for(mix_path))
        if index is None:
            continue
        try:
            counts = count_references(data, index)
        except MixError as exc:
            print(f"error: {mix_path.name}: {exc}", file=sys.stderr)
            failed = True
            continue
        print(format_report(mix_path, counts, index), end="")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
