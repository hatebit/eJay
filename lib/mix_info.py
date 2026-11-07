"""Print summary information about eJay `.MIX` arrangement files.

    python libs/mix_info.py disk/MIX/TRANCE.MIX
    python libs/mix_info.py --events disk/MIX/TRANCE.MIX

Header facts come from :mod:mix_file (the container is documented in
`docs/formats/MIX_FORMAT_RAVE.md`).  `--events` lists arrangement events by
resolving sample IDs through a sample index if provided.
Standard library only; one input line per file, non-zero exit if a file
fails.
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import mix_file
except ImportError:  # invoked from another directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mix_file

__all__ = ["info", "build_parser", "main"]


def info(path: str, events: bool = False, index_path: str | None = None,
         bpm: float = mix_file.DEFAULT_BPM,
         beats: float = mix_file.DEFAULT_BEATS) -> str:
    """Return the report for one `.mix` file as a string."""
    m = mix_file.MixFile(path)
    head = m.header()
    inf = m.info()
    size = os.path.getsize(path)
    lines = [
        path,
        "  magic      0x%04X (%s)" % (head.header_word, mix_file.MIX_MAGIC == head.header_word and "'\\x07\\x0a'" or "t?"),
        "  version    %r" % head.version,
        "  records    %d total, %d used" % (head.record_count, inf.used_records),
        "  file       %d bytes" % size,
    ]
    if events:
        idx = None
        if index_path:
            try:
                idx = mix_file.read_index(index_path)
            except Exception as exc:
                lines.append("  index      %s: %s" % (index_path, exc))
        evs = m.events(index=idx, bpm=bpm, beats=beats)
        lines.append("  events     %d" % len(evs))
        s_frames = mix_file.step_frames(bpm, beats)
        for ev in evs:
            t_sec = ev.time_frames / float(mix_file.SAMPLE_RATE)
            desc = ""
            if ev.sample_path:
                desc = "  %s" % ev.sample_path
            if ev.sample_name:
                desc += "  [%s]" % ev.sample_name
            lines.append(
                "    rec %3d  %7.2fs  T%d/%s  ID 0x%03X%s"
                % (ev.record, t_sec, ev.track, ev.lane, ev.sample_id, desc)
            )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mix_info",
        description="Print summary information about eJay .mix arrangement files.",
    )
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help="one or more .mix files")
    p.add_argument("-e", "--events", action="store_true",
                   help="list arrangement events (collapsed runs)")
    p.add_argument("-i", "--index", metavar="PATH",
                   help="path to sample index EJAY/PXD for name resolution")
    p.add_argument("--bpm", type=float, default=mix_file.DEFAULT_BPM,
                   help="bpm for time calculation (default: %.1f)" % mix_file.DEFAULT_BPM)
    p.add_argument("--beats", type=float, default=mix_file.DEFAULT_BEATS,
                   help="beats per record (default: %.1f)" % mix_file.DEFAULT_BEATS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    status = 0
    for path in args.inputs:
        try:
            print(info(path, events=args.events, index_path=args.index,
                       bpm=args.bpm, beats=args.beats), end="")
        except Exception as exc:
            print("mix_info: %s" % exc, file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
