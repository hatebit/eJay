"""Presentation helpers shared by listings and verbose playback."""

from __future__ import annotations


def format_time(seconds: float) -> str:
    """Render seconds as ``minutes:seconds.hundredths``.

    Args:
        seconds: Non-negative time in seconds.

    Returns:
        A compact timestamp such as ``3:05.25``.
    """
    minutes = int(seconds // 60)
    return "%d:%05.2f" % (minutes, seconds - 60 * minutes)
