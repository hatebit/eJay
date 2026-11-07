"""Base exception for every recoverable mix-player failure."""

from __future__ import annotations


class MixError(Exception):
    """A mix, its samples, or the output device cannot be used.

    Subclasses narrow the stage that failed so callers can distinguish a
    malformed container from a missing sample or an unavailable device.
    """
