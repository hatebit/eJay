#!/usr/bin/env python3
"""Play a Techno eJay ``.MIX`` arrangement straight through sounddevice.

    python src/sdmixplayer2.py "data/Techno eJay/WAMBAM.MIX"
    python src/sdmixplayer2.py "data/Techno eJay/WAMBAM.MIX" --list

Like ``sdmixplay.py`` this player owns the container and the codec; the ported
``pxd32d5`` engine is not involved.  The format is documented in
``docs/__MIX_FORMAT.md``.  The arrangement lives in the trailer as per-track
event lists: ``u8 track, u32 count`` followed by that many entries.  An entry
is 7 bytes normally and 17 bytes when its time field is non-negative; both end
with the sample id.  The time is a fixed-point bar position with seven
fraction bits, negated in the short form, and bar 1 is the start of the mix.

The sample id is the first field of a ``RAVE20.INF`` record
(``docs/INF_FORMAT.md``); the record's ``tPxD`` stream sits at ``offset``
inside the ``RAVE20`` archive.  Techno eJay has no per-sample ``.pxd`` files,
so the archive is read directly and decoded by ``sdmixplay``'s codec.

A bar is four beats at 140 BPM, i.e. 75 600 frames at 44.1 kHz.  The header's
word 4 carries the tempo (140 in every mix seen) and ``--bpm`` overrides it.
Every entry is played as a one-shot at its position; the ten extra bytes of
the long entry variant are not interpreted yet.  Tracks 4, 13 and 15 are
left-only, 5, 14 and 16 right-only, the rest are centred
(``work/dumps/WAMBAM.tracks.txt``).  A centred track is at full scale in both
channels, not at half scale on each: the engine's gain path has no 0.5 factor
and pan there only selects the output channel (``docs/PXD32R4.md``).
"""

from __future__ import annotations

import argparse
import array
import struct
import sys
from pathlib import Path
from typing import Sequence

import mixsamples
import sdmixplay

SAMPLE_RATE = sdmixplay.SAMPLE_RATE
DEFAULT_BPM = 140.0
BEATS_PER_BAR = 4.0
BLOCK_FRAMES = 2048

# work/dumps/WAMBAM.tracks.txt: 1 means the track plays on that side.
LEFT_TRACKS = frozenset({4, 13, 15})
RIGHT_TRACKS = frozenset({5, 14, 16})


class PlayerError(Exception):
    """A mix, index, or archive cannot be used for playback."""


def bar_frames(bpm: float) -> float:
    """Frames in one 4/4 bar at ``bpm``.

    Args:
        bpm: Tempo in beats per minute.

    Returns:
        Frames per bar at 44.1 kHz as a float, 75 600 for the default 140.
    """
    return 60.0 / bpm * BEATS_PER_BAR * SAMPLE_RATE


def header_bpm(data: bytes) -> float:
    """Tempo from header word 4, falling back to 140 for nonsense.

    Args:
        data: Contents of a Techno eJay ``.MIX``.

    Returns:
        The tempo in beats per minute.
    """
    if len(data) < 16:
        return DEFAULT_BPM
    bpm = struct.unpack_from("<H", data, 8)[0]
    return float(bpm) if 40 <= bpm <= 300 else DEFAULT_BPM


def track_gains(track: int) -> tuple[float, float]:
    """Gains for ``track``: a centred track is full scale in both channels.

    Centred tracks are not attenuated to half scale on each side; the engine
    mixes them at unity into both channels.  The hard-panned tracks are the
    halves of a stereo sample pair, so they too are at full scale in their own
    channel.

    Args:
        track: 1-based track number from the event table.

    Returns:
        The left and right gains.
    """
    if track in LEFT_TRACKS:
        return 1.0, 0.0
    if track in RIGHT_TRACKS:
        return 0.0, 1.0
    return 1.0, 1.0


def find_paths(mix_path: Path, inf: str | None,
               archive: str | None) -> tuple[Path, Path]:
    """Locate ``RAVE20.INF`` and the ``RAVE20`` archive.

    Args:
        mix_path: The mix being played.
        inf: ``--inf`` value, or None to look next to the mix.
        archive: ``--archive`` value, or None to look next to the index.

    Returns:
        The index path and the archive path.  Only the index is required here;
        ``--list`` does not need the archive.

    Raises:
        PlayerError: The index is missing.
    """
    inf_path = Path(inf) if inf else mix_path.parent / "RAVE20.INF"
    archive_path = (Path(archive) if archive
                    else inf_path.parent / "RAVE20")
    if not inf_path.is_file():
        raise PlayerError(f"{inf_path}: sample index not found")
    return inf_path, archive_path


