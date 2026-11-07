# AGENTS.md — working in `player`

This file is for agents and contributors changing the `player` package. It is
narrower than [`../AGENTS.md`](../AGENTS.md); read that for the repository-wide
rules and this one for the package contract.

## What this package is

An extensible eJay `.MIX` player. Format plugins parse a container, resolve
its samples, and position playback events; one shared mixer renders the
result. The four stages are:

```
parse mix  ->  collect samples  ->  prepare events  ->  play events
(format)       (format)             (format)           (common)
```

The Rave and Techno plugins are refactors of the standalone players in
`../work/src` (`sdmixplay.py`, `sdmixplayer2.py`, `mixsamples.py`).
Dance, Dance 2 and Hiphop are separate reverse-engineered plugins. The package
does not import `../work/src`.

## Read first

* [`README.md`](README.md) — package map and library use.
* [`docs/architecture.md`](docs/architecture.md) — pipeline, data model,
  error model, playback rules.
* [`docs/formats.md`](docs/formats.md) — Rave, Dance, Dance 2, Hiphop, and
  Techno container details.
* [`docs/adding-a-format.md`](docs/adding-a-format.md) — extension skeleton
  and checklist.
* [`../mix_player.md`](../mix_player.md) — command-line manual.
* The reverse-engineering notes, the source of truth for container
  behaviour: [Rave](../docs/formats/MIX_FORMAT_RAVE.md),
  [Dance](../docs/formats/MIX_FORMAT_DANCE.md),
  [Dance 2](../docs/formats/MIX_FORMAT_DANCE2.md),
  [Hiphop](../docs/formats/MIX_FORMAT_HIPHOP.md) and
  [Techno](../docs/formats/MIX_FORMAT_TECHNO.md).

## Non-negotiables

1. **The common core stays format-agnostic.** `mixer.py`, `mix_player.py`,
   `cli.py`, `pxd/sample_decoder.py`, and `mix_registry.py` must not contain
   `if format == ...` branches or format names. Format rules belong in that
   format's event builder.
2. **One class per file.** A module may hold functions or constants instead,
   but do not add a second class to an existing class module.
3. **Standard library only.** `sounddevice` is the single optional dependency
   and must stay lazily imported, so importing the package and running
   `--list` never require it.
4. **No imports from `../work/src/`.** The codecs and parsers are standalone
   ports.
5. **The pipeline contract is fixed.** A format implements `matches`, `parse`,
   `collect_samples`, and `prepare_events`. Do not bypass a stage from
   `MixPlayer`.
6. **Public API is stable.** `MixFormat`, `MixRegistry`, `MixPlayer`,
   `MixDocument`, `Placement`, `SampleRef`, `SampleCollection`, `SampleBank`,
   `PlaybackEvent`, `PlaybackPlan`, `PlaybackSession`, `Mixer`,
   `AudioOutput`, `SampleDecoder`, `PxdDecoder`, and `RiffDecoder` are used by
   tests and library callers.
7. **No `__all__`.** Import public names explicitly instead of declaring
   `__all__` in a module.

## Pipeline contract

| stage | owner | input | output | format-specific |
|---|---|---|---|---|
| detect | `MixRegistry` | first 32 bytes | `MixFormat` | no |
| parse | `MixFormat.parse` | path, options | `MixDocument` | yes |
| collect | `MixFormat.collect_samples` | document, options | `SampleCollection` | yes |
| decode | `SampleDecoder` | collection | `SampleBank` (lazy streams) | no |
| prepare | `MixFormat.prepare_events` | document, bank, options | `PlaybackPlan` | yes |
| render | `Mixer` | plan, block range | int16 PCM | no |
| output | `AudioOutput` | PCM block | device | no |

`MixPlayer.load` runs detect through prepare. `MixPlayer.play` renders;
`MixPlayer.show` lists. The decode stage only reads sample headers: each
`SampleBank` entry is a `SampleStream`, and the mixer pulls block-sized
decoded windows from it while playback advances.

## Invariants

* `Placement` is the neutral, pre-timing view: 1-based track, 1-based bar,
  sample id, optional span/layer/parameters.
* `MixDocument.payload` holds the raw format structure. The format's event
  builder casts it back; the common code must not inspect it.
* `SampleRef` points at either a standalone `path` or an `archive` slice
  (`offset` + `size`). The common decoder handles both.
* `PlaybackEvent.end` is one past the last audible frame, not always
  `start + len(pcm)`. Rave cuts and loops; Techno one-shots do not.
* `PlaybackPlan.channels` is exactly 1 or 2.
* `PlaybackPlan.total_frames` includes ring-out and the full run length, not
  just the last event's PCM end.
* Per-sample resolution and decode failures are collected as strings. The
  index or archive being unusable raises `SampleError`.
