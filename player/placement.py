"""Format-neutral placement of one sample in an arrangement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Placement:
    """One sample cell as the mix file stores it.

    A placement is deliberately format-neutral: a Rave grid cell and a Techno
    event-table entry both become one of these.  The format-specific event
    builder turns a list of placements (or its own raw payload) into
    :class:`~player.playback_event.PlaybackEvent` objects.

    Attributes:
        track: 1-based track number.
        bar: 1-based musical position, in bars.
        sample_id: Numeric id the format uses to reference a sample.
        span: Length in bars when the format stores a run, otherwise zero.
        layer: Optional sub-track label, e.g. the Rave ``A``/``B`` lane.
        parameters: Format-specific extras that the event builder may read.
    """

    track: int
    bar: float
    sample_id: int
    span: float = 0.0
    layer: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def end_bar(self) -> float:
        """One past the last bar the placement covers."""
        return self.bar + self.span