def load_samples(events: Sequence[mixsamples.Event],
                 index: dict[int, mixsamples.Sample],
                 archive: Path) -> tuple[dict[int, array.array],
                                         list[str]]:
    """Decode every sample the events reference.

    Args:
        events: The arrangement's placements.
        index: Records read from ``RAVE20.INF``.
        archive: The ``RAVE20`` file holding the ``tPxD`` records.

    Returns:
        Decoded mono int16 samples keyed by id, plus one message per sample
        that could not be resolved or decoded.
    """
    samples: dict[int, array.array] = {}
    errors: list[str] = []
    ids = sorted({event.sample_id for event in events})
    try:
        handle = archive.open("rb")
    except OSError as exc:
        raise PlayerError(f"{archive}: {exc.strerror or exc}") from exc
    with handle:
        for sample_id in ids:
            entry = index.get(sample_id)
            if entry is None:
                errors.append(f"id {sample_id}: not in RAVE20.INF")
                continue
            try:
                handle.seek(entry.offset)
                data = handle.read(entry.size)
                samples[sample_id] = sdmixplay.decode_sample_bytes(data)
            except (OSError, sdmixplay.MixError) as exc:
                errors.append(f"{entry.name}: {exc}")
    return samples, errors


def _clamp(value: int) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return value


class Mixer:
    """Mixes one-shot placements into interleaved stereo int16 blocks."""

    def __init__(self, spans, total: int, gain: float = 1.0):
        self.spans = sorted(spans, key=lambda span: span[0])
        self.total = total
        self.gain = float(gain)
        self._next = 0
        self._active = []

    def mix(self, start: int, count: int) -> array.array:
        """Return ``count`` interleaved stereo frames from ``start``.

        Args:
            start: First frame to render.
            count: Number of frames to render.

        Returns:
            An int16 array of ``2 * count`` values.
        """
        out = array.array("h", bytes(4 * count))
        end = start + count
        while self._next < len(self.spans) and self.spans[self._next][0] < end:
            span = self.spans[self._next]
            self._next += 1
            if span[0] + len(span[1]) <= start:
                continue
            self._active.append(span)

        alive = []
        gain = self.gain
        for begin, pcm, left_gain, right_gain in self._active:
            finish = begin + len(pcm)
            lo = begin if begin > start else start
            hi = end if end < finish else finish
            if hi > lo:
                src = lo - begin
                dst = lo - start
                for i in range(hi - lo):
                    value = int(pcm[src + i] * gain)
                    left = out[2 * (dst + i)] + int(value * left_gain)
                    right = out[2 * (dst + i) + 1] + int(value * right_gain)
                    out[2 * (dst + i)] = _clamp(left)
                    out[2 * (dst + i) + 1] = _clamp(right)
            if finish > end:
                alive.append((begin, pcm, left_gain, right_gain))
        self._active = alive
        return out


def build_spans(events: Sequence[mixsamples.Event],
                samples: dict[int, array.array],
                frames_per_bar: float) -> tuple[list, int]:
    """Turn placements into ``(start, pcm, left, right)`` spans.

    Args:
        events: Placements from the event table.
        samples: Decoded samples keyed by id.
        frames_per_bar: Frames per bar at the mix tempo.

    Returns:
        The spans and the number of frames they cover.
    """
    spans = []
    for event in events:
        pcm = samples.get(event.sample_id)
        if not pcm:
            continue
        start = int(round((event.bar - 1.0) * frames_per_bar))
        left_gain, right_gain = track_gains(event.track)
        spans.append((start, pcm, left_gain, right_gain))
    total = max((span[0] + len(span[1]) for span in spans), default=0)
    return spans, total


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    return "%d:%05.2f" % (minutes, seconds - 60 * minutes)


def _describe(entry: mixsamples.Sample | None) -> str:
    if entry is None:
        return "?"
    return f"{entry.label} ({entry.name})"


