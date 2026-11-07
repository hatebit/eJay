"""Play one PXD32D5 stream through sounddevice, without the ported engine.

    python src/sdpxdplay.py data/bo-test.pxd
    python src/sdpxdplay.py song.wav -d Speakers
    python src/sdpxdplay.py --list-devices

The standalone twin of ``pxdplay.py``: it decodes the file itself (``tPxd``
or RIFF/WAVE PCM, via ``sdmixplay.decode_sample``) and writes 16-bit mono at
44.1 kHz to a ``sounddevice.RawOutputStream``.  Nothing here imports
``pxd32d5`` or ``pxdsink``, so the engine's play ring, player thread and
command queue are not involved.

Formats are documented in ``docs/PXD_FORMAT.md`` (``tPxd``) and
``docs/RWavToTemp.md`` (RIFF/PCM).  The engine's converter keeps the left
channel, so a stereo input is played as its left channel, exactly as in
``sdmixplay``.
"""

from __future__ import annotations

import argparse
import os
import sys

import sdmixplay

SAMPLE_RATE = sdmixplay.SAMPLE_RATE
BLOCK_FRAMES = sdmixplay.BLOCK_FRAMES

__all__ = [
    "SAMPLE_RATE",
    "BLOCK_FRAMES",
    "build_parser",
    "list_devices",
    "apply_gain",
    "play",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sdpxdplay",
        description="Play one PXD32D5 stream (.pxd, RIFF/WAVE) through "
                    "sounddevice, without the ported engine.")
    p.add_argument("input", nargs="?", metavar="INPUT",
                   help="source file to play")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device (index or name substring); see "
                        "--list-devices")
    p.add_argument("--block", type=int, default=BLOCK_FRAMES, metavar="N",
                   help="write block in frames (default: %d)" % BLOCK_FRAMES)
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="sample gain (default: 1.0)")
    p.add_argument("-l", "--list-devices", action="store_true",
                   help="list sounddevice output devices and exit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def list_devices() -> int:
    try:
        import sounddevice
    except ImportError as exc:
        print("sdpxdplay: %s" % exc, file=sys.stderr)
        return 1
    try:
        print(sounddevice.query_devices())
    except sounddevice.PortAudioError as exc:
        print("sdpxdplay: %s" % exc, file=sys.stderr)
        return 1
    return 0


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


def play(args, stream=None) -> int:
    """Decode and play ``args.input``; returns a process status."""
    src = args.input
    if not os.path.isfile(src):
        print("sdpxdplay: %s: no such file" % src, file=sys.stderr)
        return 1
    try:
        samples = sdmixplay.decode_sample(src)
    except sdmixplay.MixError as exc:
        print("sdpxdplay: %s" % exc, file=sys.stderr)
        return 1
    if not samples:
        print("sdpxdplay: %s: no audio data" % src, file=sys.stderr)
        return 1

    apply_gain(samples, args.gain)

    if stream is None:
        try:
            stream = sdmixplay.open_stream(args.device, args.block)
        except sdmixplay.MixError as exc:
            print("sdpxdplay: %s" % exc, file=sys.stderr)
            return 1
        owned = True
    else:
        owned = False

    frames = len(samples)
    seconds = frames / float(SAMPLE_RATE)
    if not args.quiet:
        print("%s  %d frames  %.2f s  via sounddevice"
              % (src, frames, seconds))

    try:
        block = max(64, int(args.block))
        for start in range(0, frames, block):
            stream.write(sdmixplay.pcm_bytes(samples[start:start + block]))
    except KeyboardInterrupt:
        if not args.quiet:
            print("sdpxdplay: interrupted", file=sys.stderr)
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
