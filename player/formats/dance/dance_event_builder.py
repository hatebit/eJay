"""Collapse Dance grid runs and position them on the output timeline."""

from __future__ import annotations

from ...constants import SAMPLE_RATE
from ...mix_document import MixDocument
from ...placement import Placement
from ...playback_event import PlaybackEvent
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from .dance_grid import BARS_PER_BLOCK, MIN_SAMPLE_ID, TRACKS, DanceGrid


class DanceEventBuilder:
    """Build the Dance playback plan from per-track grid runs.

    A run is one sounding: the same id repeated in consecutive bars on one
    track.  A run longer than its sample repeats the sample; a run shorter
    than its sample still plays the whole sample, except that the next sample
    on that track cuts it when the next one starts.
    """

    def build(self, document: MixDocument, samples: SampleBank, bpm: float,
              rate: int = SAMPLE_RATE) -> PlaybackPlan:
        """Build the plan.

        Args:
            document: Parsed Dance mix; ``payload`` must be a
                :class:`~player.formats.dance.dance_grid.DanceGrid`.
            samples: Decoded samples.
            bpm: Tempo in beats per minute; one bar is four beats.
            rate: Output sample rate.

        Returns:
            A mono plan.
        """
        grid: DanceGrid = document.payload
        bar_frames = 240.0 * rate / bpm
        runs = self._runs(grid)

        positions = []
        for run in runs:
            pcm = samples.get(run.sample_id)
            if not pcm:
                continue
            start = int(round((run.bar - 1.0) * bar_frames))
            run_end = int(round((run.end_bar - 1.0) * bar_frames))
            positions.append((start, run_end, run, pcm))
        positions.sort(key=lambda item: (item[0], item[2].track))

        next_start: dict[int, int] = {}
        by_track: dict[int, list[tuple[int, int]]] = {}
        for index, (start, _, run, _) in enumerate(positions):
            by_track.setdefault(run.track, []).append((start, index))
        for starts in by_track.values():
            for (_, index), (following, _) in zip(starts, starts[1:]):
                next_start[index] = following

        events: list[PlaybackEvent] = []
        total = 0
        for index, (start, run_end, run, pcm) in enumerate(positions):
            loop = run_end - start > len(pcm) and len(pcm) >= bar_frames
            audio_end = run_end if loop else start + len(pcm)
            following = next_start.get(index)
            if following is not None:
                audio_end = min(audio_end, following)
            if audio_end <= start:
                audio_end = start + 1

            events.append(PlaybackEvent(
                start=start,
                end=audio_end,
                pcm=pcm,
                sample_id=run.sample_id,
                track=run.track,
                left_gain=1.0,
                right_gain=1.0,
                loop=loop,
                label=samples.label_for(run.sample_id),
                parameters={
                    "block": int((run.bar - 1.0) // BARS_PER_BLOCK),
                    "bar": int(round(run.bar - 1.0)),
                    "bar_in_block": int(round(run.bar - 1.0))
                    % BARS_PER_BLOCK,
                    "span": int(round(run.span)),
                },
            ))
            total = max(total, audio_end, run_end)

        return PlaybackPlan(
            events=events,
            total_frames=total,
            channels=1,
            format_name="dance",
            title=document.title,
            sample_rate=rate,
            details={
                "blocks": len(grid.blocks),
                "used_blocks": grid.used_blocks(),
                "used_bars": grid.used_bars(),
                "bpm": bpm,
                "bar_frames": bar_frames,
                "placements": len(events),
            },
        )

    @staticmethod
    def _runs(grid: DanceGrid) -> list[Placement]:
        """Collapse repeated ids into one run per continuous track segment."""
        runs: list[Placement] = []
        current = [0] * TRACKS
        first = [0] * TRACKS
        for bar, row in grid.bars():
            for track, sample_id in enumerate(row):
                if sample_id < MIN_SAMPLE_ID:
                    sample_id = 0
                if sample_id == current[track]:
                    continue
                if current[track]:
                    runs.append(Placement(
                        track=track + 1,
                        bar=1.0 + first[track],
                        sample_id=current[track],
                        span=float(bar - first[track]),
                    ))
                current[track] = sample_id
                first[track] = bar
        bar_count = len(grid.blocks) * BARS_PER_BLOCK
        for track, sample_id in enumerate(current):
            if sample_id:
                runs.append(Placement(
                    track=track + 1,
                    bar=1.0 + first[track],
                    sample_id=sample_id,
                    span=float(bar_count - first[track]),
                ))
        runs.sort(key=lambda run: (run.bar, run.track))
        return runs
