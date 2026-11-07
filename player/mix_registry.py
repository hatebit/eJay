"""Format detection and registration."""

from __future__ import annotations

from pathlib import Path

from .format_error import FormatError
from .mix_format import MixFormat


class MixRegistry:
    """Ordered collection of mix formats.

    Detection tries each registered format's :meth:`MixFormat.matches` in
    registration order.  Put the most specific format first.
    """

    def __init__(self) -> None:
        self._formats: list[MixFormat] = []

    def register(self, mix_format: MixFormat) -> MixFormat:
        """Append ``mix_format`` and return it.

        Args:
            mix_format: Format instance with a non-empty unique name.

        Raises:
            ValueError: The name is empty or already registered.
        """
        if not mix_format.name:
            raise ValueError("a mix format needs a non-empty name")
        if any(item.name == mix_format.name for item in self._formats):
            raise ValueError(f"duplicate mix format name {mix_format.name!r}")
        self._formats.append(mix_format)
        return mix_format

    @property
    def formats(self) -> tuple[MixFormat, ...]:
        """Registered formats in detection order."""
        return tuple(self._formats)

    def by_name(self, name: str) -> MixFormat:
        """Return the format registered as ``name``.

        Raises:
            FormatError: No format has that name.
        """
        for mix_format in self._formats:
            if mix_format.name == name:
                return mix_format
        known = ", ".join(item.name for item in self._formats) or "none"
        raise FormatError(f"unknown mix format {name!r} (known: {known})")

    def detect(self, path: Path) -> MixFormat:
        """Choose the first registered format that matches ``path``.

        Args:
            path: Candidate mix file.

        Returns:
            The matching format.

        Raises:
            FormatError: The file cannot be read or no format matches.
        """
        try:
            with path.open("rb") as handle:
                header = handle.read(32)
        except OSError as exc:
            raise FormatError(f"{path}: {exc.strerror or exc}") from exc
        for mix_format in self._formats:
            if mix_format.matches(header):
                return mix_format
        raise FormatError(f"{path.name}: unknown mix format")

    @classmethod
    def default(cls) -> "MixRegistry":
        """Build the registry shipped with the player.

        Returns:
            A registry holding the Dance, Dance 2, Hiphop, Rave and Techno
            formats.
        """
        from .formats.dance.dance_mix_format import DanceMixFormat
        from .formats.dance2.dance2_mix_format import Dance2MixFormat
        from .formats.hiphop.hiphop_mix_format import HiphopMixFormat
        from .formats.rave.rave_mix_format import RaveMixFormat
        from .formats.techno.techno_mix_format import TechnoMixFormat

        registry = cls()
        registry.register(DanceMixFormat())
        registry.register(Dance2MixFormat())
        registry.register(HiphopMixFormat())
        registry.register(RaveMixFormat())
        registry.register(TechnoMixFormat())
        return registry
