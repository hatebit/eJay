"""The four-stage contract every mix format implements."""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Mapping

if TYPE_CHECKING:
    from .mix_document import MixDocument
    from .playback_plan import PlaybackPlan
    from .pxd.sample_bank import SampleBank
    from .pxd.sample_collection import SampleCollection


class MixFormat(ABC):
    """A mix container plus its sample source and placement rules.

    The common player runs the same pipeline for every format:

    1. :meth:`parse` reads the container into a
       :class:`~player.mix_document.MixDocument`.
    2. :meth:`collect_samples` resolves the ids the document references into
       :class:`~player.pxd.sample_ref.SampleRef` objects.
    3. :meth:`prepare_events` turns placements and decoded PCM into a
       :class:`~player.playback_plan.PlaybackPlan`.
    4. The common :class:`~player.mix_player.MixPlayer` renders that plan.

    Only stages 1-3 are format-specific.  A new format is a subclass that
    implements them and registers itself with a
    :class:`~player.mix_registry.MixRegistry`.
    """

    name: ClassVar[str] = ""
    """Stable short name used by ``--format`` and options lookup."""
    version: ClassVar[str] = ""
    """Version of this plugin's interface, following semantic versioning.

    MAJOR when a caller of this format has to change (options read,
    ``add_arguments`` flags, the payload type), MINOR when a mix or sample
    variant is newly supported, PATCH for fixes that keep both.  A new
    format starts at ``1.0.0``.
    """

    @abstractmethod
    def matches(self, header: bytes) -> bool:
        """Return True when ``header`` looks like this format.

        Args:
            header: First bytes of a candidate file; the registry
                supplies 32.
        """

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add format-specific command-line options to ``parser``.

        The default adds nothing.  The common ``--pxd`` and ``--index`` are
        added by the CLI, so add only flags this format needs.  Keep option
        names unique across formats; the CLI merges every format's options
        into one namespace.
        """

    def options(self, namespace: argparse.Namespace) -> dict[str, Any]:
        """Extract this format's options from a parsed CLI namespace.

        Args:
            namespace: Namespace built by :meth:`add_arguments`.

        Returns:
            A dictionary stored under ``options["formats"][self.name]``.
        """
        return {}

    def format_options(self,
                       options: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return this format's slice of a player options mapping.

        Args:
            options: The mapping passed to the player.

        Returns:
            The format's own options, or an empty mapping.
        """
        formats = options.get("formats", {})
        if isinstance(formats, Mapping):
            scoped = formats.get(self.name, {})
            if isinstance(scoped, Mapping):
                return scoped
        return {}

    @abstractmethod
    def parse(self, path, options: Mapping[str, Any]) -> "MixDocument":
        """Read ``path`` into a format-neutral document.

        Args:
            path: Mix file to read.
            options: Full player options, including ``formats``.
        """

    @abstractmethod
    def collect_samples(self, document: "MixDocument",
                        options: Mapping[str, Any]) -> "SampleCollection":
        """Resolve every sample id the document references.

        Args:
            document: Result of :meth:`parse`.
            options: Full player options; ``pxd`` names the folder holding
                the samples and ``index`` the index file.
        """

    @abstractmethod
    def prepare_events(self, document: "MixDocument",
                       samples: "SampleBank",
                       options: Mapping[str, Any]) -> "PlaybackPlan":
        """Build positioned events and the total render length.

        Args:
            document: Result of :meth:`parse`.
            samples: Decoded samples keyed by id.
            options: Full player options.
        """

    def describe(self, document: "MixDocument", samples: "SampleBank",
                 plan: "PlaybackPlan") -> list[str]:
        """Return format-specific listing lines for ``--list``.

        Args:
            document: Parsed mix.
            samples: Decoded samples.
            plan: Prepared plan.

        Returns:
            Lines to print below the common summary.
        """
        lines = ["    time      Tk  ID    sample"]
        rate = float(plan.sample_rate)
        for event in sorted(plan.events, key=lambda item: item.start):
            lines.append(
                f"  {event.start / rate:8.2f}  T{event.track}  "
                f"{event.sample_id:04X}  {event.label}")
        return lines
