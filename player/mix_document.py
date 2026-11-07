"""Parsed, format-neutral view of one mix file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .placement import Placement


@dataclass
class MixDocument:
    """The result of parsing a mix, before samples are collected.

    ``placements`` is the common view used for listings and for simple
    formats.  ``payload`` keeps the raw format-specific structure (for example
    the Rave grid records) so the format's event builder can apply rules the
    neutral view cannot express.

    Attributes:
        source: File the document was read from.
        format_name: Name of the :class:`MixFormat` that parsed it.
        title: Human-readable title, often the stored version string.
        tempo_bpm: Tempo stored in the file, or None when the format has none.
        placements: Sample cells in file order.
        payload: Format-specific parsed data.
        metadata: Small format-specific facts for listings and debugging.
    """

    source: Path
    format_name: str
    title: str = ""
    tempo_bpm: float | None = None
    placements: list[Placement] = field(default_factory=list)
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_bars(self) -> float:
        """Musical length implied by the placements, in bars."""
        if not self.placements:
            return 0.0
        return max(p.end_bar for p in self.placements) - 1.0

    @property
    def display_name(self) -> str:
        """Title when the file has one, otherwise the file name."""
        return self.title or self.source.name
