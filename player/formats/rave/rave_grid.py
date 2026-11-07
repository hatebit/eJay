"""The Rave eJay grid: 16-word records after a one-word header."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

TRACKS = 8
RECORD_WORDS = 16
MIN_SAMPLE_ID = 731


@dataclass(frozen=True)
class RaveGrid:
    """Parsed grid records and the trailer version string.

    Attributes:
        header: Header word, normally ``0x0A07``.
        records: Grid records, each holding 16 sample ids.
        version: Version string from the trailer, e.g. ``Rave eJay 1.01``.
    """

    header: int
    records: tuple[tuple[int, ...], ...]
    version: str = ""

    def used_records(self) -> int:
        """One past the last record that holds a resolvable sample.

        The unused tail is not reliably zero, so only values the index can
        resolve count as content.
        """
        for index in range(len(self.records) - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self.records[index]):
                return index + 1
        return 0

    def cells(self) -> Iterator[tuple[int, str, int, int]]:
        """Yield ``(record, lane, track, sample_id)`` for every sample cell."""
        for record, row in enumerate(self.records):
            for column, sample_id in enumerate(row):
                if sample_id < MIN_SAMPLE_ID:
                    continue
                lane = "A" if column < TRACKS else "B"
                yield record, lane, column % TRACKS + 1, sample_id
