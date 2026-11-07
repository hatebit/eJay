"""Extensible eJay ``.MIX`` player.

The package separates the format-dependent pipeline stages from the common
renderer::

    parse mix -> collect samples -> prepare events -> play events
    (format)     (format)           (format)          (common)

Add a format by subclassing :class:`MixFormat`, implementing those three
stages, and registering it with a :class:`MixRegistry`.
"""

from __future__ import annotations

from .audio_output import AudioOutput
from .cli import build_parser, main, options_from_namespace
from .constants import (
    DEFAULT_BLOCK_FRAMES,
    DEFAULT_GAIN,
    MIN_BLOCK_FRAMES,
    SAMPLE_RATE,
    VERSION,
)
from .format_error import FormatError
from .formats.dance.dance_mix_format import DanceMixFormat
from .formats.dance2.dance2_mix_format import Dance2MixFormat
from .formats.hiphop.hiphop_mix_format import HiphopMixFormat
from .formats.rave.rave_mix_format import RaveMixFormat
from .formats.techno.techno_mix_format import TechnoMixFormat
from .mix_document import MixDocument
from .mix_error import MixError
from .mix_format import MixFormat
from .mix_player import MixPlayer
from .mix_registry import MixRegistry
from .mixer import Mixer
from .placement import Placement
from .playback_error import PlaybackError
from .playback_event import PlaybackEvent
from .playback_plan import PlaybackPlan
from .playback_session import PlaybackSession
from .pxd.sample_bank import SampleBank
from .pxd.sample_collection import SampleCollection
from .pxd.sample_decoder import SampleDecoder
from .pxd.sample_error import SampleError
from .pxd.sample_ref import SampleRef
from .pxd.sample_stream import SampleStream
