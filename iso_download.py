"""Download an ISO file listed in an index JSON file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError


def format_seconds(seconds: float | None) -> str:
    """Format a duration in seconds as H:MM:SS or M:SS.

    Args:
        seconds: Duration in seconds, or None if unknown.

    Returns:
        A human-readable duration string.
    """
    if seconds is None or seconds < 0:
        return "unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        num_bytes: Number of bytes.

    Returns:
        A human-readable byte string (e.g. ``1.23 MB``).
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            if unit == "B":
                return f"{num_bytes} {unit}"
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="Download an ISO file from an index JSON file.",
    )
    parser.add_argument(
        "-o",
        "--iso",
        default="./iso",
        help="Directory to save the downloaded ISO (default: ./iso)",
    )
    parser.add_argument(
        "-i",
        "--index",
        default="./iso/index.json",
        help="Path to the index JSON file (default: ./iso/index.json)",
    )
    parser.add_argument(
        "key",
        help="Index key identifying the ISO to download.",
    )
    return parser.parse_args(argv)


def load_index(path: Path) -> dict[str, dict]:
    """Load the index JSON file.

    Args:
        path: Path to the index JSON file.

    Returns:
        The parsed index mapping keys to metadata dicts.

    Raises:
        SystemExit: If the file cannot be read or parsed.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: failed to read index '{path}': {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def find_url(index: dict[str, dict], key: str) -> str | None:
    """Find the download URL for an index key (case-insensitive).

    Args:
        index: The loaded index mapping.
        key: The key to look up.

    Returns:
        The download URL, or None if not found or null.
    """
    for entry_key, entry in index.items():
        if entry_key.lower() == key.lower():
            url = entry.get("iso")
            return str(url) if url else None
    return None


def download(url: str, output_dir: Path, key: str) -> None:
    """Download a file from a URL with a progress display.

    Args:
        url: The URL to download.
        output_dir: Directory to save the file into.
        key: The index key (used for the output filename).

    Raises:
        SystemExit: If the download fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{key}.iso"

    try:
        response = urlopen(url)
    except (URLError, HTTPError, OSError) as exc:
        print(f"Error: failed to open URL '{url}': {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    total_size = response.headers.get("Content-Length")
    total_size = int(total_size) if total_size else None

    start_time = time.monotonic()
    downloaded = 0
    block_size = 8192

    try:
        with output_path.open("wb") as out_file:
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)

                elapsed = time.monotonic() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0.0

                if total_size:
                    percent = downloaded / total_size * 100
                    remaining = (total_size - downloaded) / speed if speed > 0 else None
                    bar_width = 30
                    filled = int(bar_width * downloaded // total_size) if total_size else 0
                    bar = "#" * filled + "-" * (bar_width - filled)
                    eta = format_seconds(remaining)
                    print(
                        f"\r[{bar}] {percent:5.1f}%  "
                        f"{format_bytes(downloaded)} / {format_bytes(total_size)}  "
                        f"{format_bytes(int(speed))}/s  "
                        f"elapsed {format_seconds(elapsed)}  "
                        f"left {eta}",
                        end="",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"\r{format_bytes(downloaded)}  "
                        f"{format_bytes(int(speed))}/s  "
                        f"elapsed {format_seconds(elapsed)}",
                        end="",
                        file=sys.stderr,
                    )
    except OSError as exc:
        print(f"\nError: failed to write to '{output_path}': {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        response.close()

    elapsed = time.monotonic() - start_time
    print(
        f"\nDownloaded '{key}.iso' to '{output_path}' "
        f"({format_bytes(downloaded)} in {format_seconds(elapsed)})",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    """Entry point for the download_iso CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).
    """
    args = parse_args(argv)
    index_path = Path(args.index)
    target_dir = Path(args.iso)

    index = load_index(index_path)
    url = find_url(index, args.key)

    if url is None:
        print(
            f"Error: key '{args.key}' not found in index or has no ISO URL.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    download(url, target_dir, args.key)


if __name__ == "__main__":
    main()