def list_events(mix_path: Path, events: Sequence[mixsamples.Event],
                index: dict[int, mixsamples.Sample], bpm: float) -> int:
    """Print the placements without opening a device.

    Args:
        mix_path: The mix file.
        events: The parsed placements.
        index: Sample records used for names and offsets.
        bpm: Tempo used for the timeline.

    Returns:
        Zero.
    """
    frames_per_bar = bar_frames(bpm)
    last_bar = max((event.bar for event in events), default=1.0)
    total = (last_bar - 1.0) * frames_per_bar / SAMPLE_RATE
    print(f"{mix_path.name}  {bpm:g} bpm  {len(events)} events  "
          f"{last_bar:.2f} bars  {_format_time(total)}")
    print("     time       Tk    bar     id  sample")
    for event in sorted(events, key=lambda item: (item.bar, item.track)):
        entry = index.get(event.sample_id)
        seconds = (event.bar - 1.0) * frames_per_bar / SAMPLE_RATE
        offset = f"0x{entry.offset:08X}" if entry else "-"
        print(f"  {_format_time(seconds):>8}  T{event.track:<2d} "
              f"{event.bar:7.3f}  {event.sample_id:04X}  "
              f"{_describe(entry):30s} {offset}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdmixplayer2",
        description="Play a Techno eJay .MIX arrangement through "
                    "sounddevice, without the ported engine.")
    parser.add_argument("input", metavar="MIX",
                        help=".MIX file to play")
    parser.add_argument("-i", "--inf", default=None, metavar="FILE",
                        help="RAVE20.INF sample index "
                             "(default: next to the mix)")
    parser.add_argument("-a", "--archive", default=None, metavar="FILE",
                        help="RAVE20 sample archive "
                             "(default: next to the index)")
    parser.add_argument("-b", "--bpm", type=float, default=None,
                        help="tempo in beats per minute "
                             "(default: header word, 140)")
    parser.add_argument("-l", "--list", action="store_true",
                        help="print the placements and exit")
    parser.add_argument("--strict", action="store_true",
                        help="fail instead of skipping unusable samples")
    parser.add_argument("-d", "--device", default=None, metavar="DEV",
                        help="output device (index or name substring)")
    parser.add_argument("--block", type=int, default=BLOCK_FRAMES, metavar="N",
                        help="mix/write block in frames (default: %d)"
                             % BLOCK_FRAMES)
    parser.add_argument("-g", "--gain", type=float, default=1.0,
                        help="mix gain (default: 1.0)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="only report errors")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="report each sound as it starts to play")
    return parser


def play(args: argparse.Namespace, stream=None) -> int:
    """Play (or list) one arrangement; returns a process status.

    Args:
        args: Parsed command line.
        stream: An already-open output stream, or None to open one.

    Returns:
        Zero on success, one on error, 130 when interrupted.
    """
    mix_path = Path(args.input)
    try:
        data = mixsamples.read_mix(mix_path)
        events = mixsamples.read_events(data)
        inf_path, archive_path = find_paths(
            mix_path, args.inf, args.archive)
        index = mixsamples.read_index(inf_path)
    except (mixsamples.MixError, PlayerError) as exc:
        print(f"sdmixplayer2: {exc}", file=sys.stderr)
        return 1

    bpm = float(args.bpm) if args.bpm else header_bpm(data)
    if bpm <= 0:
        print("sdmixplayer2: --bpm must be positive", file=sys.stderr)
        return 1
    if args.list:
        return list_events(mix_path, events, index, bpm)

    try:
        samples, errors = load_samples(events, index, archive_path)
    except PlayerError as exc:
        print(f"sdmixplayer2: {exc}", file=sys.stderr)
        return 1
    if errors:
        if args.strict:
            for message in errors:
                print(f"sdmixplayer2: {message}", file=sys.stderr)
            return 1
        if not args.quiet:
            for message in errors:
                print(f"sdmixplayer2: skipped {message}", file=sys.stderr)
        events = [event for event in events
                  if event.sample_id in samples]
    if not events:
        print("sdmixplayer2: no playable samples left", file=sys.stderr)
        return 1

    spans, total = build_spans(events, samples, bar_frames(bpm))
    if not spans or total <= 0:
        print("sdmixplayer2: the arrangement is empty", file=sys.stderr)
        return 1
    mixer = Mixer(spans, total, gain=args.gain)

    if stream is None:
        try:
            stream = sdmixplay.open_stream(args.device, args.block,
                                           channels=2)
        except sdmixplay.MixError as exc:
            print(f"sdmixplayer2: {exc}", file=sys.stderr)
            return 1
        owned = True
    else:
        owned = False

    if not args.quiet:
        print(f"{mix_path.name}  {bpm:g} bpm  {len(events)} events  "
              f"{total / SAMPLE_RATE:.2f} s  via sounddevice")
    try:
        block = max(64, int(args.block))
        for start in range(0, total, block):
            count = min(block, total - start)
            stream.write(sdmixplay.pcm_bytes(mixer.mix(start, count)))
    except KeyboardInterrupt:
        if not args.quiet:
            print("sdmixplayer2: interrupted", file=sys.stderr)
        return 130
    finally:
        if owned:
            try:
                stream.stop()
            finally:
                stream.close()

    if not args.quiet:
        print("done")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.gain <= 0:
        parser.error("--gain must be positive")
    if args.block <= 0:
        parser.error("--block must be positive")
    return play(args)


if __name__ == "__main__":
    raise SystemExit(main())
