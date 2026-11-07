"""One six-line record of the Rave eJay sample index."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RaveSampleEntry:
    """A sample-list row from ``EJAY/PXD``.

    Attributes:
        path: Relative sample path, e.g. ``bq\\r1bs001.pxd``.
        category: Category string, e.g. ``bass``.
        number: Length in bars, stored as text.
        name: Display name built from the last two index lines.
    """

    path: str
    category: str = ""
    number: str = ""
    name: str = ""
