# player

An extensible eJay `.MIX` player. It keeps the format-dependent work in
plugins and shares one mixer and one audio output for every format.

```
parse mix  ->  collect samples  ->  prepare events  ->  play events
(format)       (format)             (format)           (common)
```

The Rave and Techno plugins are refactors of the two standalone players in
`../work/src`; Dance, Dance 2 and Hiphop are separate reverse-engineered
plugins:

| old module | role in `player` |
|---|---|
| `work/src/sdmixplay.py` | `formats/rave` plus the shared `PxdDecoder`, `RiffDecoder`, and `Mixer` |
| `work/src/sdmixplayer2.py` | `formats/techno` |
| `work/src/mixsamples.py` | the Techno event-table and `RAVE20.INF` readers |

Nothing in `player` imports the `work/src` port, its sinks, or the old players.

## Quick start

Run from the repository root:

```sh
# Rave eJay: grid + EJAY/PXD + per-sample .pxd files
python -m player "disks/Rave_eJay/MIX/TRANCE.MIX" \
    --pxd "disks/Rave_eJay/RAVE"

# list without opening an audio device
python -m player "disks/Rave_eJay/MIX/TRANCE.MIX" \
    --pxd "disks/Rave_eJay/RAVE" --list

# Dance eJay: 351-block grid + DMACHINE/PXD.TXT or EJAY/PXDDANCE catalog
python -m player "disks/Dance_eJay/MIX/DREAM.MIX" \
    --pxd "disks/Dance_eJay/DANCE" --list
python -m player "disks/Dance_eJay_old/MIX/FREAK.MIX" --list

# Dance eJay 2.0: 17-track event table + DANCE20/DANCESK4-DANCESK6 archives
python -m player "disks/Dance_2/MIX/CAMRON.MIX" --list

# Techno eJay: trailer event table + RAVE20.INF + RAVE20 archive
python -m player "disks/Techno_eJay/MIX/WAMBAM.MIX" \
    --pxd "disks/Techno_eJay/EJAY/PXD"

# force a format when the header is ambiguous
python -m player song.mix --format rave --pxd disks/Rave_eJay/RAVE
```

Common options: `--pxd DIR`, `--index FILE`, `-b/--bpm`, `-l/--list`,
`--strict`, `-d/--device`, `--block FRAMES`, `-g/--gain`, `-q/--quiet`,
`-v/--verbose`, `--format`.

`--pxd` points at the folder holding the sample data — the sample
subfolders for Rave, Dance and Hiphop, the `D_ejay2/PXD` folder for Dance 2,
the `RAVE20` archive for Techno — and `--index` at the sample index file
inside it. Without them the player searches near the mix.

Format options are contributed by the format itself. Rave adds `--beats` and
`--step`; Dance, Dance 2, Hiphop and Techno add none.

Playback needs the optional `sounddevice` package. It is imported lazily, so
`--list` and all tests work without it.

During playback, `Space` pauses or resumes and `Esc` stops. Samples are
decoded in block-sized windows while the mix plays, so loading only reads
each sample header and `--list` never decodes audio. The player logs how long sample loading and
audio initialization took; `-q` hides both lines. The banner and version
header appear only on an interactive terminal, never with `-q` or `--list`.

## Supported formats

| name | magic | arrangement | sample source | output |
|---|---|---|---|---|
| `rave` | `0x0A07` | 351 x 16-word grid records | `EJAY/PXD` index + standalone `.pxd`/WAVE files | mono |
| `dance` | `0x0A06` | 351 blocks x two bars x eight tracks | `DMACHINE/PXD.TXT` or `EJAY/PXDDANCE` catalog + `.pxd`/WAVE files | mono |
| `dance2` | `0x0A19` | per-track event table + text track | `DANCE20.INF` and `DANCESK4`-`DANCESK6` indexes + archive slices | stereo |
| `hiphop` | `0x0A08` | 351 blocks x two bars x eight tracks | `HIPHOP/EJAY/PXD` catalog + `.pxd`/WAVE files | mono |
| `techno` | `0x0889` | per-track event table in the trailer | `RAVE20.INF` + slices of the `RAVE20` archive | stereo |

Details: [docs/formats.md](docs/formats.md).

## Package layout

Every class lives in its own file. Modules that hold only functions or
constants are marked as such.

