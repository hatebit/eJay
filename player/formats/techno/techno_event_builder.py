"""Position Techno one-shot placements and pan them by track."""

from __future__ import annotations

from ...constants import SAMPLE_RATE
from ...mix_document import MixDocument
from ...playback_event import PlaybackEvent
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank

BEATS_PER_BAR = 4.0
LEFT_TRACKS = frozenset({4, 13, 15})
RIGHT_TRACKS = frozenset({5, 14, 16})
FULL = 1.0
SILENT = 0.0


def bar_frames(bpm: float, rate: int = SAMPLE_RATE) -> float:
    """Return the number of frames in one 4/4 bar.

    Args:
        bpm: Tempo in beats per minute.
        rate: Output sample rate.

    Returns:
        Frames per bar, 75 600 for 140 BPM at 44.1 kHz.
    """
    return 60.0 / bpm * BEATS_PER_BAR * rate


def track_gains(track: int) -> tuple[float, float]:
    """Return a track's (left, right) gains.

    A centred track is at full scale in both channels, not at half scale: the
    engine has no 0.5 factor on its gain path, and pan there selects the
    output channel rather than attenuating the other one. Hard-panned tracks
    are the halves of a stereo sample pair, so they are at full scale in their
    own channel.

    Args:
        track: 1-based track number.

    Returns:
        The left and right gains.
    """
    if track in LEFT_TRACKS:
        return FULL, SILENT
    if track in RIGHT_TRACKS:
        return SILENT, FULL
    return FULL, FULL


class TechnoEventBuilder:
    """Build the Techno stereo plan from one-shot placements."""

    def build(self, document: MixDocument, samples: SampleBank, bpm: float,
              rate: int = SAMPLE_RATE) -> PlaybackPlan:
        """Build the plan.

        Args:
            document: Parsed Techno mix.
            samples: Decoded samples.
            bpm: Tempo used for the timeline.
            rate: Output sample rate.

        Returns:
            An interleaved-stereo plan.
        """
        frames_per_bar = bar_frames(bpm, rate)
        events: list[PlaybackEvent] = []
        for placement in document.placements:
            pcm = samples.get(placement.sample_id)
            if not pcm:
                continue
            start = int(round((placement.bar - 1.0) * frames_per_bar))
            left_gain, right_gain = track_gains(placement.track)
            events.append(PlaybackEvent(
                start=start,
                end=start + len(pcm),
                pcm=pcm,
                sample_id=placement.sample_id,
                track=placement.track,
                left_gain=left_gain,
                right_gain=right_gain,
                loop=False,
                label=samples.label_for(placement.sample_id),
                parameters={
                    "bar": placement.bar,
                    "long": placement.parameters.get("long", False),
                },
            ))

        events.sort(key=lambda event: (event.start, event.track))
        total = max((event.end for event in events), default=0)
        return PlaybackPlan(
            events=events,
            total_frames=total,
            channels=2,
            format_name="techno",
            title=document.title,
            sample_rate=rate,
            details={
                "bpm": bpm,
                "frames_per_bar": frames_per_bar,
                "placements": len(document.placements),
            },
        )