* `--strict` raises only after the whole collection/header stage, so the
  message lists every skipped sample. A stream that fails while decoding is
  reported during playback and treated as silence.
* `MixRegistry` order is detection order. Put the most specific `matches`
  first. `matches` reads at most the 32 bytes the registry provides.
* CLI option names must be unique across formats. The common `--pxd`,
  `--index` and `--bpm` stay at the top level; format options live under
  `options["formats"][name]`.
* The mixer never loops, cuts, or pans by itself. Those decisions are already
  encoded in the event.

## Adding a format

Follow [`docs/adding-a-format.md`](docs/adding-a-format.md). In short:

1. Create `formats/<name>/` with one file per class.
2. Subclass `MixFormat`; set a unique `name`.
3. Implement `matches`, `parse`, `collect_samples`, `prepare_events`.
4. Raise `FormatError` for a bad container, `SampleError` for an unusable
   index/archive, and collect per-sample problems in `collection.errors`.
5. Reuse `SampleRef` and `SampleDecoder`; do not write a codec in a format.
6. Read `options["pxd"]` and `options["index"]` for the sample source;
   add only format-specific CLI flags, and return them from `options`.
7. Register the format in `MixRegistry.default()` if it ships with the
   package, or document explicit registration for third parties.
8. Add tests covering detection, parsing, collection, timing, channels,
   listing, and strict mode.

## Adding a codec

1. Add a decoder class in its own module.
2. Teach `SampleDecoder.decode_bytes` the magic.
3. Return mono int16 at `SAMPLE_RATE`.
4. Raise `SampleError` for unknown or truncated streams.
5. Add a synthetic stream test plus a real fixture test when one exists.
6. Formats do not change.

## Testing

Run from the repository root:

```powershell
python -m player.test_mix_player
```

* Tests are plain functions named `test_*` that take a `tmp` directory.
  `main()` discovers them; do not add a test framework dependency.
* Build synthetic containers and sample banks; keep bar/record lengths tiny so
  the suite stays fast.
* Use a `Recorder` object with `write(samples)` and `close()` instead of a
  device.
* The real `tPxd` fixture test skips when `data/hyper-test.pxd` is absent.
  Say so; do not imply it ran.
* Never weaken an assertion, skip a test, or add a suppression to get green.
  Fix the cause.
* If a golden value changes, explain why the new value is more correct.

## Style

* 4 spaces, no tabs, 79 columns, no trailing whitespace.
* `snake_case` functions and modules, `PascalCase` classes, `UPPER_CASE`
  constants.
* Type-hint public functions, methods, and return values.
* Google-style docstrings with `Args`, `Returns`, and `Raises` where useful.
* `pathlib` for paths, f-strings for formatting, EAFP for file access.
* No emojis in code or string representations.
* Never declare `__all__`; import the names you need explicitly.
* Do not add comments that restate the code or leak prompt text.
* Keep imports grouped: standard library, then package-relative, then
  type-checking-only imports.

## Documentation

A behaviour change is incomplete without its docs:

* container or timing change → `docs/formats.md` and the matching
  `../docs/formats/MIX_FORMAT_*.md` notes;
* pipeline, data model, or error change → `docs/architecture.md`;
* extension contract change → `docs/adding-a-format.md`;
* CLI or option change → `../mix_player.md` and `README.md`;
* high-level story change → `../README.md`.

Keep the reverse-engineering notes' confidence tags and addresses intact.
`player` implements what those notes describe; it does not invent new
container facts.

## Commands

Run these from the repository root:

```powershell
# tests
python -m player.test_mix_player

# help
python -m player --help

# Rave: list and play
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" --list
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE"

# Dance: list and play (either catalog; --pxd is optional in the shipped layout)
python -m player "disks\Dance_eJay\MIX\DREAM.MIX" --pxd "disks\Dance_eJay\DANCE" --list
python -m player "disks\Dance_eJay_old\MIX\FREAK.MIX" --list

# Dance 2: list and play (--pxd is optional in the shipped layout)
python -m player "disks\Dance_2\MIX\CAMRON.MIX" --list
python -m player "disks\Dance_2\MIX\CAMRON.MIX" --pxd "disks\Dance_2\D_ejay2\PXD"

# Techno: list and play
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD" --list
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD"
```

Bash uses the same commands with forward slashes.

## Common pitfalls

* `python player/cli.py` works too: it repairs `sys.path` before importing the
  package. Prefer `python -m player` from the repository root.
* `python -m .\player` fails with **Relative module names not supported**.
  `-m` takes a module name: use `python -m player` from the repository root.
* `--pxd` and `--index` are common flags added once by the CLI. Do not add
  them in a format's `add_arguments`; argparse rejects the duplicate.
* Rave `--pxd` is the folder containing `EJAY/PXD` and the sample
  subfolders, not the mix folder.
