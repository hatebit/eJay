"""One audible placement, already positioned in output frames."""

from __future__ import annotations

import array
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .pxd.sample_stream import SampleStream


@dataclass(slots=True)
class PlaybackEvent:
    """A decoded sample placed on the output timeline.

    ``end`` is the last frame at which the event is audible, not necessarily
    the end of its PCM: the Rave builder cuts an earlier sample when the final
    record takes over.  A looping event repeats its PCM until ``end``.

    Attributes:
        start: First output frame.
        end: One past the last output frame the event may sound on.
        pcm: Mono int16 sample, or a stream that decodes as it plays.
        sample_id: Id from the mix file.
        track: 1-based track number, or a format-specific label.
        left_gain: Gain applied to the left channel.
        right_gain: Gain applied to the right channel.
        loop: Repeat ``pcm`` to fill ``start``..``end`` when True.
        label: Display label for verbose output and listings.
        parameters: Format-specific extras used by listings.
    """

    start: int
    end: int
    pcm: "array.array | SampleStream"
    sample_id: int
    track: int | str = 0
    left_gain: float = 1.0
    right_gain: float = 1.0
    loop: bool = False
    label: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> int:
        """Number of PCM frames in the sample."""
        return len(self.pcm)

    @property
    def duration(self) -> int:
        """Number of output frames the event may sound on."""
        return self.end - self.start
