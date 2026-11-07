"""Dance eJay 2.0 ``.MIX`` format implementation."""

from __future__ import annotations

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
from .dance2_event_builder import Dance2EventBuilder
from .dance2_mix_data import Dance2MixData
from .dance2_reader import MIX_MAGIC, Dance2Reader
from .dance2_sample_collector import Dance2SampleCollector

DEFAULT_BPM = 140.0


class Dance2MixFormat(MixFormat):
    """Dance eJay 2.0: a text catalog plus a 17-track event table."""

    name = "dance2"
    version = "1.0.0"

    def matches(self, header: bytes) -> bool:
        """Return True for the ``0x0A19`` Dance eJay 2.0 header."""
        if len(header) < 2:
            return False
        return struct.unpack_from("<H", header, 0)[0] == MIX_MAGIC

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        """Parse the header, catalog, and per-track event table.

        Args:
            path: ``.MIX`` file.
            options: Full player options (unused here).

        Returns:
            A document whose ``payload`` is a
            :class:`~player.formats.dance2.dance2_mix_data.Dance2MixData`.

        Raises:
            FormatError: The magic, footer, or a section is bad.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc
        payload = Dance2Reader().read(data, path.name)

        placements = [
            Placement(
                track=event.track,
                bar=event.bar,
                sample_id=event.sample_id,
                span=0.0,
                parameters={
                    "units": event.units,
                    "flag": event.flag,
                    "long": event.long,
                    "extension": event.extension.hex(),
                },
            )
            for event in payload.sample_events
        ]
        title = " - ".join(
            part for part in (payload.title, payload.description) if part)
        return MixDocument(
            source=path,
            format_name=self.name,
            title=title,
            tempo_bpm=payload.bpm,
            placements=placements,
            payload=payload,
            metadata={
                "subtitle": payload.subtitle,
                "description": payload.description,
                "catalog": payload.catalog_name,
                "kits": len(payload.kits),
                "palette": len(payload.palette),
                "text_events": len(payload.text_events),
            },
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        """Resolve ids through ``DANCE20.INF`` and the add-on indexes."""
        return Dance2SampleCollector().collect(document, options)

    def prepare_events(self, document: MixDocument, samples: SampleBank,
                       options: Mapping[str, Any]) -> PlaybackPlan:
        """Position one-shots and build the stereo plan.

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
        return Dance2EventBuilder().build(document, samples, bpm)

    def describe(self, document: MixDocument, samples: SampleBank,
                 plan: PlaybackPlan) -> list[str]:
        """Render the Dance eJay 2.0 event table."""
        details = plan.details
        lines = [
            f"  {details.get('bpm', DEFAULT_BPM):g} bpm  "
            f"{details.get('placements', len(plan.events))} placements  "
            f"{details.get('text_events', 0)} text events",
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
