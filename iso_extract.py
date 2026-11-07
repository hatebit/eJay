"""Extract an ISO file listed in an index JSON file to disk."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pycdlib


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        The parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="Extract an ISO file into a directory.",
    )
    parser.add_argument(
        "-s",
        "--source",
        default="./iso",
        help="Directory containing the ISO file (default: ./iso)",
    )
    parser.add_argument(
        "-i",
        "--index",
        default="./iso/index.json",
        help="Path to the index JSON file (default: ./iso/index.json)",
    )
    parser.add_argument(
        "-t",
        "--target",
        default="./disks",
        help="Base directory for extraction (default: ./disk)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove the ISO file after extraction",
    )
    parser.add_argument(
        "key",
        help="Index key identifying the ISO to extract.",
    )
    return parser.parse_args(argv)


def load_index(path: Path) -> dict[str, dict]:
    """Load the index JSON file.

    Args:
        path: Path to the index JSON file.

    Returns:
        The parsed index mapping keys to metadata dicts.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: failed to read index '{path}': {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def find_entry(index: dict[str, dict], key: str) -> tuple[str, dict] | tuple[None, None]:
    """Find an index entry by key (case-insensitive).

    Args:
        index: The loaded index mapping.
        key: The key to look up.

    Returns:
        A tuple of (canonical_key, entry) or (None, None) if not found.
    """
    for entry_key in index:
        if entry_key.lower() == key.lower():
            return entry_key, index[entry_key]
    return None, None


def split_rel(path: str) -> tuple[str, ...]:
    """Split a relative path into its components.

    Args:
        path: A path using ``/`` separators, possibly with leading or
            trailing slashes.

    Returns:
        The non-empty path components as a tuple.
    """
    return tuple(part for part in path.strip("/").split("/") if part)


def fold_rel(parts: tuple[str, ...]) -> tuple[str, ...]:
    """Case-fold path components so skip matching is case-insensitive.

    Args:
        parts: Path components.

    Returns:
        The components lower-cased.
    """
    return tuple(part.lower() for part in parts)


def extract_iso(
    iso_path: Path,
    output_dir: Path,
    root: str | None = None,
    skip: set[tuple[str, ...]] | None = None,
) -> None:
    """Extract files from an ISO into a directory.

    Only the contents of ``root`` (an ISO directory name) are extracted;
    when ``root`` is ``None`` the whole ISO is extracted. The ``root``
    directory itself is not recreated in ``output_dir``: files that sit
    directly in it are written straight into ``output_dir``. Paths in
    ``skip`` are relative to ``root`` and may denote files or directories;
    matched entries are not copied and skipped directories are not descended
    into. Skip matching is case-insensitive. When the ISO has a Joliet
    extension its (long, mixed-case) names are used, otherwise the plain
    ISO9660 names are used.

    Args:
        iso_path: Path to the ISO file.
        output_dir: Directory to extract files into.
        root: ISO directory whose contents are extracted, or None for all.
        skip: Skip-path component tuples relative to ``root``.
    """
    iso = pycdlib.PyCdlib()
    iso.open(str(iso_path))

    try:
        skip_set = {fold_rel(parts) for parts in (skip or set())}
        # Prefer the Joliet tree: it carries the real long file names that
        # the skip list is written against (ISO9660 names are mangled 8.3).
        ns = "joliet_path" if iso.has_joliet() else "iso_path"
        print(f"Using {'Joliet' if ns == 'joliet_path' else 'ISO9660'} namespace")
        resolved = None  # actual case of the root directory
        for dirpath, dirnames, filenames in iso.walk(**{ns: "/"}):
            if root:
                if dirpath == "/":
                    # Locate the root directory case-insensitively
                    # (read-only; do not prune dirnames here, as that
                    # corrupts pycdlib's file listings for the kept
                    # directory). The top level itself is never extracted.
                    for d in dirnames:
                        if d.lower() == root.lower():
                            resolved = d
                            break
                    continue
                if not resolved:
                    continue
                prefix = "/" + resolved + "/"
                if dirpath == "/" + resolved:
                    # The root directory's own files belong to the output.
                    rel_parts: tuple[str, ...] = ()
                elif dirpath.startswith(prefix):
                    rel_parts = split_rel(dirpath[len(prefix):])
                else:
                    continue
            else:
                rel_parts = split_rel(dirpath)

            # Prune skipped directories so they are never descended into.
            dirnames[:] = [
                d
                for d in dirnames
                if fold_rel(rel_parts + (d,)) not in skip_set
            ]
            if fold_rel(rel_parts) in skip_set:
                continue
            print(f"Processing: {dirpath}")
            target_dir = output_dir / Path(*rel_parts) if rel_parts else output_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in filenames:
                clean = name.split(";")[0]
                if fold_rel(rel_parts + (clean,)) in skip_set:
                    print(f"Skipping: {dirpath.rstrip('/')}/{clean}")
                    continue
                iso_file_path = f"/{name}" if dirpath == "/" else f"{dirpath}/{name}"
                iso.get_file_from_iso(
                    local_path=str(target_dir / clean),
                    **{ns: iso_file_path},
                )
        if root and resolved is None:
            raise FileNotFoundError(
                f"root directory '{root}' not found in ISO '{iso_path}'"
            )
    finally:
        iso.close()


def main(argv: list[str] | None = None) -> None:
    """Entry point for the extract_iso CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).
    """
    args = parse_args(argv)
    index_path = Path(args.index)
    source_dir = Path(args.source)
    target_dir = Path(args.target)

    index = load_index(index_path)
    canonical_key, entry = find_entry(index, args.key)

    if canonical_key is None or entry is None:
        print(f"Error: key '{args.key}' not found in index.", file=sys.stderr)
        raise SystemExit(1)

    iso_url = entry.get("iso")
    iso_filename = None
    if iso_url:
        iso_filename = Path(str(iso_url)).name
    if not iso_filename:
        iso_filename = f"{canonical_key}.iso"

    iso_path = source_dir / iso_filename
    if not iso_path.exists():
        alt = source_dir / f"{args.key}.iso"
        if alt.exists():
            iso_path = alt
        else:
            alt2 = source_dir / f"{canonical_key}.iso"
            if alt2.exists():
                iso_path = alt2
            else:
                print(f"Error: ISO file not found: {iso_path}", file=sys.stderr)
                raise SystemExit(1)

    skip_dirs = set(entry.get("skip", []))
    skip = {split_rel(path) for path in skip_dirs if path.strip("/")}
    root = entry.get("root")

    target_dir = target_dir / canonical_key.replace(" ", "_")
    print(f"Extracting '{canonical_key}' to '{target_dir}'")

    try:
        extract_iso(iso_path, target_dir, root=root, skip=skip)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.clean:
        print(f"Cleaning up '{iso_path}'...")
        iso_path.unlink(missing_ok=True)

    print("Done.")


if __name__ == "__main__":
    main()
