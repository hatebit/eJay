"""Common block mixer: plan -> int16 PCM, mono or interleaved stereo."""

from __future__ import annotations

import array
from typing import Callable

from .binary import clamp16
from .playback_error import PlaybackError
from .playback_event import PlaybackEvent
from .playback_plan import PlaybackPlan
from .pxd.sample_stream import SampleStream


class Mixer:
    """Adds positioned events into successive, contiguous output blocks.

    The mixer is deliberately format-agnostic: looping, cutting, and panning
    were decided by the format's event builder and are already encoded in the
    :class:`PlaybackEvent` objects.

    Attributes:
        total: Number of frames in the plan.
        channels: 1 for mono, 2 for interleaved stereo.
    """

    def __init__(self, plan: PlaybackPlan, gain: float = 1.0,
                 on_start: Callable[[PlaybackEvent], None] | None = None
                 ) -> None:
        if plan.channels not in (1, 2):
            raise PlaybackError(
                f"unsupported channel count {plan.channels} (use 1 or 2)")
        self.plan = plan
        self.gain = float(gain)
        self.channels = plan.channels
        self.total = plan.total_frames
        self.on_start = on_start
        self._events = sorted(plan.events, key=lambda event: event.start)
        self._next = 0
        self._active: list[PlaybackEvent] = []

    def mix(self, start: int, count: int) -> array.array:
        """Render ``count`` frames starting at ``start``.

        Events are summed into a 64-bit accumulator and clipped once per
        output frame, so the result does not depend on event order.

        Args:
            start: First output frame.
            count: Number of frames to render.

        Returns:
            An int16 array of ``count`` mono values or ``2 * count``
            interleaved stereo values.

        Raises:
            PlaybackError: The plan uses an unsupported channel count.
        """
        acc = array.array("q", bytes(8 * self.channels * count))
        end = start + count
        self._activate(start, end)
        alive: list[PlaybackEvent] = []
        gain = self.gain

        for event in self._active:
            pcm = event.pcm
            stream = pcm if isinstance(pcm, SampleStream) else None
            lo = event.start if event.start > start else start
            hi = end if end < event.end else event.end
            if hi > lo:
                length = len(pcm)
                if length:
                    src = lo - event.start
                    if event.loop:
                        src %= length
                    frames = hi - lo
                    loop = event.loop
                    if stream is not None:
                        pcm = stream.window(src, frames, loop)
                        src = 0
                        frames = len(pcm)
                        loop = False
                    elif not loop and src + frames > length:
                        frames = length - src
                    dst = lo - start
                    if self.channels == 1:
                        self._mix_mono(acc, dst, src, frames, pcm,
                                       loop, gain)
                    else:
                        self._mix_stereo(acc, dst, src, frames, pcm,
                                         loop, event.left_gain,
                                         event.right_gain, gain)
            if event.end > end:
                alive.append(event)

        self._active = alive
        if not acc:
            return array.array("h")
        if max(acc) > 32767 or min(acc) < -32768:
            return array.array("h", (clamp16(value) for value in acc))
        return array.array("h", acc)

    def _activate(self, start: int, end: int) -> None:
        """Move events that begin before ``end`` into the active list."""
        while (self._next < len(self._events)
               and self._events[self._next].start < end):
            event = self._events[self._next]
            self._next += 1
            if event.end <= start:
                continue
            self._active.append(event)
            if self.on_start is not None:
                self.on_start(event)

    def _mix_mono(self, acc: array.array, dst: int, src: int, frames: int,
                  pcm: array.array, loop: bool, gain: float) -> None:
        length = len(pcm)
        if gain == 1.0:
            for i in range(frames):
                if loop and src >= length:
                    src -= length
                acc[dst + i] += pcm[src]
                src += 1
            return
        for i in range(frames):
            if loop and src >= length:
                src -= length
            acc[dst + i] += int(pcm[src] * gain)
            src += 1

    def _mix_stereo(self, acc: array.array, dst: int, src: int, frames: int,
                    pcm: array.array, loop: bool, left_gain: float,
                    right_gain: float, gain: float) -> None:
        length = len(pcm)
        for i in range(frames):
            if loop and src >= length:
                src -= length
            value = int(pcm[src] * gain)
            left = 2 * (dst + i)
            acc[left] += int(value * left_gain)
            acc[left + 1] += int(value * right_gain)
            src += 1
