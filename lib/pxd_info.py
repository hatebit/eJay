"""Print summary information about eJay ``tPxd`` (``.pxd``) files.

    python lib/pxd_info.py data/hyper-test.pxd
    python lib/pxd_info.py --samples data/hyper-test.pxd

Header facts come from :mod:`pxd_file` (the container is documented in
``docs/formats/PXD_FORMAT.md``).  Comment lines are shown with the sample
bank's library-record semantics (name, producer, category, bar size;
docs/formats/PXD_FORMAT.md, "Comment-line semantics").  ``--samples``
additionally decodes the DPCM stream and reports statistics of the mono
16-bit output at 44.1 kHz - what the engine's file conversion produces.
Standard library only; one input line per file, non-zero exit if a file
fails.
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

__all__ = ["info", "build_parser", "main"]


def _hex2(marker) -> str:
    return " ".join("%02x" % b for b in marker)


def _comment_rows(c: pxd_file.PxdComment) -> list:
    """Render one comment's lines with the library-record labels.

    Six-line records get the field labels of ``docs/formats/PXD_FORMAT.md``;
    line 4 (always empty) and the bar size (line 6, ``58800`` frames)
    are summarized instead of echoed raw.  Other shapes (e.g. the
    one-line ``EJAY\\INTRO.PXD``) show their lines as-is.
    """
    if not c.is_record:
        return ["      %r" % line for line in c.lines]
    labels = ["name 1", "name 2", "producer", "line 4", "category",
              "bar size"]
    # Hyper-bank records carry a sequential id on line 2, not a name
    # part (docs/formats/PXD_FORMAT.md, "Comment-line semantics").
    if c.category == "hyper":
        labels[1] = "hyper id"
    rows = []
    for label, text in zip(labels, c.lines):
        if label == "line 4" and not text:
            rows.append("      %-9s (empty)" % label)
        elif label == "bar size" and c.bar_frames is not None:
            rows.append(
                "      %-9s %d frames (one bar, %.3f s)%s"
                % (label, c.bar_frames,
                   c.bar_frames / pxd_file.PXD_SAMPLE_RATE,
                   "  [the grid quantum]" if c.bar_frames
                   == pxd_file.BANK_BAR_FRAMES else ""))
        else:
            rows.append("      %-9s %r" % (label, text))
    return rows


def _bars(frames, unit) -> str:
    """Describe ``frames`` in bars of ``unit``, always rounded up.

    Exact multiples show as whole bars; everything else as the ceiling
    with a ``~`` marker (a 14 700-frame hyper one-shot: ``~1 bar``).
    The ceiling covers the fractional lengths and the four documented
    exporter-rounding files (``HYPER_GENERATOR.md`` §2).
    """
    whole, rem = divmod(frames, unit)
    if rem == 0:
        return "%d bar%s" % (whole, "" if whole == 1 else "s")
    up = whole + 1
    return "~%d bar%s" % (up, "" if up == 1 else "s")


def info(path, samples=False) -> str:
    """Return the report for one ``.pxd`` file as a string."""
    f = pxd_file.PxdFile(path)
    head = f.header()
    size = os.path.getsize(path)
    c = head.comment
    lines = [
        path,
        "  magic      '%s'" % pxd_file.PXD_MAGIC.decode("ascii"),
        "  comment    %d bytes, %d %s"
        % (c.length, len(c.lines),
           "lines (library record)" if c.is_record else "line(s)"),
    ]
    lines += _comment_rows(c)
    unit = c.bar_frames or pxd_file.BANK_BAR_FRAMES
    lines += [
        "  marker     %s  (skip-tag, meaning unverified)" % _hex2(head.marker),
        "  frames     %d mono samples at %d Hz (%.3f s, %s)"
        % (head.frame_count, pxd_file.PXD_SAMPLE_RATE,
           head.duration_seconds, _bars(head.frame_count, unit)),
        "  stream     %d bytes at offset %d (file is %d bytes)"
        % (size - head.data_offset, head.data_offset, size),
    ]
    if samples:
        pcm = f.samples()
        nonzero = [i for i, v in enumerate(pcm) if v]
        lines.append(
            "  samples    %d decoded (%d requested)"
            % (len(pcm), head.frame_count))
        if nonzero:
            lines.append(
                "  decoded    min/max %d / %d, sum %d"
                % (min(pcm), max(pcm), sum(pcm)))
            had_sound = len(nonzero) > 0
            tail = len(pcm) - nonzero[-1] - 1
            if tail:
                lines.append(
                    "             %d trailing silent frames%s"
                    % (tail, " (byte code ends early)" if had_sound else ""))
        else:
            lines.append("  decoded    all frames silent")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pxd_info",
        description="Print summary information about eJay tPxD (.pxd) "
                    "audio files.")
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help="one or more .pxd files")
    p.add_argument("-s", "--samples", action="store_true",
                   help="decode the DPCM stream and print sample "
                        "statistics (slower)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    status = 0
    for path in args.inputs:
        try:
            print(info(path, samples=args.samples), end="")
        except pxd_file.PxdError as exc:
            print("pxd_info: %s" % exc, file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
