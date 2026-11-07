"""Exception raised while collecting or decoding samples."""

from __future__ import annotations

from ..mix_error import MixError


class SampleError(MixError):
    """A sample index, sample file, or sample stream cannot be used.

    Collectors raise it for an unusable index or archive; the decoder raises
    it for an unknown or truncated sample stream.
    """
