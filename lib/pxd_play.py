"""Play one eJay ``tPxd`` stream through ``sounddevice``.

    python lib/pxd_play.py data/hyper-test.pxd
    python lib/pxd_play.py -d Speakers data/hyper-test.pxd
    python lib/pxd_play.py --list-devices

Decodes the ``tPxd`` container itself through :mod:`pxd_file` (the DPCM
stream, docs/formats/PXD_FORMAT.md) and writes the mono 16-bit output at 44.1 kHz
to a ``sounddevice.RawOutputStream``.  This is the standalone twin of
``work/src/sdpxdplay.py`` without the engine: no ``pxd32d5``, no ring, no
mixer - the file is decoded first, then streamed.

``sounddevice`` is an optional dependency and imported lazily, so
``--list-devices`` is the only command that needs it (besides playing).
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import pxd_file
except ImportError:                      # invoked from another directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pxd_file

SAMPLE_RATE = pxd_file.PXD_SAMPLE_RATE

__all__ = ["SAMPLE_RATE", "build_parser", "list_devices",
           "apply_gain", "pcm_bytes", "play", "main"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxd_play",
        description="Play one eJay tPxD stream (.pxd) through sounddevice, "
                    "decoding it via lib/pxd_file.py.")
    p.add_argument("input", nargs="?", metavar="INPUT",
                   help="source file to play")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device (index or name substring); see "
                        "--list-devices")
    p.add_argument("--block", type=int, default=945, metavar="N",
                   help="write block in frames (default: 945)")
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="sample gain (default: 1.0; the decoded stream "
                        "already carries the 2x conversion gain)")
    p.add_argument("-l", "--list-devices", action="store_true",
                   help="list sounddevice output devices and exit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def _import_sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        print("pxd_play: sounddevice not installed "
              "('pip install sounddevice'): %s" % exc, file=sys.stderr)
        return None
    return sounddevice


def list_devices() -> int:
    sd = _import_sounddevice()
    if sd is None:
        return 1
    try:
        print(sd.query_devices())
        return 0
    except sd.PortAudioError as exc:
        print("pxd_play: %s" % exc, file=sys.stderr)
        return 1


def apply_gain(samples, gain: float) -> None:
    """Scale int16 ``samples`` in place, clipping to the int16 range."""
    if gain == 1.0:
        return
    for i, value in enumerate(samples):
        scaled = int(value * gain)
        if scaled > 0x7FFF:
            scaled = 0x7FFF
        elif scaled < -0x8000:
            scaled = -0x8000
        samples[i] = scaled


def pcm_bytes(samples) -> bytes:
    """Little-endian int16 bytes of ``array('h')`` ``samples``."""
    if sys.byteorder == "big":
        samples.byteswap()
    data = samples.tobytes()
    if sys.byteorder == "big":
        samples.byteswap()          # restore for reuse
    return data


def play(args, stream=None) -> int:
    """Decode ``args.input`` and play it; returns a process status."""
    if not os.path.isfile(args.input):
        print("pxd_play: %s: no such file" % args.input, file=sys.stderr)
        return 1

    try:
        f = pxd_file.PxdFile(args.input)
        head = f.header()
        samples = f.samples()
    except pxd_file.PxdError as exc:
        print("pxd_play: %s" % exc, file=sys.stderr)
        return 1
    if not samples:
        print("pxd_play: %s: no audio data" % args.input, file=sys.stderr)
        return 1

    apply_gain(samples, args.gain)
    frames = len(samples)

    if stream is None:
        owned = True
        sd = _import_sounddevice()
        if sd is None:
            return 1
        try:
            stream = sd.RawOutputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                device=args.device)
            stream.start()
        except sd.PortAudioError as exc:
            print("pxd_play: %s" % exc, file=sys.stderr)
            return 1
    else:
        owned = False

    if not args.quiet:
        title = head.comment.title
        print('%s  %d frames  %.2f s at %d Hz%s'
              % (args.input, frames, head.duration_seconds, SAMPLE_RATE,
                 '  "%s"' % title if title else ""))

    try:
        block = max(64, int(args.block))
        for start in range(0, frames, block):
            stream.write(pcm_bytes(samples[start:start + block]))
    except KeyboardInterrupt:
        if not args.quiet:
            print("pxd_play: interrupted", file=sys.stderr)
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


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_devices:
        return list_devices()
    if args.input is None:
        parser.error("the following arguments are required: INPUT")
    if args.gain <= 0:
        parser.error("--gain must be positive")
    if args.block <= 0:
        parser.error("--block must be positive")
    return play(args)


if __name__ == "__main__":
    sys.exit(main())
