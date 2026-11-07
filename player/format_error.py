"""Exception raised while parsing a mix container."""

from __future__ import annotations

from .mix_error import MixError


class FormatError(MixError):
    """The file does not match the selected mix format.

    Raised by a :class:`~player.mix_format.MixFormat` parser when the
    magic, a table, or a required trailer is missing or inconsistent.
    """
