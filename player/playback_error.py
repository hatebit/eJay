"""Exception raised while opening or writing the audio output."""

from __future__ import annotations

from .mix_error import MixError


class PlaybackError(MixError):
    """The audio output cannot be opened or written.

    ``sounddevice`` is imported lazily, so a missing package or an unavailable
    PortAudio device surfaces as this error instead of an import failure.
    """
