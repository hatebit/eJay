"""The common player: parse -> collect -> prepare -> render."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Mapping

from .audio_output import AudioOutput
from .constants import (
    DEFAULT_BLOCK_FRAMES,
    DEFAULT_GAIN,
    MIN_BLOCK_FRAMES,
)
from .event_printer import EventPrinter
from .formatting import format_time
from .mix_error import MixError
from .mix_registry import MixRegistry
from .mixer import Mixer
from .playback_error import PlaybackError
from .playback_keys import available, read
from .playback_session import PlaybackSession
from .pxd.sample_decoder import SampleDecoder
from .pxd.sample_error import SampleError


class MixPlayer:
    """Run a mix through the shared four-stage pipeline.

    The player owns no format knowledge.  It asks the registry to pick a
    :class:`~player.mix_format.MixFormat`, then calls its parse,
    collect, and prepare stages before handing the plan to the common
    :class:`~player.mixer.Mixer`.

    Attributes:
        registry: Formats available for detection and ``--format``.
        decoder: Shared sample decoder.
    """

    def __init__(self, registry: MixRegistry | None = None,
                 decoder: SampleDecoder | None = None) -> None:
        self.registry = registry or MixRegistry.default()
        self.decoder = decoder or SampleDecoder()

    def load(self, path: Path, options: Mapping[str, Any] | None = None
             ) -> PlaybackSession:
        """Run parse, collect, and prepare for one file.

        Args:
            path: Mix file to load.
            options: Player options; ``formats`` holds per-format dictionaries.

        Returns:
            The loaded session.

        Raises:
            MixError: A stage failed, or ``strict`` is set and any sample was
                skipped.
        """
        started = time.perf_counter()
        opts = dict(options or {})
        selected = opts.get("format")
        if selected:
            mix_format = self.registry.by_name(str(selected))
        else:
            mix_format = self.registry.detect(path)

        document = mix_format.parse(path, opts)
        samples_started = time.perf_counter()
        collection = mix_format.collect_samples(document, opts)
        samples = self.decoder.decode_collection(collection)
        sample_seconds = time.perf_counter() - samples_started
        warnings = list(collection.errors) + list(samples.errors)
        if opts.get("strict") and warnings:
            raise SampleError("; ".join(warnings))

        plan = mix_format.prepare_events(document, samples, opts)
        return PlaybackSession(
            mix_format=mix_format,
            document=document,
            samples=samples,
            plan=plan,
            warnings=warnings,
            load_seconds=time.perf_counter() - started,
            sample_seconds=sample_seconds,
        )

    def play(self, path: Path, options: Mapping[str, Any] | None = None,
             output: Any | None = None) -> int:
        """Play or list one mix.

        Args:
            path: Mix file to play.
            options: Player options.  Recognised common keys are ``list``,
                ``strict``, ``pxd``, ``index``, ``device``, ``block``,
                ``gain``, ``quiet``, ``verbose``, and ``format``.
            output: An object with ``write(samples)``; when omitted an
                :class:`AudioOutput` is created and closed by the player.

        Returns:
            Zero on success, one on error, 130 when interrupted.
        """
        opts = dict(options or {})
        try:
            session = self.load(path, opts)
        except MixError as exc:
            self._error(str(exc))
            return 1

        quiet = bool(opts.get("quiet"))
        if opts.get("list"):
            self._report_warnings(session, quiet)
            self._report_load_timing(session, quiet)
            return self.show_session(session)

        verbose = bool(opts.get("verbose")) and not quiet
        plan = session.plan
        if plan.is_empty:
            self._error(f"{path.name}: nothing to play")
            return 1

        gain = float(opts.get("gain", DEFAULT_GAIN))
        if gain <= 0:
            self._error("--gain must be positive")
            return 1
        block = max(MIN_BLOCK_FRAMES,
                    int(opts.get("block", DEFAULT_BLOCK_FRAMES)))

        self._report_warnings(session, quiet)
        self._report_load_timing(session, quiet)

        rate = float(plan.sample_rate)

        owned = output is None
        if owned:
            output = AudioOutput(
                device=opts.get("device"),
                block_frames=block,
                channels=plan.channels,
                sample_rate=plan.sample_rate,
            )

        printer = EventPrinter(plan.sample_rate)

        if not quiet:
            summary = self._summary(session)
            print(summary + ("  via sounddevice" if owned else ""))

        stopped = False
        try:
            if owned:
                audio_started = time.perf_counter()
                output.open()
                if not quiet:
                    print("audio initialized in "
                          f"{time.perf_counter() - audio_started:.3f} s")

            mixer = Mixer(plan, gain=gain,
                          on_start=printer.announce if verbose else None)
            paused = False
            controls = owned and available()
            start = 0
            while start < plan.total_frames:
                if controls:
                    for key in read():
                        if key == "\x1b":
                            stopped = True
                            break
                        if key == " ":
                            paused = not paused
                            if paused:
                                output.pause()
                            else:
                                output.resume()
                            if not quiet:
                                printer.note("paused" if paused else "resumed")
                    if stopped:
                        break
                if paused:
                    time.sleep(0.02)
                    continue
                count = min(block, plan.total_frames - start)
                t0 = time.perf_counter()
                buf = mixer.mix(start, count)
                dt = time.perf_counter() - t0
                if dt > count / rate:
                    printer.note(f"slow block at {start / rate:.2f}s: "
                                 f"{dt * 1000:.1f} ms")
                output.write(buf)
                start += count
        except KeyboardInterrupt:
            if not quiet:
                self._error("interrupted")
            return 130
        except PlaybackError as exc:
            self._error(str(exc))
            return 1
        finally:
            try:
                if owned:
                    output.close()
            finally:
                printer.close()
                session.samples.close()

        if not quiet:
            self._report_decode_errors(session)
            print("stopped" if stopped else "done")
        return 0

    def show(self, path: Path,
             options: Mapping[str, Any] | None = None) -> int:
        """Print the parsed arrangement without opening a device.

        Args:
            path: Mix file to list.
            options: Player options.

        Returns:
            Zero on success, one on error.
        """
        try:
            session = self.load(path, options)
        except MixError as exc:
            self._error(str(exc))
            return 1
        quiet = bool((options or {}).get("quiet"))
        self._report_warnings(session, quiet)
        self._report_load_timing(session, quiet)
        return self.show_session(session)

    def show_session(self, session: PlaybackSession) -> int:
        """Print one loaded session as a listing.

        Args:
            session: Result of :meth:`load`.

        Returns:
            Zero.
        """
        print(self._summary(session))
        for line in session.mix_format.describe(
                session.document, session.samples, session.plan):
            print(line)
        return 0

    def _summary(self, session: PlaybackSession) -> str:
        plan = session.plan
        document = session.document
        return (f"{document.display_name}  {plan.format_name}  "
                f"{len(plan.events)} events  "
                f"{format_time(plan.duration_seconds)}")

    def _report_warnings(self, session: PlaybackSession, quiet: bool) -> None:
        if quiet:
            return
        for message in session.warnings:
            self._error(f"skipped {message}")

    @staticmethod
    def _report_load_timing(session: PlaybackSession, quiet: bool) -> None:
        if quiet:
            return
        print(f"loaded {len(session.samples)} samples in "
              f"{session.sample_seconds:.3f} s")

    @staticmethod
    def _report_decode_errors(session: PlaybackSession) -> None:
        """Report samples that failed to decode after playback started."""
        reported = set(session.warnings)
        for message in session.samples.errors:
            if message not in reported:
                reported.add(message)
                MixPlayer._error(f"skipped {message}")

    @staticmethod
    def _error(message: str) -> None:
        print(f"player: {message}", file=sys.stderr)
