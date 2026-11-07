"""Resolve Dance eJay 2.0 sample ids across the four kit archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_error import SampleError
from .dance2_sample_index import Dance2SampleIndex

INDEX_NAME = "DANCE20.INF"
INDEX_STEMS = ("DANCE20", "DANCESK4", "DANCESK5", "DANCESK6")


class Dance2SampleCollector:
    """Turn a Dance eJay 2.0 document's ids into archive references."""

    def collect(self, document: MixDocument,
                options: Mapping[str, Any]) -> SampleCollection:
        """Resolve every id through the indices found beside the archives.

        The base kit is ``DANCE20``; ``DANCESK4`` to ``DANCESK6`` hold the
        add-on kits.  Their id ranges are disjoint, so the event's flag only
        matters for the UI, not for resolution.

        Args:
            document: Parsed Dance eJay 2.0 mix.
            options: Full player options; ``pxd`` names the folder holding
                the archives and ``index`` one specific ``.INF`` file.

        Returns:
            References into the archives, plus one error per id that could
            not be resolved or whose archive is missing.

        Raises:
            SampleError: No index can be found or read, or no archive exists.
        """
        index_option = options.get("index")
        pxd_option = options.get("pxd")
        if index_option:
            index_path = Path(index_option)
            root = Path(pxd_option) if pxd_option else index_path.parent
        else:
            root = _find_root(document.source.parent, None)
        index = _read_indices(root, index_option)

        archives = {
            ref.archive for ref in index.samples.values()
            if ref.archive is not None
        }
        if not any(archive.is_file() for archive in archives):
            raise SampleError(f"{root}: no Dance eJay sample archives found")

        collection = SampleCollection()
        seen: set[int] = set()
        for placement in document.placements:
            sample_id = placement.sample_id
            if sample_id in seen:
                continue
            seen.add(sample_id)

            ref = index.get(sample_id)
            if ref is None:
                collection.errors.append(
                    f"id {sample_id}: not in {INDEX_NAME} or the add-on kits")
                continue
            if ref.archive is None or not ref.archive.is_file():
                name = ref.archive.name if ref.archive else "sample"
                collection.errors.append(
                    f"id {sample_id}: {name} archive not found")
                continue
            collection.add(ref)
        return collection


def _find_root(mix_dir: Path, pxd_option: Any) -> Path:
    """Locate the folder holding ``DANCE20.INF``.

    Args:
        mix_dir: Folder containing the mix file.
        pxd_option: The ``--pxd`` value, when given.

    Returns:
        The folder that holds the indexes and archives.

    Raises:
        SampleError: No candidate folder contains ``DANCE20.INF``.
    """
    if pxd_option:
        candidates = [Path(pxd_option)]
    else:
        candidates = [
            mix_dir,
            mix_dir / "PXD",
            mix_dir.parent / "PXD",
            mix_dir.parent / "EJAY" / "PXD",
            mix_dir.parent / "D_ejay2" / "PXD",
            Path.cwd(),
            Path.cwd() / "PXD",
        ]
    for candidate in candidates:
        if (candidate / INDEX_NAME).is_file():
            return candidate
    for candidate in candidates:
        try:
            children = sorted(candidate.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if (child / INDEX_NAME).is_file():
                return child
            if (child / "PXD" / INDEX_NAME).is_file():
                return child / "PXD"
    searched = ", ".join(str(path) for path in candidates)
    raise SampleError(f"{INDEX_NAME} not found (looked in {searched})")


def _read_indices(root: Path, index_option: Any) -> Dance2SampleIndex:
    """Read the explicit index plus every known index in ``root``.

    Args:
        root: Folder holding the ``.INF`` files.
        index_option: The ``--index`` value, when given.

    Returns:
        One merged index.

    Raises:
        SampleError: An explicit index cannot be read, or no index exists.
    """
    index = Dance2SampleIndex({})
    if index_option:
        index.merge(Dance2SampleIndex.read(Path(index_option)))
    for stem in INDEX_STEMS:
        path = root / f"{stem}.INF"
        if path.is_file():
            index.merge(Dance2SampleIndex.read(path))
    if not len(index):
        raise SampleError(f"{root}: no Dance eJay sample indexes found")
    return index
