"""The four pipeline products held together for one mix."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .mix_document import MixDocument
from .playback_plan import PlaybackPlan
from .pxd.sample_bank import SampleBank

if TYPE_CHECKING:
    from .mix_format import MixFormat


@dataclass
class PlaybackSession:
    """A loaded mix: parsed document, samples, and the prepared plan.

    Attributes:
        mix_format: Format implementation that produced the session.
        document: Parsed mix.
        samples: Sample streams, decoded lazily when playback needs them.
        plan: Ready-to-play events.
        warnings: Non-fatal problems, one message per skipped sample.
        load_seconds: Wall time spent running the whole load pipeline.
        sample_seconds: Wall time spent collecting and decoding samples.
    """

    mix_format: "MixFormat"
    document: MixDocument
    samples: SampleBank
    plan: PlaybackPlan
    warnings: list[str] = field(default_factory=list)
    load_seconds: float = 0.0
    sample_seconds: float = 0.0

    @property
    def duration_seconds(self) -> float:
        """Rendered length in seconds."""
        return self.plan.duration_seconds
