from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

__all__ = ["MIX_MAGIC", "MIX_TRAILER", "RECORD_WORDS", "RECORD_BYTES", "GRID_OFFSET", "TRACKS", "ID_OFFSET", "MIN_SAMPLE_ID", "DEFAULT_BPM", "DEFAULT_BEATS", "SAMPLE_RATE", "BAR_FRAMES", "RECORD_FRAMES", "MixError", "MixHeader", "MixFileInfo", "MixEvent", "SampleEntry", "MixFile"]

MIX_MAGIC = 0x0A07
MIX_TRAILER = 0x0A08
RECORD_WORDS = 16
RECORD_BYTES = 32
GRID_OFFSET = 2
TRACKS = 8
ID_OFFSET = 731
MIN_SAMPLE_ID = ID_OFFSET

DEFAULT_BPM = 180.0
DEFAULT_BEATS = 8.0
SAMPLE_RATE = 44100
BAR_FRAMES = 58800
RECORD_FRAMES = 2 * BAR_FRAMES


class MixError(ValueError):
    pass


@dataclass(frozen=True)
class MixHeader:
    header_word: int
    version: str
    record_count: int


@dataclass(frozen=True)
class MixFileInfo:
    path: str
    header_word: int
    version: str
    record_count: int
    used_records: int


@dataclass(frozen=True)
class SampleEntry:
    path: str
    category: str = ""
    number: str = ""
    name: str = ""


@dataclass(frozen=True)
class MixEvent:
    record: int
    time_frames: int
    lane: str
    track: int
    sample_id: int
    sample_path: Optional[str] = None
    sample_name: Optional[str] = None
    sample_category: Optional[str] = None
    sample_number: Optional[str] = None
    run_start: int = 0
    run_end: int = 0
    span: int = 0

    @property
    def end_record(self):
        if self.span:
            return self.record + self.span
        if self.run_end:
            return self.run_end
        return self.record


def _read_mix_raw(path: str):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < GRID_OFFSET + RECORD_BYTES:
        raise MixError("file is too short for an arrangement")
    header = struct.unpack_from("<H", data, 0)[0]
    if header != MIX_MAGIC:
        raise MixError("not a Rave eJay .mix (header 0x%04X)" % header)

    tag = data.find(b"\x08\x0a", GRID_OFFSET)
    while tag != -1 and (tag - GRID_OFFSET) % RECORD_BYTES:
        tag = data.find(b"\x08\x0a", tag + 1)
    if tag != -1:
        count = (tag - GRID_OFFSET) // RECORD_BYTES
    else:
        count = (len(data) - GRID_OFFSET) // RECORD_BYTES
    if count <= 0:
        raise MixError("the arrangement grid is empty")

    records = [
        struct.unpack_from("<%dH" % RECORD_WORDS, data, GRID_OFFSET + RECORD_BYTES * i)
        for i in range(count)
    ]
    version = ""
    if tag != -1 and tag + 6 <= len(data):
        size = struct.unpack_from("<H", data, tag + 4)[0]
        raw = data[tag + 6:tag + 6 + size]
        version = raw.split(b"\0")[0].decode("latin-1", "replace").strip()
    return header, records, version


def read_index(path: str):
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


def sample_for(sample_id: int, index: Sequence[SampleEntry]):
    if sample_id < MIN_SAMPLE_ID:
        return None
    idx = sample_id - ID_OFFSET
    if idx < 0 or idx >= len(index):
        return None
    return index[idx]


def step_seconds(bpm: float = DEFAULT_BPM, beats: float = DEFAULT_BEATS) -> float:
    if bpm <= 0 or beats <= 0:
        raise MixError("bpm and beats must be positive")
    return 60.0 * beats / bpm


def step_frames(bpm: float = DEFAULT_BPM, beats: float = DEFAULT_BEATS, sample_rate: int = SAMPLE_RATE) -> int:
    return int(round(step_seconds(bpm, beats) * sample_rate))


class MixFile:
    def __init__(self, path: str):
        self.path = path
        header, records, version = _read_mix_raw(path)
        self._header_word = header
        self._records = records
        self._version = version

    def header(self):
        return MixHeader(self._header_word, self._version, len(self._records))

    def info(self):
        return MixFileInfo(self.path, self._header_word, self._version, len(self._records), self.used_records())

    def records(self):
        return list(self._records)

    def used_records(self):
        for i in range(len(self._records) - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self._records[i]):
                return i + 1
        return 0

    def cells(self):
        for record, row in enumerate(self._records):
            for column, sample_id in enumerate(row):
                if sample_id < MIN_SAMPLE_ID:
                    continue
                lane = "A" if column < TRACKS else "B"
                yield record, lane, column % TRACKS + 1, sample_id

    def events(self, index: Optional[Sequence[SampleEntry]] = None, bpm: float = DEFAULT_BPM, beats: float = DEFAULT_BEATS, sample_rate: int = SAMPLE_RATE):
        s_frames = step_frames(bpm, beats, sample_rate)
        events = []
        for column in range(RECORD_WORDS):
            lane = "A" if column < TRACKS else "B"
            track = column % TRACKS + 1
            current = 0
            first = 0
            for record, row in enumerate(self._records):
                sample_id = row[column]
                if sample_id < MIN_SAMPLE_ID:
                    sample_id = 0
                if sample_id == current:
                    continue
                if current:
                    span = record - first
                    ent = sample_for(current, index) if index is not None else None
                    spath = ent.path if ent else None
                    sname = ent.name if ent else None
                    scat = ent.category if ent else None
                    snum = ent.number if ent else None
                    events.append(MixEvent(record=first, time_frames=first * s_frames, lane=lane, track=track, sample_id=current,
                                           sample_path=spath, sample_name=sname, sample_category=scat, sample_number=snum,
                                           run_start=first, run_end=record, span=span))
                current = sample_id
                first = record
            if current:
                span = len(self._records) - first
                ent = sample_for(current, index) if index is not None else None
                spath = ent.path if ent else None
                sname = ent.name if ent else None
                scat = ent.category if ent else None
                snum = ent.number if ent else None
                events.append(MixEvent(record=first, time_frames=first * s_frames, lane=lane, track=track, sample_id=current,
                                       sample_path=spath, sample_name=sname, sample_category=scat, sample_number=snum,
                                       run_start=first, run_end=len(self._records), span=span))
        events.sort(key=lambda e: (e.record, e.track, 0 if e.lane == "A" else 1))
        return events

    def __repr__(self):
        return f"MixFile({self.path!r}, records={len(self._records)}, version={self._version!r})"
