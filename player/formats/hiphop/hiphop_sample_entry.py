"""One record of the Hiphop eJay sample catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HiphopSampleEntry:
    """One record from the Hiphop ``EJAY/PXD`` catalog.

    Attributes:
        path: Relative sample path, for example ``aa\\h1bs001.pxd``.
        bars: Catalog length in bars.
        name1: Sample name, part 1.
        name2: Sample name, part 2, often empty.
        path_index: Zero-based record index in the catalog.
    """

    path: str
    bars: int
    name1: str
    name2: str
    path_index: int
