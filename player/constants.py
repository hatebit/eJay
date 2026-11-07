"""Constants shared by every mix format and by the common player."""

from __future__ import annotations

SAMPLE_RATE = 44100
"""Output sample rate, in frames per second."""

DEFAULT_BLOCK_FRAMES = 2048
"""Default number of frames mixed and written per block."""

MIN_BLOCK_FRAMES = 64
"""Lower bound for a caller-supplied block size."""

DEFAULT_GAIN = 1.0
"""Default linear mix gain."""

VERSION = "1.2.1"
"""Package version."""
