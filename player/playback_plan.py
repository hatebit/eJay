"""Common, ready-to-play description of a whole mix."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import SAMPLE_RATE
from .playback_event import PlaybackEvent


@dataclass
class PlaybackPlan:
    """Everything the common mixer and player need.

    Attributes:
        events: Positioned events, in any order (the mixer sorts them).
        total_frames: Number of output frames to render.
        channels: 1 for mono, 2 for interleaved stereo.
        format_name: Name of the format that produced the plan.
        title: Human-readable title.
        sample_rate: Output rate; every event is already at this rate.
        details: Format-specific facts for the summary and listings.
    """

    events: list[PlaybackEvent]
    total_frames: int
    channels: int
    format_name: str
    title: str = ""
    sample_rate: int = SAMPLE_RATE
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Rendered length in seconds."""
        if self.sample_rate <= 0:
            return 0.0
        return self.total_frames / float(self.sample_rate)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing audible to play."""
        return not self.events or self.total_frames <= 0
