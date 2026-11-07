"""One sample placement from a Dance eJay 2.0 event table."""

from __future__ import annotations

from dataclasses import dataclass

UNITS_PER_BAR = 128


@dataclass(frozen=True, slots=True)
class Dance2SampleEvent:
    """A sample trigger read from tracks 1 to 16.

    Short entries store the time negated as ``-(units + 1)`` and describe a
    slice; long entries store ``units`` directly and carry a 10-byte
    extension.  ``units`` is the distance from the start of the mix in
    128ths of a bar.

    Attributes:
        track: 1-based sample track.
        units: Position in 128ths of a bar.
        flag: Stored head byte; 0 uses the base kit, 3 an add-on kit.
        sample_id: Sample id referenced by the event.
        long: True when the 17-byte long form stored the event.
        extension: The long form's 10 opaque trailing bytes, or empty.
    """

    track: int
    units: int
    flag: int
    sample_id: int
    long: bool
    extension: bytes = b""

    @property
    def bar(self) -> float:
        """1-based musical position, in bars."""
        return self.units / float(UNITS_PER_BAR) + 1.0
