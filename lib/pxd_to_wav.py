"""Convert eJay ``tPxd`` (``.pxd``) streams to WAV files.

    python lib/pxd_to_wav.py song.pxd                    # -> song.wav
    python lib/pxd_to_wav.py *.pxd -o out/               # batch
    python lib/pxd_to_wav.py song.pxd --raw -o out/      # headerless PCM

Decodes through :mod:`pxd_file` (DPCM stream, docs/formats/PXD_FORMAT.md) and
writes a mono 16-bit 44.1 kHz WAV - what the engine's ``RWavToTemp``
conversion produces for a ``tPxD`` input, including its 44-byte RIFF
header.  ``--raw`` writes the same PCM without the header (``.pcm``).

Standard library only.
"""

from __future__ import annotations

import argparse
import os
import sys
import wave

try:
    import pxd_file
except ImportError:                      # invoked from another directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pxd_file

SAMPLE_RATE = pxd_file.PXD_SAMPLE_RATE
WAV_EXT = ".wav"                         # 44-byte RIFF/PCM mono
RAW_EXT = ".pcm"                         # headerless mono 16-bit, little-endian

__all__ = ["SAMPLE_RATE", "WAV_EXT", "RAW_EXT",
           "build_parser", "output_path", "convert", "main"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxd_to_wav",
        description="Convert eJay tPxD streams (.pxd) to WAV files, "
                    "decoding via lib/pxd_file.py.")
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help="source file(s)")
    p.add_argument("-o", "--outdir", metavar="DIR", default=None,
                   help="output directory (default: next to each input)")
    p.add_argument("--raw", action="store_true",
                   help="write headerless mono 16-bit PCM (%s)" % RAW_EXT)
    p.add_argument("-f", "--force", action="store_true",
                   help="overwrite existing output files")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    return p


def output_path(src: str, outdir: str | None, raw: bool) -> str:
    """Default output path: the input's stem, next to it or in ``outdir``."""
    stem, _ = os.path.splitext(os.path.basename(src))
    ext = RAW_EXT if raw else WAV_EXT
    return os.path.join(outdir if outdir else os.path.dirname(src) or ".",
                        stem + ext)


def _ensure_dir(outdir: str | None) -> str | None:
    if outdir:
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as exc:
            return str(exc)
    return None


def convert(args: argparse.Namespace, src: str) -> str | None:
    """Decode ``src`` and write the result; returns an error or None."""
    dst = output_path(src, args.outdir, args.raw)
    if os.path.abspath(dst) == os.path.abspath(src):
        return "%s: refusing to overwrite the input" % src
    if os.path.exists(dst) and not args.force:
        return "%s: %s exists (use --force)" % (src, dst)
    if not os.path.isfile(src):
        return "%s: no such file" % src

    err = _ensure_dir(args.outdir)
    if err:
        return "%s: %s" % (src, err)

    try:
        f = pxd_file.PxdFile(src)
        head = f.header()
        samples = f.samples()
    except pxd_file.PxdError as exc:
        return "%s: %s" % (src, exc)

    # The decoder output is little-endian int16 (array 'h', byteswapped on
    # big-endian platforms), exactly the PCM bytes the WAV/Raw stores.
    if sys.byteorder == "big":
        samples.byteswap()
    pcm = samples.tobytes()
    if sys.byteorder == "big":
        samples.byteswap()                # restore for reuse

    try:
        if args.raw:
            with open(dst, "wb") as fh:
                fh.write(pcm)
        else:
            with wave.open(dst, "wb") as fh:
                fh.setnchannels(1)
                fh.setsampwidth(2)
                fh.setframerate(SAMPLE_RATE)
                fh.writeframes(pcm)
    except OSError as exc:
        return "%s: %s: %s" % (src, dst, exc)

    if not args.quiet:
        secs = head.frame_count / float(SAMPLE_RATE)
        print("%s -> %s  %d frames  %.2f s  %d bytes"
              % (src, dst, len(samples), secs,
                 len(pcm) + (44 if not args.raw else 0)))
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    failures = 0
    for src in args.inputs:
        err = convert(args, src)
        if err:
            failures += 1
            print("pxd_to_wav: " + err, file=sys.stderr)
    if failures and not args.quiet:
        print("pxd_to_wav: %d of %d file(s) failed"
              % (failures, len(args.inputs)), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
