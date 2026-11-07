"""Read the Hiphop eJay ``EJAY/PXD`` sample catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...pxd.sample_error import SampleError
from .hiphop_sample_entry import HiphopSampleEntry

ID_OFFSET = 731
RECORD_LINES = 6


@dataclass
class HiphopSampleIndex:
    """The Hiphop sample catalog: 1,341 records of 6 quoted lines each.

    Attributes:
        entries: The 1,341 base catalog records in file order.
        paths: The .pxd filename from each record's field 0.
    """

    entries: list[HiphopSampleEntry]
    paths: tuple[str, ...]

    @classmethod
    def read(cls, pxd_path: Path) -> "HiphopSampleIndex":
        """Read the Hiphop ``EJAY/PXD`` catalog.

        The catalog holds one record per sample: a path, an unused field,
        a category word, a bar length, and two name lines.

        Args:
            pxd_path: Path to ``EJAY/PXD`` under the eJay install root.

        Returns:
            The parsed catalog.

        Raises:
            SampleError: The file cannot be read, or a record is bad.
        """
        try:
            text = pxd_path.read_bytes().decode("latin-1")
        except OSError as exc:
            raise SampleError(f"{pxd_path}: {exc.strerror or exc}") from exc

        # The catalog is CRLF-terminated, so strip each line before the
        # surrounding quote marks.
        lines = [line[1:-1] for line in text.splitlines()
                 if len(line) >= 2 and line.startswith('"')
                 and line.endswith('"')]
        if not lines:
            raise SampleError(f"{pxd_path}: catalog is empty")

        entries: list[HiphopSampleEntry] = []
        paths: list[str] = []
        for index in range(len(lines) // RECORD_LINES):
            start = index * RECORD_LINES
            record = lines[start:start + RECORD_LINES]
            if len(record) < RECORD_LINES:
                raise SampleError(
                    f"{pxd_path}: catalog does not end on a whole record")

            path = record[0]
            if not path:
                raise SampleError(
                    f"{pxd_path}: record {index} has no path")
            paths.append(path)

            try:
                bars = int(record[3])
            except ValueError as exc:
                raise SampleError(
                    f"{pxd_path}: record {index} has a bad length"
                ) from exc

            entries.append(HiphopSampleEntry(
                path=path,
                bars=bars,
                name1=record[4],
                name2=record[5],
                path_index=index,
            ))

        return cls(
            entries=entries,
            paths=tuple(paths),
        )

    def entry_for(self, sample_id: int) -> HiphopSampleEntry | None:
        """Resolve a sample id to one catalog entry.

        The base ID range is 731--2071 (1,341 records), so the record
        index is ``sample_id - 731``.
        """
        position = sample_id - ID_OFFSET
        if 0 <= position < len(self.entries):
            return self.entries[position]
        return None

    def __len__(self) -> int:
        return len(self.entries)
