"""Format-specific facts kept from a parsed Techno eJay mix."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TechnoMixData:
    """Header, title, and table counts of one Techno mix.

    Attributes:
        header: The eight little-endian header words.
        bpm: Tempo from header word 4, or the default.
        title: Mix name from the text block.
        track_count: Number of track blocks in the event table.
        event_count: Number of placements read.
    """

    header: tuple[int, ...]
    bpm: float
    title: str
    track_count: int
    event_count: int