* Techno `--pxd` is the `EJAY/PXD` folder, whose `RAVE20` archive is the
  sample source; the `RAVE20.INF` index usually sits beside it.
* Rave records are two bars; Dance and Techno bars are four beats. Do not
  share a frames-per-unit constant between them. Dance defaults to 140 BPM
  (75,600 frames per bar); Hiphop defaults to 96 BPM (110,250 frames per
  bar) even though its grid has Dance's shape.
* Dance `MAX.TXT` is not parallel to `PXD.TXT`. Resolve the id through the
  catalog record, then use the key's low word to select the path. The newer
  `PXDDANCE` records carry their path directly.
* Dance `--pxd` is the folder containing `DMACHINE` or `EJAY` and the
  `AA`..`BW` sample folders, not the catalog folder itself. Without the
  option the player searches next to the mix for `DANCE`.
* With only `--index`, the sample root is inferred: the grandparent for
  Rave, Dance and Hiphop catalogs, the parent for Techno's `RAVE20.INF`.
* Dance high IDs 3400-3822, 3900-4419 and 4500-5049 map onto `EJAY/MAX`
  rows, but the `dmkit` sample files are absent from the discs. The mixes
  still load and skip those samples with a warning.
* Rave listing records are zero-based; `Placement.bar` is one-based.
* The Rave grid's unused tail is not reliably zero. Only ids the index can
  resolve count as content (`MIN_SAMPLE_ID`).
* Techno entries are 7 bytes when the time field is negative and 17 bytes
  otherwise. The short form stores the time negated.
* A Techno long entry's 10 extra bytes are preserved, not interpreted.
* Dance 2 uses the same 7/17-byte entry split and 128-unit bar grid as
  Techno, but its magic is `0x0A19`, it has a text track at block 17, and its
  samples are slices of `DANCE20`/`DANCESK4`-`DANCESK6`, not `RAVE20`.
* Dance 2's `--pxd` is the `D_ejay2/PXD` folder holding the four `.INF` files
  and archives. The collector also finds it from `MIX/` without `--pxd`.
* `--block` values below 64 are clamped by the player, not rejected.
* `-q` suppresses playback status and warnings but never the `--list` table.
* Rave output is mono; Techno output is interleaved stereo.

## File map

| file | contents |
|---|---|
| `constants.py` | shared rate and block constants |
| `binary.py` | C-semantics and PCM helpers |
| `pxd/delta_table.py` | `tPxd` delta ladder |
| `pxd/pxd_decoder.py` | `PxdDecoder` |
| `pxd/riff_decoder.py` | `RiffDecoder` |
| `pxd/sample_decoder.py` | `SampleDecoder` |
| `pxd/sample_ref.py`, `pxd/sample_collection.py`, `pxd/sample_bank.py` | sample model |
| `pxd/sample_stream.py` | `SampleStream` (windowed PCM) |
| `pxd/stream_source.py` | `StreamSource` (sequential reference reader) |
| `pxd/pxd_stream_decoder.py` | `PxdStreamDecoder` (incremental `tPxd`) |
| `pxd/riff_stream_decoder.py` | `RiffStreamDecoder` (incremental WAVE) |
| `pxd/sample_error.py` | `SampleError` |
| `mix_error.py`, `format_error.py`, `playback_error.py` | remaining error hierarchy |
| `placement.py`, `mix_document.py` | neutral parse model |
| `playback_event.py`, `playback_plan.py`, `playback_session.py` | render model |
| `mix_format.py`, `mix_registry.py` | extension contract and detection |
| `mixer.py`, `audio_output.py`, `playback_keys.py`, `mix_player.py` | common render path |
| `event_printer.py` | `EventPrinter` (queued console output) |
| `formatting.py`, `sugar.py` | text output helpers |
| `cli.py`, `__main__.py`, `__init__.py` | command line and public API |
| `formats/rave/` | Rave plugin |
| `formats/dance/` | Dance plugin |
| `formats/dance2/` | Dance eJay 2.0 plugin |
| `formats/hiphop/` | Hiphop plugin |
| `formats/techno/` | Techno plugin |
| `test_mix_player.py` | verification suite |

## Definition of done

- [ ] The change is in the correct stage; no format rule leaked into the
      common core.
- [ ] One class per file still holds.
- [ ] Public functions and methods are type-hinted and documented.
- [ ] `python -m player.test_mix_player` passes with real numbers.
- [ ] `--list` works on a real Rave, Dance, Dance 2, Hiphop, and Techno
      mix.
- [ ] No generated files (`__pycache__`, `.wav`, `.pcm`) are left behind.
- [ ] `docs/formats.md`, `docs/architecture.md`, `docs/adding-a-format.md`,
      `../mix_player.md`, and `../README.md` are updated where the change
      affects them.
- [ ] Any new container fact is added to the reverse-engineering notes with a
      confidence tag before it is treated as settled.
