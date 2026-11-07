"""Position Dance eJay 2.0 one-shots and pan them by track."""

from __future__ import annotations

from ...constants import SAMPLE_RATE
from ...mix_document import MixDocument
from ...placement import Placement
from ...playback_event import PlaybackEvent
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from .dance2_mix_data import Dance2MixData

UNITS_PER_BAR = 128.0
BEATS_PER_BAR = 4.0
FULL = 1.0


def bar_frames(bpm: float, rate: int = SAMPLE_RATE) -> float:
    """Return the number of frames in one 4/4 bar.

    Args:
        bpm: Tempo in beats per minute.
        rate: Output sample rate.

    Returns:
        Frames per bar, 75 600 for 140 BPM at 44.1 kHz.
    """
    return 60.0 / bpm * BEATS_PER_BAR * rate


class Dance2EventBuilder:
    """Build the Dance eJay 2.0 stereo plan from its event table."""

    def build(self, document: MixDocument, samples: SampleBank, bpm: float,
              rate: int = SAMPLE_RATE) -> PlaybackPlan:
        """Build the plan.

        A track plays one sample at a time, so an event is cut at the start
        of the next event on the same track; the last event rings out for its
        full length.  Track volume and pan come from the mix's settings
        table.

        Args:
            document: Parsed Dance eJay 2.0 mix.
            samples: Decoded samples.
            bpm: Tempo used for the timeline.
            rate: Output sample rate.

        Returns:
            An interleaved-stereo plan.
        """
        data: Dance2MixData = document.payload
        frames_per_bar = bar_frames(bpm, rate)
        settings = {item.track: item for item in data.track_settings}

        by_track: dict[int, list[Placement]] = {}
        for placement in document.placements:
            by_track.setdefault(placement.track, []).append(placement)

        events: list[PlaybackEvent] = []
        for track, placements in by_track.items():
            placements.sort(key=lambda item: item.bar)
            for index, placement in enumerate(placements):
                stream = samples.get(placement.sample_id)
                if stream is None or not len(stream):
                    continue
                start = int(round((placement.bar - 1.0) * frames_per_bar))
                end = start + len(stream)
                if index + 1 < len(placements):
                    next_bar = placements[index + 1].bar
                    next_start = int(round((next_bar - 1.0) * frames_per_bar))
                    end = min(end, next_start)
                if end <= start:
                    continue

                setting = settings.get(track)
                left_gain, right_gain = (
                    setting.gains() if setting is not None else (FULL, FULL))
                events.append(PlaybackEvent(
                    start=start,
                    end=end,
                    pcm=stream,
                    sample_id=placement.sample_id,
                    track=track,
                    left_gain=left_gain,
                    right_gain=right_gain,
                    loop=False,
                    label=samples.label_for(placement.sample_id),
                    parameters={
                        "bar": placement.bar,
                        "units": placement.parameters.get("units", 0),
                        "flag": placement.parameters.get("flag", 0),
                        "long": placement.parameters.get("long", False),
                    },
                ))

        events.sort(key=lambda event: (event.start, event.track))
        total = max((event.end for event in events), default=0)
        return PlaybackPlan(
            events=events,
            total_frames=total,
            channels=2,
            format_name="dance2",
            title=document.title,
            sample_rate=rate,
            details={
                "bpm": bpm,
                "frames_per_bar": frames_per_bar,
                "placements": len(document.placements),
                "sample_events": data.event_count,
                "text_events": len(data.text_events),
            },
        )
