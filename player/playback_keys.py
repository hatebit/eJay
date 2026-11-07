"""Non-blocking console key polling for playback controls."""

from __future__ import annotations

import sys


def available() -> bool:
    """Return True when the console can report keys without blocking.

    Returns:
        True on a Windows console; False elsewhere or when input is
        redirected.
    """
    if not sys.stdin.isatty():
        return False
    try:
        import msvcrt
    except ImportError:
        return False
    return hasattr(msvcrt, "kbhit")


def read() -> str:
    """Return every key currently waiting in the console buffer.

    Returns:
        The pending characters, oldest first, or an empty string when there
        is no console input.
    """
    if not available():
        return ""
    import msvcrt
    keys: list[str] = []
    try:
        while msvcrt.kbhit():
            keys.append(msvcrt.getwch())
    except OSError:
        return ""
    return "".join(keys)
