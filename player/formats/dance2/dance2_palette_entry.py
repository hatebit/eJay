"""One entry of the ten-slot sample palette in a Dance eJay 2.0 mix."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dance2PaletteEntry:
    """A palette slot naming one sample the mix was built from.

    Attributes:
        sample_id: Sample id the slot points at.
        name: Stored sample name without the ``00 01`` terminator.
        first: First opaque 32-bit parameter.
        second: Second opaque 32-bit parameter.
    """

    sample_id: int
    name: str
    first: int
    second: int
