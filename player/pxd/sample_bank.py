"""Sample streams keyed by the format's sample id."""

from __future__ import annotations

import array
from dataclasses import dataclass, field

from .sample_stream import SampleStream


@dataclass
class SampleBank:
    """Mono int16 sample streams at the player's sample rate.

    Entries store their declared frame count before playback, so a format can
    position events without decoding anything.  The PCM is decoded in
    block-sized windows, which is what streams a mix instead of decoding it
    at load.

    Attributes:
        pcm: Sample streams keyed by id.
        labels: Display labels carried over from the sample references.
        errors: One message per sample that could not be read or decoded.
    """

    pcm: dict[int, SampleStream] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, sample_id: int, samples: array.array,
            label: str = "") -> None:
        """Store already-decoded ``samples`` and their display label."""
        self.add_stream(SampleStream(sample_id, len(samples), pcm=samples),
                        label)

    def add_stream(self, stream: SampleStream, label: str = "") -> None:
        """Store ``stream`` and its display label."""
        self.pcm[stream.sample_id] = stream
        if label:
            self.labels[stream.sample_id] = label

    def get(self, sample_id: int) -> SampleStream | None:
        """Return the stream for ``sample_id``, if any."""
        return self.pcm.get(sample_id)

    def close(self) -> None:
        """Close decoder handles held by the streams."""
        for stream in self.pcm.values():
            stream.close()

    def label_for(self, sample_id: int) -> str:
        """Display label, falling back to the hexadecimal id."""
        return self.labels.get(sample_id, f"0x{sample_id:04X}")

    @property
    def ids(self) -> list[int]:
        """Sorted sample ids in the bank."""
        return sorted(self.pcm)

    def __contains__(self, sample_id: object) -> bool:
        return sample_id in self.pcm

    def __len__(self) -> int:
        return len(self.pcm)
