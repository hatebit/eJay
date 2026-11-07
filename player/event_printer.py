"""Background printer that keeps console writes off the playback path."""

from __future__ import annotations

import queue
import sys
import threading
from typing import TextIO

from .formatting import format_time
from .playback_event import PlaybackEvent


class EventPrinter:
    """Format and print playback lines from a worker thread.

    Console writes can take milliseconds on Windows.  The real-time loop must
    not wait for them, so :class:`~player.mix_player.MixPlayer` hands each
    event or status line to this printer instead of calling ``print`` itself.
    The verbose layout is built in :meth:`announce`, so the mixer callback is
    the method itself.

    Attributes:
        sample_rate: Frames per second used to turn event frames into times.
        stream: Destination of the worker; the ``sys.stdout`` that was
            current when the printer was created unless another is given.
    """

    _SENTINEL = None

    def __init__(self, sample_rate: float,
                 stream: TextIO | None = None) -> None:
        self.sample_rate = float(sample_rate)
        self.stream = sys.stdout if stream is None else stream
        self._queue: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="mix-player-printer", daemon=True)
        self._thread.start()

    def announce(self, event: PlaybackEvent) -> None:
        """Queue the verbose line for an event that starts playing.

        Args:
            event: The event that entered the active set.
        """
        self._put(f"  {format_time(event.start / self.sample_rate):>8}  "
                  f"T{event.track}  {event.sample_id:04X}  {event.label}  {"LOOPED" if event.loop else ""}")

    def note(self, line: str) -> None:
        """Queue a status or diagnostic line that is already formatted.

        Args:
            line: Complete line, without the trailing newline.
        """
        self._put(line)

    def close(self) -> None:
        """Print every queued line, then stop the worker.

        The call is idempotent and blocks until the queue is empty, so output
        stays in order with anything the caller prints afterwards.
        """
        if self._closed:
            return
        self._closed = True
        self._queue.put(self._SENTINEL)
        self._thread.join()

    def _put(self, line: str) -> None:
        if self._closed:
            raise RuntimeError("the event printer is closed")
        self._queue.put(line)

    def _run(self) -> None:
        while True:
            line = self._queue.get()
            if line is self._SENTINEL:
                return
            print(line, file=self.stream, flush=True)
