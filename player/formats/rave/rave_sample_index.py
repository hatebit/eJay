"""Reading and locating the Rave eJay ``EJAY/PXD`` sample list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...pxd.sample_error import SampleError
from .rave_sample_entry import RaveSampleEntry

ID_OFFSET = 731
RECORD_LINES = 6


@dataclass
class RaveSampleIndex:
    """The six-lines-per-record sample list.

    Attributes:
        entries: Records in file order.
    """

    entries: list[RaveSampleEntry]

    @classmethod
    def read(cls, path: Path) -> "RaveSampleIndex":
        """Read the quoted, CRLF, six-lines-per-record sample list.

        Args:
            path: Path to ``EJAY/PXD``.

        Returns:
            The parsed index.

        Raises:
            SampleError: The file cannot be read.
        """
        try:
            text = path.read_bytes().decode("latin-1")
        except OSError as exc:
            raise SampleError(f"{path}: {exc.strerror or exc}") from exc

        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        entries: list[RaveSampleEntry] = []
        for start in range(0, len(lines) - RECORD_LINES + 1, RECORD_LINES):
            fields = [value.strip().strip('"')
                      for value in lines[start:start + RECORD_LINES]]
            if not fields[0]:
                continue
            name = " ".join(value for value in fields[4:] if value)
            entries.append(RaveSampleEntry(
                path=fields[0],
                category=fields[2],
                number=fields[3],
                name=name,
            ))
        return cls(entries)

    def entry_for(self, sample_id: int) -> RaveSampleEntry | None:
        """Resolve ``sample_id`` through the ``sample_id - 731`` rule."""
        position = sample_id - ID_OFFSET
        if 0 <= position < len(self.entries):
            return self.entries[position]
        return None

    def __len__(self) -> int:
        return len(self.entries)


def find_index(mix_path: Path) -> Path | None:
    """Look for ``EJAY/PXD`` next to the mix, above it, or in the cwd.

    Args:
        mix_path: Mix file being played.

    Returns:
        The index path, or None when no candidate exists.
    """
    here = mix_path.resolve().parent
    candidates = [
        here,
        here / "disk" / "RAVE",
        here.parent,
        here.parent.parent,
        Path.cwd(),
        Path.cwd() / "disk" / "RAVE",
    ]
    for base in candidates:
        path = base / "EJAY" / "PXD"
        if path.is_file():
            return path
    return None


def resolve_sample(res_root: Path, relative: str) -> Path | None:
    """Resolve an index path under ``res_root``, ignoring letter case.

    Args:
        res_root: eJay install folder.
        relative: Backslash- or slash-separated index path.

    Returns:
        The existing file, or None.
    """
    path = res_root
    for part in relative.replace("\\", "/").split("/"):
        if not part:
            continue
        try:
            names = list(path.iterdir())
        except OSError:
            return None
        match = None
        for candidate in names:
            if candidate.name == part:
                match = candidate
                break
        if match is None:
            for candidate in names:
                if candidate.name.lower() == part.lower():
                    match = candidate
                    break
        if match is None:
            return None
        path = match
    return path if path.is_file() else None
