#!/usr/bin/env python3
"""Scan every .pxd file under ``disk/RAVE`` and write a CSV of path, filename, and
header fields.

Header fields (see ``docs/PXD_FORMAT.md`` and ``src/pxd32d5.py``:
``_parse_header``):

    offset 0x00  4 bytes  magic 't','P','x','D'
    offset 0x04  1 byte   len (h[4]) - counts the comment field including itself
    offset 0x05  len-1    ASCII comment (6 lines, some may be empty)
    offset 4+len+2  4     i32 frame count (mono samples at 44.1 kHz)
    offset 4+len+8  ...   ADPCM/codebook stream data

The comment is split into a fixed 6 columns. Files that are too short, do
not start with the expected magic, or are otherwise unreadable are still
listed, with the header fields left empty.
"""

from __future__ import annotations

import csv
import os
import struct
import sys

def _find_repo_root(start: str) -> str:
    """Walk up from this script until a directory containing ``disk/RAVE`` is found."""
    cur = os.path.abspath(start)
    for _ in range(10):
        if os.path.isdir(os.path.join(cur, "disk", "RAVE")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    raise RuntimeError("could not locate repo root (no disk/RAVE directory found)")


ROOT = _find_repo_root(__file__)
RES_DIR = os.path.join(ROOT, "disk", "RAVE")
OUT_CSV = os.path.join(ROOT, "disk_RAVE_pxd_headers.csv")

MAGIC = b"tPxD"
COMMENT_LINES = 6

FIELDNAMES = [
    "file_path",
    "filename",
    "magic",
    "comment_len",
] + [f"comment_line_{i + 1}" for i in range(COMMENT_LINES)] + [
    "frame_count",
    "data_start",
]


def parse_pxd_header(path: str):
    """Return (magic, comment_len, comment_lines, frame_count, data_start) or None."""
    with open(path, "rb") as f:
        data = f.read(220)  # the DLL reads up to 220 bytes for classification

    if len(data) < 5 or data[0:4] != MAGIC:
        return None

    comment_len = data[4]
    if comment_len <= 0 or 4 + comment_len + 8 > len(data):
        return None

    comment_bytes = data[5:4 + comment_len - 1]
    try:
        comment_text = comment_bytes.decode("ascii", errors="replace")
    except Exception:
        comment_text = ""

    # Normalise CRLF to LF and split into the fixed number of lines.
    comment_text = comment_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = comment_text.split("\n")
    if len(lines) < COMMENT_LINES:
        lines = lines + [""] * (COMMENT_LINES - len(lines))
    else:
        lines = lines[:COMMENT_LINES]

    frame_count = struct.unpack_from("<i", data, 4 + comment_len + 2)[0]
    data_start = 4 + comment_len + 8
    return MAGIC.decode("ascii"), comment_len, lines, frame_count, data_start


def main() -> int:
    pxd_files = []
    for dirpath, _dirnames, filenames in os.walk(RES_DIR):
        for name in sorted(filenames):
            low = name.lower()
            if not (low.endswith(".pxd") or low.endswith(".pxd;1")):
                continue
            pxd_files.append(os.path.join(dirpath, name))

    pxd_files.sort(key=lambda p: p.lower())

    rows = []
    for full in pxd_files:
        rel = os.path.relpath(full, ROOT)
        name = os.path.basename(full)
        try:
            parsed = parse_pxd_header(full)
        except OSError as exc:
            parsed = None
            print(f"warn: could not read {rel}: {exc}", file=sys.stderr)

        row = {
            "file_path": rel,
            "filename": name,
            "magic": "",
            "comment_len": "",
            **{f"comment_line_{i + 1}": "" for i in range(COMMENT_LINES)},
            "frame_count": "",
            "data_start": "",
        }
        if parsed is not None:
            magic, comment_len, lines, frame_count, data_start = parsed
            row["magic"] = magic
            row["comment_len"] = comment_len
            for i, line in enumerate(lines):
                row[f"comment_line_{i + 1}"] = line
            row["frame_count"] = frame_count
            row["data_start"] = data_start
        rows.append(row)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Scanned {len(rows)} .pxd files -> {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())