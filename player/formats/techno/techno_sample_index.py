"""Reading the Techno eJay ``RAVE20.INF`` sample index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...pxd.sample_error import SampleError
from ...pxd.sample_ref import SampleRef

SECTION = "[SAMPLES]"
RECORD_LINES = 12


@dataclass
class TechnoSampleIndex:
    """``RAVE20.INF`` records keyed by the id the mix references.

    Attributes:
        samples: References without an archive path; the collector adds it.
    """

    samples: dict[int, SampleRef]

    @classmethod
    def read(cls, path: Path) -> "TechnoSampleIndex":
        """Read the ``[SAMPLES]`` section.

        Args:
            path: Path to ``RAVE20.INF``.

        Returns:
            The parsed index.

        Raises:
            SampleError: The file is unreadable, has no section, or has no
                usable records.
        """
        try:
            lines = path.read_text(encoding="latin-1").splitlines()
        except OSError as exc:
            raise SampleError(f"{path}: {exc.strerror or exc}") from exc
        try:
            start = lines.index(SECTION) + 1
        except ValueError as exc:
            raise SampleError(f"{path}: no {SECTION} section") from exc

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
                part1 = _unquote(record[6])
                bars = int(record[8])
            except (IndexError, ValueError):
                continue
            label = " ".join(part for part in (category, part1) if part)
            samples.setdefault(sample_id, SampleRef(
                sample_id=sample_id,
                name=name,
                label=label,
                offset=offset,
                size=size,
                bars=bars,
                parameters={"category": category, "part": part1},
            ))
        if not samples:
            raise SampleError(f"{path}: no sample records after {SECTION}")
        return cls(samples)

    def get(self, sample_id: int) -> SampleRef | None:
        """Return the record for ``sample_id``, if any."""
        return self.samples.get(sample_id)

    def __len__(self) -> int:
        return len(self.samples)


def _unquote(text: str) -> str:
    """Strip the quotes ``RAVE20.INF`` puts around its strings."""
    return text.strip().strip('"')
