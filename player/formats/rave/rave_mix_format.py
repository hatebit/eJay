"""Rave eJay 1.x ``.MIX`` format implementation."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path
from typing import Any, Mapping

from ...format_error import FormatError
from ...formatting import format_time
from ...mix_document import MixDocument
from ...mix_format import MixFormat
from ...placement import Placement
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from ...pxd.sample_collection import SampleCollection
from .rave_event_builder import RaveEventBuilder
from .rave_grid import MIN_SAMPLE_ID, RECORD_WORDS, TRACKS, RaveGrid
from .rave_sample_collector import RaveSampleCollector

MIX_MAGIC = 0x0A07
MIX_TRAILER = 0x0A08
RECORD_BYTES = 32
GRID_OFFSET = 2
DEFAULT_BPM = 180.0
DEFAULT_BEATS = 8.0


class RaveMixFormat(MixFormat):
    """Rave eJay: 16-word grid records plus the ``EJAY/PXD`` index."""

    name = "rave"
    version = "2.0.0"

    def matches(self, header: bytes) -> bool:
        """Return True for the ``0x0A07`` grid header."""
        if len(header) < 2:
            return False
        return struct.unpack_from("<H", header, 0)[0] == MIX_MAGIC

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add the Rave timing options."""
        parser.add_argument(
            "--beats", type=float, default=DEFAULT_BEATS,
            help="beats per record (default: 8, i.e. two 4/4 bars)")
        parser.add_argument(
            "--step", type=float, default=None, metavar="SECONDS",
            help="length of one record; overrides --bpm/--beats")

    def options(self, namespace: argparse.Namespace) -> dict[str, Any]:
        """Extract the Rave options from a CLI namespace."""
        return {
            "beats": namespace.beats,
            "step": namespace.step,
        }

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        """Parse a Rave grid and its trailer.

        Args:
            path: ``.MIX`` file.
            options: Full player options (unused here).

        Returns:
            A document whose ``payload`` is a
            :class:`~player.formats.rave.rave_grid.RaveGrid`.

        Raises:
            FormatError: The file is too short, has the wrong magic, or has an
                empty grid.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc
        if len(data) < GRID_OFFSET + RECORD_BYTES:
            raise FormatError(f"{path.name}: too short for an arrangement")

        header = struct.unpack_from("<H", data, 0)[0]
        if header != MIX_MAGIC:
            raise FormatError(
                f"{path.name}: header 0x{header:04X}, "
                f"expected 0x{MIX_MAGIC:04X}")

        tag = data.find(b"\x08\x0a", GRID_OFFSET)
        while tag != -1 and (tag - GRID_OFFSET) % RECORD_BYTES:
            tag = data.find(b"\x08\x0a", tag + 1)
        if tag != -1:
            count = (tag - GRID_OFFSET) // RECORD_BYTES
        else:
            count = (len(data) - GRID_OFFSET) // RECORD_BYTES
        if count <= 0:
            raise FormatError(f"{path.name}: the arrangement grid is empty")

        records = tuple(
            struct.unpack_from("<%dH" % RECORD_WORDS, data,
                               GRID_OFFSET + RECORD_BYTES * index)
            for index in range(count)
        )
        version = ""
        if tag != -1 and tag + 6 <= len(data):
            size = struct.unpack_from("<H", data, tag + 4)[0]
            raw = data[tag + 6:tag + 6 + size]
            version = raw.split(b"\0")[0].decode(
                "latin-1", "replace").strip()

        grid = RaveGrid(header=header, records=records, version=version)
        placements = []
        for record, lane, track, sample_id in grid.cells():
            placements.append(Placement(
                track=track,
                bar=1.0 + 2.0 * record,
                sample_id=sample_id,
                span=2.0,
                layer=lane,
                parameters={"record": record},
            ))

        return MixDocument(
            source=path,
            format_name=self.name,
            title=version or path.name,
            tempo_bpm=None,
            placements=placements,
            payload=grid,
            metadata={
                "header": header,
                "version": version,
                "records": len(records),
                "tracks": TRACKS,
                "min_sample_id": MIN_SAMPLE_ID,
            },
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        """Resolve the Rave ids through ``EJAY/PXD``."""
        return RaveSampleCollector().collect(document, options)

    def prepare_events(self, document: MixDocument, samples: SampleBank,
                       options: Mapping[str, Any]) -> PlaybackPlan:
        """Time the grid runs and build the mono plan.

        Raises:
            FormatError: The record length or tempo is not positive.
        """
        scoped = self.format_options(options)
        bpm_option = options.get("bpm")
        bpm = float(DEFAULT_BPM if bpm_option is None else bpm_option)
        step_option = scoped.get("step")
        if step_option is not None:
            step = float(step_option)
        else:
            beats_option = scoped.get("beats")
            beats = float(
                DEFAULT_BEATS if beats_option is None else beats_option)
            if bpm <= 0:
                raise FormatError("--bpm must be positive")
            step = 60.0 / bpm * beats
        if step <= 0:
            raise FormatError("the record length must be positive")
        return RaveEventBuilder().build(document, samples, step)

    def describe(self, document: MixDocument, samples: SampleBank,
                 plan: PlaybackPlan) -> list[str]:
        """Render the Rave arrangement as a table."""
        details = plan.details
        lines = [
            f"  {details.get('records', 0)} records, "
            f"{details.get('used_records', 0)} used, "
            f"{details.get('step_seconds', 0.0):.4f} s per record",
            "    #   time     Tk Ln  ID   filename",
        ]
        rate = float(plan.sample_rate)
        for event in sorted(plan.events,
                            key=lambda item: (item.start, item.track)):
            record = event.parameters.get("record", 0)
            span = event.parameters.get("span", 1)
            lane = event.parameters.get("lane", "A")
            line = (
                f"  {record:3d}  {format_time(event.start / rate):>8}  "
                f"T{event.track} {lane}  {event.sample_id:04X}  "
                f"{event.label:<20s}")
            if span > 1:
                line += f" x{span}"
            lines.append(line.rstrip())
        return lines
