"""One lyric entry from track 17 of a Dance eJay 2.0 mix."""

from __future__ import annotations

from dataclasses import dataclass

UNITS_PER_BAR = 128


@dataclass(frozen=True, slots=True)
class Dance2TextEvent:
    """A word or phrase on the text/vocoder track.

    Track 17 does not reference a sample id.  Its records share the first
    five bytes of the sample-entry framing (flag, time, second) followed by
    22 opaque bytes, a name and a value.  The player preserves them but does
    not render them.

    Attributes:
        units: Position in 128ths of a bar.
        flag: Stored leading byte.
        second: Stored second time field, usually ``-1``.
        prefix: The 22 bytes that follow the five-byte head.
        name: Lyric name without the ``00 01`` terminator.
        value: The following length-prefixed value bytes.
    """

    units: int
    flag: int
    second: int
    prefix: bytes
    name: str
    value: bytes

    @property
    def bar(self) -> float:
        """1-based musical position, in bars."""
        return self.units / float(UNITS_PER_BAR) + 1.0
