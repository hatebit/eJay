"""Collapse Rave grid runs and position them on the output timeline."""

from __future__ import annotations

from ...constants import SAMPLE_RATE
from ...mix_document import MixDocument
from ...placement import Placement
from ...playback_event import PlaybackEvent
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from .rave_grid import MIN_SAMPLE_ID, RECORD_WORDS, TRACKS


class RaveEventBuilder:
    """Build the Rave playback plan from grid runs.

    A run is one sounding: the same id repeated in consecutive records.  A run
    longer than its sample repeats the sample; a run shorter than its sample
    still plays the whole sample, except that an earlier sample is cut when
    the arrangement's final record begins.
    """

    def build(self, document: MixDocument, samples: SampleBank, step: float,
              rate: int = SAMPLE_RATE) -> PlaybackPlan:
        """Build the plan.

        Args:
            document: Parsed Rave mix; ``payload`` must be a
                :class:`~player.formats.rave.rave_grid.RaveGrid`.
            samples: Decoded samples.
            step: Seconds per grid record.
            rate: Output sample rate.

        Returns:
            A mono plan.
        """
        grid = document.payload
        runs = self._runs(grid.records)
        record_frames = int(round(step * rate))

        positions = []
        for run in runs:
            pcm = samples.get(run.sample_id)
            if not pcm:
                continue
            start = int(round((run.bar - 1.0) / 2.0 * step * rate))
            end = int(round((run.end_bar - 1.0) / 2.0 * step * rate))
            if end <= start:
                end = start + 1
            positions.append((start, end, run, pcm))
        positions.sort(key=lambda item: item[0])

        last_end = max((end for _, end, _, _ in positions), default=0)
        final_start = min(
            (start for start, end, _, _ in positions if end == last_end),
            default=0,
        )

        events: list[PlaybackEvent] = []
        total = 0
        for start, end, run, pcm in positions:
            loop = end - start > len(pcm) and len(pcm) >= record_frames
            if loop:
                audio_end = end
            else:
                natural = start + len(pcm)
                if end >= last_end:
                    audio_end = natural
                else:
                    audio_end = min(natural, final_start)

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
                    "record": int((run.bar - 1.0) / 2.0),
                    "span": int(round(run.span / 2.0)),
                    "lane": run.layer,
                },
            ))
            if audio_end > total:
                total = audio_end
            if end > total:
                total = end

        return PlaybackPlan(
            events=events,
            total_frames=total,
            channels=1,
            format_name="rave",
            title=document.title,
            sample_rate=rate,
            details={
                "records": len(grid.records),
                "used_records": grid.used_records(),
                "step_seconds": step,
                "version": grid.version,
            },
        )

    @staticmethod
    def _runs(records: tuple[tuple[int, ...], ...]) -> list[Placement]:
        """Collapse repeated ids into one run per continuous grid segment."""
        runs: list[Placement] = []
        for column in range(RECORD_WORDS):
            lane = "A" if column < TRACKS else "B"
            track = column % TRACKS + 1
            current = 0
            first = 0
            for record, row in enumerate(records):
                sample_id = row[column]
                if sample_id < MIN_SAMPLE_ID:
                    sample_id = 0
                if sample_id == current:
                    continue
                if current:
                    runs.append(Placement(
                        track=track,
                        bar=1.0 + 2.0 * first,
                        sample_id=current,
                        span=2.0 * (record - first),
                        layer=lane,
                    ))
                current = sample_id
                first = record
            if current:
                runs.append(Placement(
                    track=track,
                    bar=1.0 + 2.0 * first,
                    sample_id=current,
                    span=2.0 * (len(records) - first),
                    layer=lane,
                ))
        runs.sort(key=lambda run: (run.bar, run.track, run.layer))
        return runs
