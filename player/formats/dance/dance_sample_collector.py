"""Resolve Dance sample ids to standalone ``.pxd`` files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_error import SampleError
from ...pxd.sample_ref import SampleRef
from .dance_sample_index import (
    DanceSampleIndex,
    catalog_in,
    default_paths,
    find_catalog,
    resolve_sample,
    root_for_catalog,
)


class DanceSampleCollector:
    """Turn a Dance document's sample ids into file references."""

    def collect(self, document: MixDocument,
                options: Mapping[str, Any]) -> SampleCollection:
        """Resolve every id the document references.

        Args:
            document: Parsed Dance mix.
            options: Full player options (``pxd`` and ``index``).

        Returns:
            References for the samples that exist, plus one error per id that
            could not be resolved.

        Raises:
            SampleError: The catalog or path list cannot be found or read.
        """
        catalog_path, paths_path, pxd_root = self._locations(
            document, options)
        index = DanceSampleIndex.read(catalog_path, paths_path)

        collection = SampleCollection()
        seen: set[int] = set()
        for placement in document.placements:
            sample_id = placement.sample_id
            if sample_id in seen:
                continue
            seen.add(sample_id)

            entry = index.entry_for(sample_id)
            expected = (pxd_root / entry.path) if entry is not None else None
            path = (resolve_sample(pxd_root, entry.path)
                    if entry is not None else None)
            if path is None:
                if expected is not None:
                    collection.errors.append(
                        f"sample 0x{sample_id:03X} ({expected}): not found")
                else:
                    collection.errors.append(
                        f"sample 0x{sample_id:03X}: not found")
                continue

            collection.add(SampleRef(
                sample_id=sample_id,
                name=entry.name,
                label=entry.name,
                path=path,
                bars=entry.bars,
                parameters={
                    "catalog_key": entry.key,
                    "path_index": entry.path_index,
                    "catalog_path": str(catalog_path),
                    "catalog_kind": index.kind,
                },
            ))
        return collection

    @staticmethod
    def _locations(document: MixDocument,
                   options: Mapping[str, Any]) -> tuple[Path, Path, Path]:
        """Return ``(catalog_path, paths_path, pxd_root)``."""
        index_option = options.get("index")
        pxd_option = options.get("pxd")

        if index_option:
            catalog_path = Path(index_option)
            paths_path = default_paths(catalog_path)
            pxd_root = (Path(pxd_option) if pxd_option
                        else root_for_catalog(catalog_path))
        elif pxd_option:
            pxd_root = Path(pxd_option)
            found = catalog_in(pxd_root) or catalog_in(pxd_root.parent)
            if found is None:
                raise SampleError(
                    "cannot find the Dance eJay catalog "
                    "(DMACHINE/PXD.TXT or EJAY/PXDDANCE); "
                    "pass --index")
            catalog_path, paths_path, pxd_root = found
        else:
            found = find_catalog(document.source)
            if found is None:
                raise SampleError(
                    "cannot find the Dance eJay catalog "
                    "(DMACHINE/PXD.TXT or EJAY/PXDDANCE); "
                    "pass --pxd or --index")
            catalog_path, paths_path, pxd_root = found

        if not catalog_path.is_file():
            raise SampleError(f"{catalog_path}: sample catalog not found")
        if not paths_path.is_file():
            raise SampleError(f"{paths_path}: sample path list not found")
        return catalog_path, paths_path, pxd_root
