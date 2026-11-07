"""Play a PXD32D5 stream on the speakers - the playback demo.

    python src/pxdplay.py data/bo-test.pxd             # sounddevice (default)
    python src/pxdplay.py song.pxd --device Speakers   # pick an output
    python src/pxdplay.py --list-devices               # list outputs
    python src/pxdplay.py song.pxd --sink waveout      # Windows waveOut

The engine runs exactly as the DLL does -- ``PInit`` -> ``PStart`` ->
``PPlay(path, ...)`` -> ``PClose`` -- with the player thread feeding an
``OutputSink`` from ``pxdsink``.  The default sink is
``pxdsink.SoundDeviceSink`` (needs ``pip install sounddevice``); ``--sink
waveout`` uses the standard-library ``ctypes`` backend instead.

``PPlay``'s ``a3``/``a5`` are ring *positions*, not a duration: the request is
queued at the current play position and runs to ``play_position() + length``,
where ``length`` is ``awave_dauer(path)`` (4 bytes per stereo frame).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import pxd32d5
import pxdsink

SAMPLE_RATE = 44100
BYTES_PER_FRAME = 4             # 16 bit stereo, the ring format
END_TIMEOUT_EXTRA = 5.0         # slack before declaring "did not finish"
TAIL_DRAIN = 0.3                # let the device buffer play out before close


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxdplay",
        description="Play a PXD32D5 stream (.pxd, RIFF/WAVE) on the speakers.")
    p.add_argument("input", nargs="?", metavar="INPUT",
                   help="source file to play")
    p.add_argument("-s", "--sink", choices=("sounddevice", "waveout"),
                   default="sounddevice",
                   help="audio backend (default: sounddevice)")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device for the sounddevice sink (index or "
                        "name substring); see --list-devices")
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="engine gain passed to PInit (default: 1.0)")
    p.add_argument("-l", "--list-devices", action="store_true",
                   help="list sounddevice output devices and exit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def open_sink(args: argparse.Namespace) -> pxdsink.OutputSink:
    """Create the requested backend (its device opens immediately)."""
    if args.sink == "waveout":
        return pxdsink.WaveOutSink()
    device = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    return pxdsink.SoundDeviceSink(device=device)


def list_devices() -> int:
    try:
        import sounddevice
    except ImportError as exc:
        print("pxdplay: %s" % exc, file=sys.stderr)
        return 1
    try:
        print(sounddevice.query_devices())
    except sounddevice.PortAudioError as exc:
        print("pxdplay: %s" % exc, file=sys.stderr)
        return 1
    return 0


def play(args: argparse.Namespace) -> int:
    src = args.input
    if not os.path.isfile(src):
        print("pxdplay: %s: no such file" % src, file=sys.stderr)
        return 1
    length = pxd32d5.awave_dauer(src)       # ring bytes, 4 per stereo frame
    if length <= 0:
        print("pxdplay: %s: not a decodable PXD/WAVE stream" % src,
              file=sys.stderr)
        return 1

    try:
        sink = open_sink(args)
    except (ImportError, OSError) as exc:
        print("pxdplay: cannot open the %s sink: %s" % (args.sink, exc),
              file=sys.stderr)
        return 1

    frames = length // BYTES_PER_FRAME
    seconds = frames / float(SAMPLE_RATE)

    pxd32d5.PInit(args.gain)
    engine = pxd32d5.engine
    engine.sink = sink          # PInit has run, so nothing closes it under us
    try:
        pxd32d5.PStart()
        start = engine.play_position()
        pxd32d5.PPlay(src, 0, start, 0, start + length, 0)
        if not args.quiet:
            print("%s  %d frames  %.2f s  via %s"
                  % (src, frames, seconds, args.sink))
        deadline = time.monotonic() + seconds + END_TIMEOUT_EXTRA
        while not engine.word_10083528 and time.monotonic() < deadline:
            time.sleep(0.02)
        if not engine.word_10083528:
            print("pxdplay: playback did not finish (timeout)",
                  file=sys.stderr)
            return 1
        time.sleep(TAIL_DRAIN)  # PClose aborts the sink; let the tail play
    except KeyboardInterrupt:
        if not args.quiet:
            print("pxdplay: interrupted", file=sys.stderr)
        return 130
    finally:
        pxd32d5.PClose()
    if not args.quiet:
        print("done")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_devices:
        return list_devices()
    if args.input is None:
        build_parser().error("the following arguments are required: INPUT")
    return play(args)


if __name__ == "__main__":
    sys.exit(main())
