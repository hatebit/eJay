"""Text output helpers for the mix player command line."""

from __future__ import annotations

import os
import re
import sys

# Fancy box-drawing banner shown on consoles that can encode it.
FANCY_LOGO = (
    "\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█▄\033[0;37m \033[0;31m▄█\033[0;91;41m▄\033[0;97;41m▄\033[0;31m▌\033[0;34m░\033[0;33m▐\033[0;93;43m▐\033[0;93m▓▄\033[0;34m▀▀░\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█\033[0;37m \033[0;34m██\033[0;37m \033[0;31m█\033[0;91;41m▄\033[0;31m█▌█\033[0;97;41m▄\033[0;91;41m▄\033[0;97;41m \033[0;31m███\033[0;91;41m▄\033[0;31m▄\033[0;34m▀\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█\033[0;34m▐█\033[0;93;44m  \033[0;34m▓▒░\033[0;31m▄\033[0;31;41m \033[0;31m███████▄\033[0;37m \033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█\033[0;37m \033[0;34m██\033[0;37m \033[0;31m█\033[0;91;41m▄\033[0;97;41m▄\033[0;31m▌\033[0;34m▌\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m████████\033[0;34m░\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█████\033[0;91;41m▄\033[0;31m▄\033[0;37m \033[0;34m▀\033[0m"
    "\n\033[0;31m█\033[0;91;41m█\033[0;31m███████\033[0;91;41m█\033[0;31m▌\033[0;34m░\033[0;31;43m \033[0;93;43m█\033[0;93m███▌\033[0;34m░\033[0;31m▀\033[0;91;41m█\033[0;31m██▄\033[0;37m \033[0;34m▀\033[0;37m \033[0;31m███\033[0;37m \033[0;31m█\033[0;91;41m█\033[0;31m██\033[0;37m \033[0;34m▄\033[0;37m \033[0;31m██▌█\033[0;91;41m█\033[0;31m██\033[0;34m▐█\033[0;34;44m  \033[0;34m▓▒░\033[0;31m█\033[0;97;41m▄\033[0;91;41m▄\033[0;31m█\033[0;37m \033[0;34m▄▄\033[0;37m \033[0;31m█\033[0;91;41m▄\033[0;31m▌█\033[0;91;41m▀\033[0;31m██▄\033[0;37m \033[0;34m▀\033[0;37m \033[0;31m██\033[0;91;41m█\033[0;31m▌\033[0;34m▌\033[0;31m█\033[0;91;41m█\033[0;31m██\033[0;37m    \033[0;34m▄\033[0;37m \033[0;31m▀\033[0;34m░\033[0;34;41m \033[0;91;41m█\033[0;31m██\033[0;37m \033[0;34m▄▄\033[0;37m \033[0;34;41m  \033[0;31m▌\033[0;37m \033[0m"
    "\n\033[0;31m█\033[0;91;41m▄\033[0;31m██\033[0;37m \033[0;31m█▀██\033[0;91;41m▄\033[0;31m▌\033[0;34m░\033[0;37m \033[0;33m▀\033[0;93;43m▀▀\033[0;93m▀\033[0;34m▄░\033[0;37m  \033[0;31m████████\033[0;37m  \033[0;31m█\033[0;91;41m▄\033[0;31m██\033[0;37m \033[0;34m▀\033[0;37m \033[0;31m██▌█\033[0;91;41m▄\033[0;31m██\033[0;34m▐\033[0;34;44m   \033[0;34m▓▒░\033[0;31m█\033[0;91;41m█\033[0;31m██\033[0;37m \033[0;34m▀▀\033[0;37m \033[0;31m██▌\033[0;37m \033[0;31m▀▀███████\033[0;91;41m▄\033[0;31m▌\033[0;34m▌\033[0;31m█\033[0;91;41m▄\033[0;31m█████\033[0;37m \033[0;34m█▓▒░\033[0;31m█\033[0;91;41m▄\033[0;31m██\033[0;37m \033[0;34m▀\033[0;37m \033[0;31m▄██▌\033[0;37m \033[0m"
    "\n\033[0;31m████\033[0;37m \033[0;31m▀\033[0;37m \033[0;31m███▌\033[0;34m░▌\033[0;31m▓▄▄▓\033[0;37m \033[0;34m░\033[0;31m▄███\033[0;37m \033[0;34m▄\033[0;37m \033[0;31m▀███\033[0;37m \033[0;31m████████▀\033[0;37m \033[0;31m████\033[0;34m▐\033[0;31;44m   \033[0;34m▓▒░\033[0;31m█\033[0;91;41m▄\033[0;31m████████▌\033[0;34m░▒▓▄▄▄▄\033[0;37m \033[0;31m███▌\033[0;34m▌\033[0;31m████\033[0;37m \033[0;34m▄▄▄█▓▒░\033[0;31m█████████▀\033[0;37m \033[0;34m▄\033[0m"
    "\n\033[0;31m████\033[0;37m \033[0;34m█\033[0;37m \033[0;31m███▌\033[0;34m░▌\033[0;31m████\033[0;37m \033[0;34m░\033[0;31m████\033[0;37m \033[0;34m██\033[0;37m \033[0;31m███▌\033[0;34;41m \033[0;31m███\033[0;37m \033[0;34m▄▄▄▒░\033[0;31m████\033[0;34m▐▀\033[0;37m \033[0;31m█\033[0;91;41m▄\033[0;31m█\033[0;34m░\033[0;31m████\033[0;37m \033[0;34m▄▄\033[0;37m \033[0;31m██▌\033[0;34m░▒▓████\033[0;37m \033[0;31m███▌\033[0;34m▌\033[0;31m████\033[0;37m \033[0;34m▀▀▀▀\033[0;37m \033[0;31m▄\033[0;34m░\033[0;31m████\033[0;37m  \033[0;31m▀███▄\033[0;37m \033[0m"
    "\n\033[0;31m████\033[0;37m \033[0;34m█\033[0;37m \033[0;31m███▌\033[0;34m░▌\033[0;31m████\033[0;37m \033[0;34m░\033[0;31m████\033[0;37m \033[0;34m██\033[0;37m \033[0;31m███▌█\033[0;31;41m \033[0;31m██\033[0;37m \033[0;34m██▓▒░\033[0;31m██████████\033[0;34m░\033[0;31m████\033[0;37m \033[0;34m██\033[0;37m \033[0;31m██▌\033[0;34m░▒▓████\033[0;37m \033[0;31m███▌\033[0;34m▌\033[0;31m███████████\033[0;34m░\033[0;31m████\033[0;30m·\033[0;34m█▄\033[0;30m·\033[0;31m███\033[0;30m·\033[0m"
)

