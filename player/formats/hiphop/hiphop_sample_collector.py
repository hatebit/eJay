"""Resolve Hiphop sample ids to standalone .pxd files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_error import SampleError
from ...pxd.sample_ref import SampleRef
from .hiphop_sample_index import HiphopSampleIndex

RES_FOLDER = "HIPHOP"
CATALOG_FOLDER = "EJAY"
CATALOG_NAME = "PXD"


class HiphopSampleCollector:
    """Turn a Hiphop document's sample ids into file references."""

    def collect(self, document: MixDocument,
                options: Mapping[str, Any]) -> SampleCollection:
        """Resolve every id the document references.

        Args:
            document: Parsed Hiphop mix.
            options: Full player options (``pxd`` and ``index``).

        Returns:
            References for the samples that exist, plus one error per id that
            could not be resolved.

        Raises:
            SampleError: The catalog cannot be found or read.
        """
        index_option = options.get("index")
        pxd_option = options.get("pxd")

        if index_option:
            catalog_path = Path(index_option)
            sample_root = (Path(pxd_option) if pxd_option
                           else catalog_path.parent.parent)
        else:
            pxd_root = (Path(pxd_option) if pxd_option
                        else document.source.resolve().parent.parent)
            found = _find_catalog(pxd_root)
            if found is None:
                raise SampleError(
                    f"cannot find the Hiphop eJay catalog "
                    f"({CATALOG_FOLDER}/{CATALOG_NAME}); "
                    f"pass --pxd or --index")
            catalog_path, sample_root = found
        index = HiphopSampleIndex.read(catalog_path)

        collection = SampleCollection()
        seen: set[int] = set()
        for placement in document.placements:
            sample_id = placement.sample_id
            if sample_id in seen:
                continue
            seen.add(sample_id)

            entry = index.entry_for(sample_id)
            if entry is None:
                collection.errors.append(
                    f"sample 0x{sample_id:03X}: not found in catalog")
                continue

            expected = sample_root / entry.path.replace("\\", "/")
            path = _resolve_sample(sample_root, entry.path)
            if path is None:
                collection.errors.append(
                    f"sample 0x{sample_id:03X} ({expected}): "
                    "not found on disk")
                continue

            label = f"{entry.name1} {entry.name2}".strip()
            collection.add(SampleRef(
                sample_id=sample_id,
                name=label,
                label=label,
                path=path,
                bars=entry.bars,
                parameters={
                    "path_index": entry.path_index,
                    "catalog_path": str(catalog_path),
                },
            ))
        return collection


def _find_catalog(res_root: Path) -> tuple[Path, Path] | None:
    """Find ``EJAY/PXD`` under a HIPHOP folder or its disc folder.

    Args:
        res_root: ``--pxd`` value or the folder above the mix.

    Returns:
        ``(catalog_path, sample_root)``, where ``sample_root`` is the folder
        the catalog paths are relative to, or None.
    """
    for root in (res_root, res_root / RES_FOLDER):
        catalog = root / CATALOG_FOLDER / CATALOG_NAME
        if catalog.is_file():
            return catalog, root
    return None


def _resolve_sample(sample_root: Path, relative: str) -> Path | None:
    """Resolve a catalog path under ``sample_root``, ignoring case.

    Args:
        sample_root: Folder the catalog paths are relative to (``HIPHOP``).
        relative: Backslash- or slash-separated catalog path.

    Returns:
        The existing file, or None.
    """
    path = sample_root
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
