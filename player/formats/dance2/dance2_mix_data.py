"""Format-specific facts kept from a parsed Dance eJay 2.0 mix."""

from __future__ import annotations

from dataclasses import dataclass

from .dance2_kit import Dance2Kit
from .dance2_palette_entry import Dance2PaletteEntry
from .dance2_sample_event import Dance2SampleEvent
from .dance2_text_event import Dance2TextEvent
from .dance2_track_settings import Dance2TrackSettings


@dataclass(frozen=True)
class Dance2MixData:
    """Everything a Dance eJay 2.0 mix stores before samples are resolved.

    Attributes:
        header: The eight little-endian header words.
        bpm: Tempo from header word 4.
        tempo_aux: Header word 5, 140 in most files and 136-152 overall.
        title: Short title stored at offset ``0x10``.
        subtitle: The ``#SKKENNUNG#`` signature line.
        description: Mix name stored in the length-prefixed block.
        catalog_name: Sample-catalog version string.
        catalog_count: Number of kit records that follow the catalog header.
        kits: The kit records, including empty trailing rows.
        palette: The ten-slot sample palette.
        track_settings: Pan/volume pairs for tracks 1 to 16.
        song_settings: The 22 opaque song-settings bytes.
        sample_events: Triggers on tracks 1 to 16.
        text_events: Lyric records on track 17.
    """

    header: tuple[int, ...]
    bpm: float
    tempo_aux: int
    title: str
    subtitle: str
    description: str
    catalog_name: str
    catalog_count: int
    kits: tuple[Dance2Kit, ...]
    palette: tuple[Dance2PaletteEntry, ...]
    track_settings: tuple[Dance2TrackSettings, ...]
    song_settings: bytes
    sample_events: tuple[Dance2SampleEvent, ...]
    text_events: tuple[Dance2TextEvent, ...]

    @property
    def event_count(self) -> int:
        """Number of sample triggers on tracks 1 to 16."""
        return len(self.sample_events)

    @property
    def track_count(self) -> int:
        """Number of track blocks, including the text track."""
        return 17
