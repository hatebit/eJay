"""Dance eJay ``.MIX`` format implementation."""

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
from .dance_event_builder import DanceEventBuilder
from .dance_grid import (
    BARS_PER_BLOCK,
    BLOCKS,
    MIN_SAMPLE_ID,
    TRACKS,
    DanceGrid,
)
from .dance_sample_collector import DanceSampleCollector

MIX_MAGIC = 0x0A06
BLOCK_BYTES = 32
GRID_OFFSET = 2
TOTAL_BYTES = GRID_OFFSET + BLOCKS * BLOCK_BYTES
DEFAULT_BPM = 140.0


class DanceMixFormat(MixFormat):
    """Dance eJay: 351 two-bar blocks plus either sample catalog."""

    name = "dance"
    version = "2.0.0"

    def matches(self, header: bytes) -> bool:
        """Return True for the ``0x0A06`` grid header."""
        if len(header) < 2:
            return False
        return struct.unpack_from("<H", header, 0)[0] == MIX_MAGIC

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        """Parse a Dance arrangement grid.

        Args:
            path: ``.MIX`` file.
            options: Full player options (unused here).

        Returns:
            A document whose ``payload`` is a
            :class:`~player.formats.dance.dance_grid.DanceGrid`.

        Raises:
            FormatError: The file is shorter than the grid or has the wrong
                magic.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc
        if len(data) < TOTAL_BYTES:
            raise FormatError(
                f"{path.name}: expected at least {TOTAL_BYTES} bytes, "
                f"found {len(data)}")

        header = struct.unpack_from("<H", data, 0)[0]
        if header != MIX_MAGIC:
            raise FormatError(
                f"{path.name}: header 0x{header:04X}, "
                f"expected 0x{MIX_MAGIC:04X}")

        blocks = tuple(
            struct.unpack_from("<16H", data, GRID_OFFSET + index * BLOCK_BYTES)
            for index in range(BLOCKS)
        )
        grid = DanceGrid(header=header, blocks=blocks)
        placements = [
            Placement(
                track=track,
                bar=1.0 + bar,
                sample_id=sample_id,
                span=1.0,
                parameters={
                    "block": bar // BARS_PER_BLOCK,
                    "bar": bar,
                    "bar_in_block": bar % BARS_PER_BLOCK,
                },
            )
            for bar, track, sample_id in grid.cells()
        ]
        return MixDocument(
            source=path,
            format_name=self.name,
            title=path.stem,
            tempo_bpm=None,
            placements=placements,
            payload=grid,
            metadata={
                "header": header,
                "blocks": len(blocks),
                "tracks": TRACKS,
                "min_sample_id": MIN_SAMPLE_ID,
            },
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        """Resolve the Dance ids through ``PXD.TXT`` and ``MAX.TXT``."""
        return DanceSampleCollector().collect(document, options)

    def prepare_events(self, document: MixDocument, samples: SampleBank,
                       options: Mapping[str, Any]) -> PlaybackPlan:
        """Time the per-track runs and build the mono plan.

        Raises:
            FormatError: The tempo is not positive.
        """
        bpm_option = options.get("bpm")
        bpm = float(DEFAULT_BPM if bpm_option is None else bpm_option)
        if bpm <= 0:
            raise FormatError("--bpm must be positive")
        return DanceEventBuilder().build(document, samples, bpm)

    def describe(self, document: MixDocument, samples: SampleBank,
                 plan: PlaybackPlan) -> list[str]:
        """Render the Dance arrangement as a table."""
        details = plan.details
        lines = [
            f"  {details.get('blocks', 0)} blocks, "
            f"{details.get('used_blocks', 0)} used, "
            f"{details.get('bpm', DEFAULT_BPM):g} bpm, "
            f"{details.get('bar_frames', 0.0):.0f} frames/bar",
            "  blk bar   time      Tk  ID    sample",
        ]
        rate = float(plan.sample_rate)
        for event in sorted(plan.events,
                            key=lambda item: (item.start, item.track)):
            block = event.parameters.get("block", 0)
            bar = event.parameters.get("bar", 0) + 1
            span = event.parameters.get("span", 1)
            stamp = format_time(event.start / rate)
            line = (
                f"  {block:3d} {bar:3d}  {stamp:>8}  "
                f"T{event.track}  {event.sample_id:04X}  "
                f"{event.label:<24s}")
            if span > 1:
                line += f" x{span}"
            lines.append(line.rstrip())
        return lines
