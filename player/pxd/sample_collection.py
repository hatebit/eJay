"""Container for the sample references a format resolved."""

from __future__ import annotations

from dataclasses import dataclass, field

from .sample_ref import SampleRef


@dataclass
class SampleCollection:
    """References produced by a format's sample-collection stage.

    Attributes:
        refs: References keyed by sample id.
        errors: One message per sample the format could not resolve.
    """

    refs: dict[int, SampleRef] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, ref: SampleRef) -> None:
        """Store ``ref`` under its sample id."""
        self.refs[ref.sample_id] = ref

    def get(self, sample_id: int) -> SampleRef | None:
        """Return the reference for ``sample_id``, if any."""
        return self.refs.get(sample_id)

    @property
    def ids(self) -> list[int]:
        """Sorted sample ids in the collection."""
        return sorted(self.refs)

    def __contains__(self, sample_id: object) -> bool:
        return sample_id in self.refs

    def __len__(self) -> int:
        return len(self.refs)
