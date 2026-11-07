"""Per-track pan and volume stored in a Dance eJay 2.0 mix."""

from __future__ import annotations

from dataclasses import dataclass

PAN_CENTRE = 0
PAN_LEFT = 1
PAN_RIGHT = 2
FULL_SCALE = 32767.0


@dataclass(frozen=True, slots=True)
class Dance2TrackSettings:
    """The pan/volume pair the mix stores for one of its 16 sample tracks.

    The pan code is one of three small values.  ``1`` and ``2`` behave like
    the left and right halves of a stereo pair; ``0`` is centred.

    Attributes:
        track: 1-based sample track.
        pan: Stored pan code.
        volume: Stored 16-bit volume.
    """

    track: int
    pan: int
    volume: int

    def gains(self) -> tuple[float, float]:
        """Return the (left, right) gains this setting implies.

        The volume is applied at full scale (``volume / 32767``); a centred
        track feeds both channels and a panned track feeds only its side.
        Unknown pan codes are treated as centred.

        Returns:
            Left and right gains in the range 0.0 to 1.0.
        """
        level = max(0.0, min(1.0, self.volume / FULL_SCALE))
        if self.pan == PAN_LEFT:
            return level, 0.0
        if self.pan == PAN_RIGHT:
            return 0.0, level
        return level, level