_ANSI_CODES = re.compile(r"\x1b\[[0-9;]*m")

# The same banner without colour codes, still using the box-drawing glyphs.
TEXT_LOGO = _ANSI_CODES.sub("", FANCY_LOGO)

# Last-resort banner for consoles that cannot encode the box-drawing glyphs
# (for example the default cp1252 Windows console). ASCII only.
PLAIN_LOGO = "\n".join((
    "  +" + "-" * 38 + "+",
    "  | " + "MixPlayer - eJay .MIX player".ljust(36) + " |",
    "  | " + "rave / dance / hiphop / techno".ljust(36) + " |",
    "  +" + "-" * 38 + "+",
))


def is_interactive(stream: object | None = None) -> bool:
    """Return True when a stream is a terminal.

    Args:
        stream: Stream to test; ``sys.stdout`` when omitted.

    Returns:
        True only when the stream reports itself as a terminal.
    """
    stream = sys.stdout if stream is None else stream
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except (OSError, ValueError):
        return False


def _can_encode(text: str) -> bool:
    """Return True when stdout can encode ``text``."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _supports_ansi() -> bool:
    """Return True when the console understands ANSI colour codes.

    Redirected output never qualifies. On Windows only hosts that enable VT
    processing are trusted, because the legacy console shows the codes as
    text.
    """
    if not is_interactive():
        return False
    if "NO_COLOR" in os.environ:
        return False
    if os.name != "nt":
        return True
    return bool(os.environ.get("WT_SESSION")
                or os.environ.get("ANSICON")
                or os.environ.get("ConEmuANSI") == "ON")


def mix_player_logo() -> None:
    """Print the player banner on an interactive terminal.

    Nothing is printed when stdout is redirected, so piped or logged output
    stays free of escape codes and decoration. On a terminal the colour logo
    is used when ANSI is supported, the same glyphs without colour when only
    the glyphs work, and an ASCII box when the code page cannot encode them.
    """
    if not is_interactive():
        return
    print()
    if not _can_encode(FANCY_LOGO):
        print(PLAIN_LOGO)
    elif _supports_ansi():
        print(FANCY_LOGO)
    else:
        print(TEXT_LOGO)
    print()
