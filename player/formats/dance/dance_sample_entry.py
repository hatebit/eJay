"""One resolved record of a Dance eJay sample catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DanceSampleEntry:
    """A catalog row plus the relative path it resolves to.

    Attributes:
        key: Catalog key whose low word selects the path; 0 for a new-catalog
            record or a high-ID bank row.
        bars: Catalog length in bars; 0 for a high-ID bank row.
        name1: Sample name, part 1.
        name2: Sample name, part 2, often empty.
        path: Relative sample path from the catalog or path list.
        path_index: Index of ``path`` in the path list.
    """

    key: int
    bars: int
    name1: str
    name2: str
    path: str
    path_index: int

    @property
    def name(self) -> str:
        """Display name built from the two name fields."""
        return " ".join(value for value in (self.name1, self.name2) if value)
