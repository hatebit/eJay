"""Techno eJay ``.MIX`` format implementation."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Mapping

from ...format_error import FormatError
from ...formatting import format_time
from ...mix_document import MixDocument
from ...mix_format import MixFormat
from ...placement import Placement
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from ...pxd.sample_collection import SampleCollection
from .techno_event_builder import TechnoEventBuilder
from .techno_mix_data import TechnoMixData
from .techno_sample_collector import TechnoSampleCollector

MIX_MAGIC = 0x0889
MIX_FOOTER = b"\xa9\x7a\x8a\x01"
EVENT_MARKER = b">?~>"
EVENT_PREFIX = 4
SHORT_BYTES = 7
LONG_BYTES = 17
TRACKS = 17
TEXT_OFFSET = 0x10
DEFAULT_BPM = 140.0


class TechnoMixFormat(MixFormat):
    """Techno eJay: event table in the trailer plus the ``RAVE20`` archive."""

    name = "techno"
    version = "2.0.1"

    def matches(self, header: bytes) -> bool:
        """Return True for the ``0x0889`` Techno header."""
        if len(header) < 2:
            return False
        return struct.unpack_from("<H", header, 0)[0] == MIX_MAGIC

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        """Parse the header, text block, and per-track event table.

        Args:
            path: ``.MIX`` file.
            options: Full player options (unused here).

        Returns:
            A document whose ``payload`` is a
            :class:`~player.formats.techno.techno_mix_data.TechnoMixData`.

        Raises:
            FormatError: The magic, footer, or event table is bad.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc
        if len(data) < 0x14:
            raise FormatError(f"{path.name}: too short for a Techno eJay mix")

        magic = struct.unpack_from("<H", data, 0)[0]
        if magic != MIX_MAGIC:
            raise FormatError(
                f"{path.name}: header 0x{magic:04X}, "
                f"expected 0x{MIX_MAGIC:04X}")
        if not data.endswith(MIX_FOOTER):
            raise FormatError(f"{path.name}: missing 0x018A7AA9 footer")

        title = _title(data) or path.name
        bpm = _header_bpm(data)
        placements = _read_events(data)

        header = tuple(struct.unpack_from("<8H", data, 0))
        payload = TechnoMixData(
            header=header,
            bpm=bpm,
            title=title,
            track_count=TRACKS,
            event_count=len(placements),
        )
        return MixDocument(
            source=path,
            format_name=self.name,
            title=title,
            tempo_bpm=bpm,
            placements=placements,
            payload=payload,
            metadata={"footer": MIX_FOOTER.hex()},
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        """Resolve the Techno ids through ``RAVE20.INF`` and ``RAVE20``."""
        return TechnoSampleCollector().collect(document, options)

    def prepare_events(self, document: MixDocument, samples: SampleBank,
                       options: Mapping[str, Any]) -> PlaybackPlan:
        """Position one-shot placements and build the stereo plan.

        Raises:
            FormatError: The tempo is not positive.
        """
        bpm_option = options.get("bpm")
        if bpm_option is not None:
            bpm = float(bpm_option)
        elif document.tempo_bpm is not None:
            bpm = float(document.tempo_bpm)
        else:
            bpm = DEFAULT_BPM
        if bpm <= 0:
            raise FormatError("--bpm must be positive")
        return TechnoEventBuilder().build(document, samples, bpm)

    def describe(self, document: MixDocument, samples: SampleBank,
                 plan: PlaybackPlan) -> list[str]:
        """Render the Techno placements as a table."""
        bpm = plan.details.get("bpm", DEFAULT_BPM)
        lines = [
            f"  {bpm:g} bpm  "
            f"{plan.details.get('placements', len(plan.events))} placements",
            "     time       Tk    bar     id  sample",
        ]
        rate = float(plan.sample_rate)
        for event in sorted(plan.events,
                            key=lambda item: (item.start, item.track)):
            bar = event.parameters.get("bar", 0.0)
            lines.append(
                f"  {format_time(event.start / rate):>8}  "
                f"T{event.track:<2d} {bar:7.3f}  "
                f"{event.sample_id:04X}  {event.label}")
        return lines


def _title(data: bytes) -> str:
    """Read the first NUL-terminated string at the text-block offset."""
    if len(data) <= TEXT_OFFSET:
        return ""
    end = data.find(b"\0", TEXT_OFFSET)
    if end < 0:
        return ""
    return data[TEXT_OFFSET:end].decode("latin-1", "replace").strip()


def _header_bpm(data: bytes) -> float:
    """Return header word 4 when it is a plausible tempo."""
    if len(data) < 10:
        return DEFAULT_BPM
    bpm = struct.unpack_from("<H", data, 8)[0]
    return float(bpm) if 40 <= bpm <= 300 else DEFAULT_BPM


def _read_events(data: bytes) -> list[Placement]:
    """Read the trailer's per-track event table.

    Each track block is ``u8 track, u32 count`` followed by that many entries.
    An entry is 7 bytes when its time field is negative and 17 bytes when it is
    zero or positive.  The time is a fixed-point bar index with seven fraction
    bits, negated for the short form; bar 1 is the start of the mix.

    Raises:
        FormatError: The marker, a block header, or the table end is bad.
    """
    marker = data.find(EVENT_MARKER)
    if marker < 0:
        raise FormatError(f"event marker {EVENT_MARKER!r} not found")
    end = len(data) - len(MIX_FOOTER)
    position = marker + len(EVENT_MARKER) + EVENT_PREFIX
    placements: list[Placement] = []

    for track in range(1, TRACKS + 1):
        if position + 5 > end:
            raise FormatError("event table is truncated")
        found = data[position]
        count = struct.unpack_from("<I", data, position + 1)[0]
        if found != track:
            raise FormatError(
                f"event table: expected track {track}, got {found}")
        position += 5
        for _ in range(count):
            if position + SHORT_BYTES > end:
                raise FormatError("event entry is truncated")
            raw = struct.unpack_from("<h", data, position + 1)[0]
            size = LONG_BYTES if raw >= 0 else SHORT_BYTES
            if position + size > end:
                raise FormatError("event entry is truncated")
            units = abs(raw) - (1 if raw < 0 else 0)
            placements.append(Placement(
                track=track,
                bar=units / 128.0 + 1.0,
                sample_id=data[position + 5] | data[position + 6] << 8,
                span=0.0,
                parameters={"long": size == LONG_BYTES},
            ))
            position += size

    if position != end:
        raise FormatError("event table does not end at the footer")
    return placements
