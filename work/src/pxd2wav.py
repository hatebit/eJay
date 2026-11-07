"""Command line front end for the pxd32d5 port.

    python pxd2wav.py song.pxd                      # -> song.wav
    python pxd2wav.py *.pxd *.wav -o out/ -t        # batch, with de-click tail
    python pxd2wav.py song.pxd --raw -o out/        # headerless mono PCM

Each input goes through `PInit` -> `RWavToTemp(input, out, 0, ...)` ->
`PClose`, exactly the sequence `RWaveLaden` drives inside the DLL.  The output
is a mono 16 bit 44.1 kHz WAV (what the engine's temp wave always is), or the
same stream without the 44-byte RIFF header with `--raw`.
"""

from __future__ import annotations

import argparse
import os
import sys

import pxd32d5

SAMPLE_RATE = 44100
WAV_EXT = ".wav"
RAW_EXT = ".pcm"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxd2wav",
        description="Convert PXD32D5 streams (.pxd, RIFF/WAVE) to WAV.")
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help="source file(s)")
    p.add_argument("-o", "--outdir", metavar="DIR", default=None,
                   help="output directory (default: next to each input)")
    p.add_argument("-t", "--tail", action="store_true",
                   help="append the 128-sample de-click ramp and pad the "
                        "result to whole 9450-byte blocks (RWavToTemp a7)")
    p.add_argument("--raw", action="store_true",
                   help="write headerless mono 16-bit PCM (%s)" % RAW_EXT)
    p.add_argument("-f", "--force", action="store_true",
                   help="overwrite existing output files")
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="engine gain passed to PInit (default: 1.0)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def output_path(src: str, outdir: str | None, raw: bool) -> str:
    stem, _ = os.path.splitext(os.path.basename(src))
    ext = RAW_EXT if raw else WAV_EXT
    return os.path.join(outdir if outdir else os.path.dirname(src) or ".",
                        stem + ext)


def convert(args: argparse.Namespace, src: str) -> str | None:
    """Convert one file. Returns an error message, or None on success."""
    dst = output_path(src, args.outdir, args.raw)
    if os.path.abspath(dst) == os.path.abspath(src):
        return "%s: refusing to overwrite the input" % src
    if os.path.exists(dst) and not args.force:
        return "%s: %s exists (use --force)" % (src, dst)
    if not os.path.isfile(src):
        return "%s: no such file" % src
    if args.outdir:
        try:
            os.makedirs(args.outdir, exist_ok=True)
        except OSError as exc:
            return "%s: %s" % (src, exc)

    tail = 1 if args.tail else 0
    try:
        rc = pxd32d5.RWavToTemp(src, dst, 0, None, 0, 0, tail)
    except pxd32d5.UnsupportedCodec as exc:
        return "%s: %s" % (src, exc)
    if rc != 0:
        return "%s: RWavToTemp failed (rc=%d)" % (src, rc)

    if not args.quiet:
        size = os.path.getsize(dst)
        data = size if args.raw else max(size - 44, 0)
        secs = data / 2.0 / SAMPLE_RATE
        print("%s -> %s  %d frames  %.2f s  %d bytes"
              % (src, dst, data // 2, secs, size))
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    pxd32d5.PInit(args.gain)
    pxd32d5.engine.output_kind = 0 if args.raw else 4
    failures = 0
    try:
        for src in args.inputs:
            err = convert(args, src)
            if err:
                failures += 1
                print("pxd2wav: " + err, file=sys.stderr)
    finally:
        pxd32d5.PClose()

    if failures and not args.quiet:
        print("pxd2wav: %d of %d file(s) failed"
              % (failures, len(args.inputs)), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
