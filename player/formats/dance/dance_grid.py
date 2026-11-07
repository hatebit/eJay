"""The Dance eJay grid: 351 blocks of two bars and eight tracks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

TRACKS = 8
BARS_PER_BLOCK = 2
BLOCKS = 351
MIN_SAMPLE_ID = 731


@dataclass(frozen=True)
class DanceGrid:
    """Parsed Dance arrangement blocks.

    Attributes:
        header: Header word, normally ``0x0A06``.
        blocks: 351 blocks, each holding 16 sample ids.
    """

    header: int
    blocks: tuple[tuple[int, ...], ...]

    def used_blocks(self) -> int:
        """One past the last block that holds a resolvable sample."""
        for index in range(len(self.blocks) - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self.blocks[index]):
                return index + 1
        return 0

    def used_bars(self) -> int:
        """One past the last bar that holds a resolvable sample."""
        for bar in range(len(self.blocks) * BARS_PER_BLOCK - 1, -1, -1):
            if any(value >= MIN_SAMPLE_ID for value in self._row(bar)):
                return bar + 1
        return 0

    def bars(self) -> Iterator[tuple[int, tuple[int, ...]]]:
        """Yield ``(bar, row)`` for every bar in the arrangement.

        ``bar`` is zero-based and ``row`` holds the eight track cells.
        """
        for block_index, block in enumerate(self.blocks):
            for bar_in_block in range(BARS_PER_BLOCK):
                start = bar_in_block * TRACKS
                yield (block_index * BARS_PER_BLOCK + bar_in_block,
                       block[start:start + TRACKS])

    def cells(self) -> Iterator[tuple[int, int, int]]:
        """Yield ``(bar, track, sample_id)`` for every resolvable cell."""
        for bar, row in self.bars():
            for track, sample_id in enumerate(row, start=1):
                if sample_id >= MIN_SAMPLE_ID:
                    yield bar, track, sample_id

    def _row(self, bar: int) -> tuple[int, ...]:
        block = self.blocks[bar // BARS_PER_BLOCK]
        start = (bar % BARS_PER_BLOCK) * TRACKS
        return block[start:start + TRACKS]
