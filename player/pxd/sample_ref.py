"""Format-neutral reference to one sample before it is decoded."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SampleRef:
    """Where a sample lives and how it should be described.

    A reference points either at a standalone file (``path``) or at a slice of
    an archive (``archive`` + ``offset`` + ``size``).  The common
    :class:`~player.pxd.sample_decoder.SampleDecoder` understands both.

    Attributes:
        sample_id: Numeric id used by the mix format.
        name: Stored sample or bank name.
        label: Display name shown in listings.
        path: Standalone sample file, when the format uses one.
        archive: Archive file, when the format stores samples inside one.
        offset: Byte offset inside ``archive``.
        size: Byte length inside ``archive``.
        bars: Length in bars, when the index records it.
        parameters: Format-specific extras.
    """

    sample_id: int
    name: str = ""
    label: str = ""
    path: Path | None = None
    archive: Path | None = None
    offset: int = 0
    size: int = 0
    bars: int = 0
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Best available name for messages and listings."""
        return self.label or self.name or f"sample {self.sample_id}"
