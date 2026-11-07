"""Hiphop eJay ``.MIX`` format implementation."""

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
from .hiphop_event_builder import HiphopEventBuilder
from .hiphop_grid import BARS_PER_BLOCK, HiphopGrid
from .hiphop_sample_collector import HiphopSampleCollector

MIX_MAGIC = 0x0A08
GRID_OFFSET = 2
GRID_BLOCKS = 351
GRID_BYTES = GRID_BLOCKS * 32  # 11232
META_OFFSET = GRID_OFFSET + GRID_BYTES  # 11234
# 110,250 frames per bar: the catalog's bar field times the decoded tPxd
# lengths, i.e. 96 BPM at four beats per bar.
DEFAULT_BPM = 96.0


class HiphopMixFormat(MixFormat):
    """Hiphop eJay: 351 two-bar blocks and the ``EJAY/PXD`` catalog.

    The grid is followed by a metadata block and a trailer; both are
    ignored.
    """

    name = "hiphop"
    version = "2.0.1"

    def matches(self, header: bytes) -> bool:
        """Return True for the ``0x0A08`` grid header."""
        if len(header) < 2:
            return False
        return struct.unpack_from("<H", header, 0)[0] == MIX_MAGIC

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        """Parse a Hiphop arrangement grid.

        Args:
            path: ``.MIX`` file.
            options: Full player options (unused here).

        Returns:
            A document whose ``payload`` is a
            :class:`~player.formats.hiphop.hiphop_grid.HiphopGrid`.

        Raises:
            FormatError: The file is shorter than the grid or has the wrong
                magic.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc

        if len(data) < META_OFFSET:
            raise FormatError(
                f"{path.name}: expected at least {META_OFFSET} bytes, "
                f"found {len(data)}")

        header = struct.unpack_from("<H", data, 0)[0]
        if header != MIX_MAGIC:
            raise FormatError(
                f"{path.name}: header 0x{header:04X}, "
                f"expected 0x{MIX_MAGIC:04X}")

        blocks = tuple(
            struct.unpack_from("<16H", data, GRID_OFFSET + index * 32)
            for index in range(GRID_BLOCKS)
        )
        grid = HiphopGrid(header=header, blocks=blocks)
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
                "tracks": 8,
                "min_sample_id": 731,
            },
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        """Resolve the Hiphop ids through ``HIPHOP/EJAY/PXD`` catalog."""
        return HiphopSampleCollector().collect(document, options)

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
        return HiphopEventBuilder().build(document, samples, bpm)

    def describe(self, document: MixDocument, samples: SampleBank,
                 plan: PlaybackPlan) -> list[str]:
        """Render the Hiphop arrangement as a table."""
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