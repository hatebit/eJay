"""Reading and locating the Dance eJay sample catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...pxd.sample_error import SampleError
from .dance_sample_entry import DanceSampleEntry

ID_OFFSET = 731
HEADER_LINES = 18
RECORD_LINES = 4
NEW_RECORD_LINES = 6
PATH_KEY_OFFSET = 3

# (sample id base, first row in the new MAX, usable row count)
HIGH_ID_BANKS = (
    (3400, 1352, 423),
    (3900, 1775, 520),
    (4500, 2295, 550),
)

# (catalog folder, catalog name, path list name)
CATALOG_LAYOUTS = (
    ("DMACHINE", "PXD.TXT", "MAX.TXT"),
    ("EJAY", "PXDDANCE", "MAX"),
)
CATALOG_FOLDERS = tuple(layout[0] for layout in CATALOG_LAYOUTS)


@dataclass
class DanceSampleIndex:
    """The catalog records and the paths their keys point at.

    Attributes:
        entries: The 1,352 base catalog records in file order.
        paths: The path list (``MAX.TXT`` or ``MAX``).
        banks: High-ID bank rows; empty for the old catalog.
        kind: ``"old"`` for ``PXD.TXT``, ``"new"`` for ``PXDDANCE``.
    """

    entries: list[DanceSampleEntry]
    paths: tuple[str, ...]
    banks: tuple[tuple[int, int, int], ...] = ()
    kind: str = "old"

    @classmethod
    def read(cls, catalog_path: Path,
             paths_path: Path) -> "DanceSampleIndex":
        """Read a ``PXD.TXT``/``MAX.TXT`` or ``PXDDANCE``/``MAX`` pair.

        Args:
            catalog_path: Path to ``DMACHINE/PXD.TXT`` or ``EJAY/PXDDANCE``.
            paths_path: Path to the matching path list.

        Returns:
            The parsed catalog.

        Raises:
            SampleError: A file cannot be read, or a record or key is bad.
        """
        lines = _quoted_lines(catalog_path)
        if not lines:
            raise SampleError(f"{catalog_path}: catalog is empty")

        paths = tuple(_read_paths(paths_path))
        if not paths:
            raise SampleError(f"{paths_path}: path list is empty")

        if _is_legacy_catalog(lines):
            return cls._read_legacy(catalog_path, lines, paths)
        return cls._read_new(catalog_path, lines, paths)

    @classmethod
    def _read_legacy(cls, catalog_path: Path, lines: list[str],
                     paths: tuple[str, ...]) -> "DanceSampleIndex":
        """Read the 18-header-value, four-line ``PXD.TXT`` shape."""
        if len(lines) < HEADER_LINES + RECORD_LINES:
            raise SampleError(f"{catalog_path}: catalog is truncated")
        if (len(lines) - HEADER_LINES) % RECORD_LINES:
            raise SampleError(
                f"{catalog_path}: catalog does not end on a whole record")

        entries: list[DanceSampleEntry] = []
        for index in range((len(lines) - HEADER_LINES) // RECORD_LINES):
            start = HEADER_LINES + index * RECORD_LINES
            record = lines[start:start + RECORD_LINES]
            key_text, bars_text, name1, name2 = record
            try:
                key = int(key_text)
                bars = int(bars_text)
            except ValueError as exc:
                raise SampleError(
                    f"{catalog_path}: record {index} has a bad key or length"
                ) from exc

            path_index = (key & 0xFFFF) - PATH_KEY_OFFSET
            if not 0 <= path_index < len(paths):
                raise SampleError(
                    f"{catalog_path}: record {index} points at "
                    f"MAX.TXT line {path_index + 1}, but the list has "
                    f"{len(paths)} lines")
            entries.append(DanceSampleEntry(
                key=key,
                bars=bars,
                name1=name1,
                name2=name2,
                path=paths[path_index],
                path_index=path_index,
            ))
        return cls(entries=entries, paths=paths)

    @classmethod
    def _read_new(cls, catalog_path: Path, lines: list[str],
                  paths: tuple[str, ...]) -> "DanceSampleIndex":
        """Read the six-line ``PXDDANCE`` shape."""
        if len(lines) % NEW_RECORD_LINES:
            raise SampleError(
                f"{catalog_path}: catalog does not end on a whole record")

        entries: list[DanceSampleEntry] = []
        for index in range(len(lines) // NEW_RECORD_LINES):
            start = index * NEW_RECORD_LINES
            record = lines[start:start + NEW_RECORD_LINES]
            path, _unused, _category, bars_text, name1, name2 = record
            try:
                bars = int(bars_text)
            except ValueError as exc:
                raise SampleError(
                    f"{catalog_path}: record {index} has a bad length"
                ) from exc
            if not path:
                raise SampleError(
                    f"{catalog_path}: record {index} has no path")
            entries.append(DanceSampleEntry(
                key=0,
                bars=bars,
                name1=name1,
                name2=name2,
                path=path,
                path_index=index,
            ))
        return cls(entries=entries, paths=paths,
                   banks=HIGH_ID_BANKS, kind="new")

    def entry_for(self, sample_id: int) -> DanceSampleEntry | None:
        """Resolve a base or high sample id to one catalog entry."""
        position = sample_id - ID_OFFSET
        if 0 <= position < len(self.entries):
            return self.entries[position]

        for base, start, count in self.banks:
            if base <= sample_id < base + count:
                path_index = start + sample_id - base
                if path_index < len(self.paths):
                    path = self.paths[path_index]
                    return DanceSampleEntry(
                        key=0,
                        bars=0,
                        name1=_path_stem(path),
                        name2="",
                        path=path,
                        path_index=path_index,
                    )
        return None

    def __len__(self) -> int:
        return len(self.entries)


def _is_legacy_catalog(lines: list[str]) -> bool:
    """Return True when the first quoted value is a numeric catalog key."""
    try:
        int(lines[0])
    except (IndexError, ValueError):
        return False
    return True


def _path_stem(relative: str) -> str:
    """Return a display stem from a backslash- or slash-separated path."""
    name = relative.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name


def _quoted_lines(path: Path) -> list[str]:
    """Return the contents of every double-quoted line in ``path``.

    Raises:
        SampleError: The file cannot be read.
    """
    try:
        text = path.read_bytes().decode("latin-1")
    except OSError as exc:
        raise SampleError(f"{path}: {exc.strerror or exc}") from exc
    return [line[1:-1] for line in text.splitlines()
            if len(line) >= 2 and line.startswith('"') and line.endswith('"')]


def _read_paths(path: Path) -> list[str]:
    """Read quoted ``MAX.TXT`` lines or raw ``MAX`` lines.

    Raises:
        SampleError: The file cannot be read.
    """
    try:
        text = path.read_bytes().decode("latin-1")
    except OSError as exc:
        raise SampleError(f"{path}: {exc.strerror or exc}") from exc
    lines = text.splitlines()
    quoted = [line[1:-1] for line in lines
              if len(line) >= 2 and line.startswith('"') and line.endswith('"')]
    if quoted:
        return quoted
    return [line for line in lines if line.strip()]


def default_paths(catalog_path: Path) -> Path:
    """Return the path-list file that belongs to ``catalog_path``."""
    name = catalog_path.name.upper()
    if name == "PXDDANCE":
        return catalog_path.with_name("MAX")
    return catalog_path.with_name("MAX.TXT")


def root_for_catalog(catalog_path: Path) -> Path:
    """Return the sample root implied by an explicit catalog path.

    Args:
        catalog_path: Path to ``DMACHINE/PXD.TXT`` or ``EJAY/PXDDANCE``, or
            to a catalog stored directly in the sample folder.

    Returns:
        The folder the catalog's relative sample paths resolve under.
    """
    folder = catalog_path.parent
    if folder.name.upper() in CATALOG_FOLDERS:
        return folder.parent
    return folder


def find_catalog(mix_path: Path) -> tuple[Path, Path, Path] | None:
    """Look for either Dance catalog near the mix.

    Args:
        mix_path: Mix file being played.

    Returns:
        ``(catalog, path_list, resource_root)``, or None when no candidate
        exists.
    """
    here = mix_path.resolve().parent
    candidates = [
        here / "DANCE",
        here.parent / "DANCE",
        here.parent.parent / "DANCE",
        here,
        here.parent,
        Path.cwd(),
        Path.cwd() / "DANCE",
    ]
    for root in candidates:
        found = catalog_in(root)
        if found is not None:
            return found
    return None


def catalog_in(root: Path) -> tuple[Path, Path, Path] | None:
    """Find a catalog under ``root`` or directly in a catalog folder."""
    for folder, catalog_name, paths_name in CATALOG_LAYOUTS:
        catalog = root / folder / catalog_name
        paths = root / folder / paths_name
        if catalog.is_file() and paths.is_file():
            return catalog, paths, root
    for _folder, catalog_name, paths_name in CATALOG_LAYOUTS:
        catalog = root / catalog_name
        paths = root / paths_name
        if catalog.is_file() and paths.is_file():
            return catalog, paths, root.parent
    return None


def resolve_sample(res_root: Path, relative: str) -> Path | None:
    """Resolve a catalog path under ``res_root``, ignoring letter case.

    Args:
        res_root: Dance eJay folder holding the sample subfolders.
        relative: Backslash- or slash-separated catalog path.

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