| file | contents |
|---|---|
| `constants.py` | shared rate and block-size constants (functions/constants) |
| `binary.py` | C-semantics and PCM helpers (functions) |
| `pxd/delta_table.py` | the `tPxd` delta ladder (functions/constant) |
| `pxd/pxd_decoder.py` | `PxdDecoder` |
| `pxd/riff_decoder.py` | `RiffDecoder` |
| `pxd/sample_decoder.py` | `SampleDecoder` |
| `pxd/sample_stream.py` | `SampleStream` |
| `pxd/stream_source.py` | `StreamSource` |
| `pxd/pxd_stream_decoder.py` | `PxdStreamDecoder` |
| `pxd/riff_stream_decoder.py` | `RiffStreamDecoder` |
| `pxd/sample_ref.py` | `SampleRef` |
| `pxd/sample_collection.py` | `SampleCollection` |
| `pxd/sample_bank.py` | `SampleBank` |
| `pxd/sample_error.py` | `SampleError` |
| `mix_error.py` | `MixError` |
| `format_error.py` | `FormatError` |
| `playback_error.py` | `PlaybackError` |
| `placement.py` | `Placement` |
| `mix_document.py` | `MixDocument` |
| `playback_event.py` | `PlaybackEvent` |
| `playback_plan.py` | `PlaybackPlan` |
| `playback_session.py` | `PlaybackSession` |
| `mix_format.py` | `MixFormat` (abstract contract) |
| `mix_registry.py` | `MixRegistry` |
| `mixer.py` | `Mixer` |
| `audio_output.py` | `AudioOutput` |
| `playback_keys.py` | non-blocking console key polling (functions) |
| `formatting.py` | shared text formatting helpers (functions) |
| `sugar.py` | startup banner selection (functions) |
| `mix_player.py` | `MixPlayer` |
| `event_printer.py` | `EventPrinter` |
| `cli.py` | `build_parser`, `options_from_namespace`, `main` (functions) |
| `formats/rave/rave_grid.py` | `RaveGrid` |
| `formats/rave/rave_sample_entry.py` | `RaveSampleEntry` |
| `formats/rave/rave_sample_index.py` | `RaveSampleIndex` (plus path helpers) |
| `formats/rave/rave_sample_collector.py` | `RaveSampleCollector` |
| `formats/rave/rave_event_builder.py` | `RaveEventBuilder` |
| `formats/rave/rave_mix_format.py` | `RaveMixFormat` |
| `formats/dance/dance_grid.py` | `DanceGrid` |
| `formats/dance/dance_sample_entry.py` | `DanceSampleEntry` |
| `formats/dance/dance_sample_index.py` | `DanceSampleIndex` (plus path helpers) |
| `formats/dance/dance_sample_collector.py` | `DanceSampleCollector` |
| `formats/dance/dance_event_builder.py` | `DanceEventBuilder` |
| `formats/dance/dance_mix_format.py` | `DanceMixFormat` |
| `formats/dance2/dance2_kit.py` | `Dance2Kit` |
| `formats/dance2/dance2_palette_entry.py` | `Dance2PaletteEntry` |
| `formats/dance2/dance2_track_settings.py` | `Dance2TrackSettings` |
| `formats/dance2/dance2_sample_event.py` | `Dance2SampleEvent` |
| `formats/dance2/dance2_text_event.py` | `Dance2TextEvent` |
| `formats/dance2/dance2_mix_data.py` | `Dance2MixData` |
| `formats/dance2/dance2_reader.py` | `Dance2Reader` |
| `formats/dance2/dance2_sample_index.py` | `Dance2SampleIndex` |
| `formats/dance2/dance2_sample_collector.py` | `Dance2SampleCollector` |
| `formats/dance2/dance2_event_builder.py` | `Dance2EventBuilder` |
| `formats/dance2/dance2_mix_format.py` | `Dance2MixFormat` |
| `formats/hiphop/hiphop_grid.py` | `HiphopGrid` |
| `formats/hiphop/hiphop_sample_entry.py` | `HiphopSampleEntry` |
| `formats/hiphop/hiphop_sample_index.py` | `HiphopSampleIndex` |
| `formats/hiphop/hiphop_sample_collector.py` | `HiphopSampleCollector` |
| `formats/hiphop/hiphop_event_builder.py` | `HiphopEventBuilder` |
| `formats/hiphop/hiphop_mix_format.py` | `HiphopMixFormat` |
| `formats/techno/techno_mix_data.py` | `TechnoMixData` |
| `formats/techno/techno_sample_index.py` | `TechnoSampleIndex` |
| `formats/techno/techno_sample_collector.py` | `TechnoSampleCollector` |
| `formats/techno/techno_event_builder.py` | `TechnoEventBuilder` |
| `formats/techno/techno_mix_format.py` | `TechnoMixFormat` |
| `test_mix_player.py` | runnable verification suite |

## Library use

```python
from pathlib import Path
from player import MixPlayer

options = {
    "pxd": "disks/Rave_eJay/RAVE",
    "formats": {
        "rave": {"beats": 8, "step": None},
    },
    "quiet": True,
}
player = MixPlayer()
session = player.load(Path("song.mix"), options)
print(session.plan.duration_seconds, len(session.plan.events))

# output may be any object with write(samples) and close()
player.play(Path("song.mix"), options)
```

A new format is a `MixFormat` subclass registered in a `MixRegistry`. See
[docs/adding-a-format.md](docs/adding-a-format.md).

## Documentation

* [AGENTS.md](AGENTS.md) — package-scoped agent instructions: invariants,
  extension rules, tests, style, pitfalls, and definition of done.
* [../mix_player.md](../mix_player.md) — command-line manual: every option,
  ready-to-run examples, output columns, exit status, and troubleshooting.
* [docs/architecture.md](docs/architecture.md) — pipeline, data model, class
  responsibilities, error model, playback rules.
* [docs/formats.md](docs/formats.md) — what the Rave, Dance, Dance 2,
  Hiphop and Techno plugins do.
* [docs/adding-a-format.md](docs/adding-a-format.md) — step-by-step extension
  guide with a skeleton and checklist.

## Tests

```sh
python -m player.test_mix_player
```

The suite builds synthetic Rave, Dance, Dance 2, Hiphop, and Techno
containers and sample banks, then checks parsing, sample collection, timing,
looping, panning, strict mode, and listing. It also registers a third-party `DummyFormat` to prove that a new
format needs no changes to the common player. A real `tPxd` fixture is used
when `data/hyper-test.pxd` is present; otherwise that check is skipped.
