"""Command line for the extensible mix player."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "player"

from .constants import DEFAULT_BLOCK_FRAMES, DEFAULT_GAIN, VERSION
from .mix_player import MixPlayer
from .mix_registry import MixRegistry
from .sugar import is_interactive, mix_player_logo


def build_parser(registry: MixRegistry | None = None
                 ) -> argparse.ArgumentParser:
    """Build the parser, including every registered format's options.

    Args:
        registry: Formats whose CLI options should be added.

    Returns:
        The parser.
    """
    registry = registry or MixRegistry.default()
    parser = argparse.ArgumentParser(
        prog="player",
        description="Play an eJay .MIX arrangement through sounddevice, "
                    "using the format plugin selected by the file header.",
    )
    parser.add_argument("input", metavar="MIX", help=".MIX file to play")
    parser.add_argument(
        "--format", choices=[item.name for item in registry.formats],
        default=None, help="force a format instead of detecting it")
    parser.add_argument(
        "--pxd", default=None, metavar="DIR",
        help="folder holding the sample data: the sample subfolders, or the "
             "sample archive (default: search near the mix)")
    parser.add_argument(
        "--index", default=None, metavar="FILE",
        help="sample index file (default: the index found under --pxd or "
             "near the mix)")
    parser.add_argument(
        "-b", "--bpm", type=float, default=None,
        help="tempo override in beats per minute")
    parser.add_argument(
        "-l", "--list", action="store_true",
        help="print the arrangement and exit")
    parser.add_argument(
        "--strict", action="store_true",
        help="fail instead of skipping unusable samples")
    parser.add_argument(
        "-d", "--device", default=None, metavar="DEV",
        help="output device (index or name substring)")
    parser.add_argument(
        "--block", type=int, default=DEFAULT_BLOCK_FRAMES, metavar="N",
        help="mix/write block in frames (default: %d)"
             % DEFAULT_BLOCK_FRAMES)
    parser.add_argument(
        "-g", "--gain", type=float, default=DEFAULT_GAIN,
        help="mix gain (default: 1.0)")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="only report errors")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="report each sound as it starts to play")

    for mix_format in registry.formats:
        group = parser.add_argument_group(f"{mix_format.name} format")
        mix_format.add_arguments(group)
    return parser


def options_from_namespace(namespace: argparse.Namespace,
                           registry: MixRegistry) -> dict[str, Any]:
    """Flatten a CLI namespace into the player options mapping.

    Args:
        namespace: Result of parsing with :func:`build_parser`.
        registry: Registry whose formats contribute their own options.

    Returns:
        Common options at the top level and ``formats`` holding one
        dictionary per format name.
    """
    formats: dict[str, Mapping[str, Any]] = {}
    for mix_format in registry.formats:
        formats[mix_format.name] = mix_format.options(namespace)
    return {
        "format": namespace.format,
        "pxd": namespace.pxd,
        "index": namespace.index,
        "bpm": namespace.bpm,
        "list": namespace.list,
        "strict": namespace.strict,
        "device": namespace.device,
        "block": namespace.block,
        "gain": namespace.gain,
        "quiet": namespace.quiet,
        "verbose": namespace.verbose,
        "formats": formats,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    The banner is printed after parsing, and only to an interactive terminal
    without ``--quiet`` or ``--list``, so redirected output stays clean.

    Args:
        argv: Arguments to parse; ``sys.argv[1:]`` when omitted.

    Returns:
        Zero on success, one on error, 130 when interrupted.
    """
    registry = MixRegistry.default()
    parser = build_parser(registry)
    namespace = parser.parse_args(argv)
    if namespace.gain <= 0:
        parser.error("--gain must be positive")
    if namespace.block <= 0:
        parser.error("--block must be positive")

    if is_interactive() and not namespace.quiet and not namespace.list:
        mix_player_logo()
        print(f"MixPlayer v{VERSION}")
        for mix_format in registry.formats:
            print(f"\t- {mix_format.name} v{mix_format.version}")
        print()

    options = options_from_namespace(namespace, registry)
    return MixPlayer(registry).play(Path(namespace.input), options)


if __name__ == "__main__":
    sys.exit(main())
