"""Reading the Dance eJay 2.0 ``.INF`` sample indexes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...pxd.sample_error import SampleError
from ...pxd.sample_ref import SampleRef

SECTION = "[SAMPLES]"
RECORD_LINES = 12


@dataclass
class Dance2SampleIndex:
    """Sample records from one or more ``.INF`` files, keyed by id.

    Attributes:
        samples: References whose ``archive`` is the ``.INF``'s sibling
            file without the extension.
    """

    samples: dict[int, SampleRef]

    @classmethod
    def read(cls, path: Path) -> "Dance2SampleIndex":
        """Read the ``[SAMPLES]`` section of one ``.INF`` file.

        Args:
            path: Path to a file such as ``DANCE20.INF``.

        Returns:
            The parsed index.

        Raises:
            SampleError: The file is unreadable, lacks the section, or has
                no usable records.
        """
        try:
            lines = path.read_text(encoding="latin-1").splitlines()
        except OSError as exc:
            raise SampleError(f"{path}: {exc.strerror or exc}") from exc
        try:
            start = lines.index(SECTION) + 1
        except ValueError as exc:
            raise SampleError(f"{path}: no {SECTION} section") from exc

        archive = path.with_suffix("")
        samples: dict[int, SampleRef] = {}
        end = len(lines) - RECORD_LINES + 1
        for position in range(start, end, RECORD_LINES):
            record = lines[position:position + RECORD_LINES]
            try:
                sample_id = int(record[0])
                name = _unquote(record[2])
                offset = int(record[3])
                size = int(record[4])
                category = _unquote(record[5])
                part = _unquote(record[6])
                bars = int(record[8])
            except (IndexError, ValueError):
                continue
            label = " ".join(
                value for value in (category, part) if value) or name
            samples.setdefault(sample_id, SampleRef(
                sample_id=sample_id,
                name=name,
                label=label,
                archive=archive,
                offset=offset,
                size=size,
                bars=bars,
                parameters={"category": category, "part": part},
            ))
        if not samples:
            raise SampleError(f"{path}: no sample records after {SECTION}")
        return cls(samples)

    def merge(self, other: "Dance2SampleIndex") -> None:
        """Add records from ``other`` without replacing existing ids."""
        for sample_id, ref in other.samples.items():
            self.samples.setdefault(sample_id, ref)

    def get(self, sample_id: int) -> SampleRef | None:
        """Return the record for ``sample_id``, if any."""
        return self.samples.get(sample_id)

    def __len__(self) -> int:
        return len(self.samples)


def _unquote(text: str) -> str:
    """Strip the quotes ``.INF`` puts around its strings."""
    return text.strip().strip('"')
