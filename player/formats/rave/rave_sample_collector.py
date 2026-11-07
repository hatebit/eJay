"""Resolve Rave sample ids to standalone ``.pxd``/WAVE files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_error import SampleError
from ...pxd.sample_ref import SampleRef
from .rave_sample_index import RaveSampleIndex, find_index, resolve_sample


class RaveSampleCollector:
    """Turn a Rave document's sample ids into file references."""

    def collect(self, document: MixDocument,
                options: Mapping[str, Any]) -> SampleCollection:
        """Resolve every id the document references.

        Args:
            document: Parsed Rave mix.
            options: Full player options (``pxd`` and ``index``).

        Returns:
            References for the samples that exist, plus one error per id that
            could not be resolved.

        Raises:
            SampleError: The sample index cannot be found or read.
        """
        index_path, pxd_root = self._locations(document, options)
        index = RaveSampleIndex.read(index_path)

        collection = SampleCollection()
        seen: set[int] = set()
        for placement in document.placements:
            sample_id = placement.sample_id
            if sample_id in seen:
                continue
            seen.add(sample_id)

            entry = index.entry_for(sample_id)
            path = (resolve_sample(pxd_root, entry.path)
                    if entry is not None else None)
            if path is None:
                collection.errors.append(
                    f"sample 0x{sample_id:03X}: not found")
                continue

            bars = int(entry.number) if entry.number.isdigit() else 0
            collection.add(SampleRef(
                sample_id=sample_id,
                name=entry.name,
                label=entry.name,
                path=path,
                bars=bars,
                parameters={
                    "category": entry.category,
                    "number": entry.number,
                    "index_path": str(index_path),
                },
            ))
        return collection

    @staticmethod
    def _locations(document: MixDocument,
                   options: Mapping[str, Any]) -> tuple[Path, Path]:
        """Return ``(index_path, pxd_root)`` from options or the mix path."""
        index_option = options.get("index")
        pxd_option = options.get("pxd")

        if index_option:
            index_path = Path(index_option)
            pxd_root = (Path(pxd_option) if pxd_option
                        else index_path.parent.parent)
        elif pxd_option:
            pxd_root = Path(pxd_option)
            index_path = pxd_root / "EJAY" / "PXD"
        else:
            found = find_index(document.source)
            if found is None:
                raise SampleError(
                    "cannot find the eJay sample index (EJAY/PXD); "
                    "pass --pxd or --index")
            index_path = found
            pxd_root = found.parent.parent

        if not index_path.is_file():
            raise SampleError(f"{index_path}: sample index not found")
        return index_path, pxd_root
