"""Resolve Techno sample ids to slices of the ``RAVE20`` archive."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_error import SampleError
from .techno_sample_index import TechnoSampleIndex

INDEX_NAME = "RAVE20.INF"
ARCHIVE_NAME = "RAVE20"


class TechnoSampleCollector:
    """Turn a Techno document's sample ids into archive references."""

    def collect(self, document: MixDocument,
                options: Mapping[str, Any]) -> SampleCollection:
        """Resolve every id through ``RAVE20.INF`` and ``RAVE20``.

        Args:
            document: Parsed Techno mix.
            options: Full player options; ``pxd`` names the folder holding
                the archive and ``index`` the index file.

        Returns:
            References into the archive, plus one error per id missing from
            the index.

        Raises:
            SampleError: The index or archive cannot be found or read.
        """
        index_option = options.get("index")
        pxd_option = options.get("pxd")

        if index_option:
            inf_path = Path(index_option)
            pxd_root = (Path(pxd_option) if pxd_option
                        else inf_path.parent)
        else:
            pxd_root = (Path(pxd_option) if pxd_option
                        else document.source.parent)
            inf_path = pxd_root / INDEX_NAME
        archive_path = pxd_root / ARCHIVE_NAME

        index = TechnoSampleIndex.read(inf_path)
        if not archive_path.is_file():
            raise SampleError(f"{archive_path}: sample archive not found")

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
                    f"id {sample_id}: not in {inf_path.name}")
                continue
            collection.add(replace(ref, archive=archive_path))
        return collection
