# player — command-line manual

`player` plays eJay `.MIX` arrangements without the original engine. It
detects the container from the file header, asks the matching format plugin to
parse the arrangement and locate its samples, then renders the result through
one shared mixer and audio output.

The package lives in `player/`. The pipeline and extension contract are
described in [`player/README.md`](player/README.md) and
[`player/docs/architecture.md`](player/docs/architecture.md).

```
parse mix  ->  collect samples  ->  prepare events  ->  play events
(format)       (format)             (format)           (common)
```

## Synopsis

Run from the repository root:

```text
python -m player MIX [common options] [format options]
```

`MIX` is one `.MIX` file. Use `--format` to force a plugin; otherwise the
first two header bytes select it.

### `-m` takes a module name, not a path

`python -m` expects a dotted module name. Do not prefix it with a dot or a
path separator, and do not include `.py`:

```text
correct:   python -m player ...
wrong:     python -m .\player ...          Relative module names not supported
wrong:     python -m ./player ...          Relative module names not supported
wrong:     python -m player.py ...     module name error
wrong:     python player\cli.py           use python -m player
```

Run the command from the repository root (the folder containing `player/`):

```powershell
python -m player --help
```

If `python` resolves to a specific interpreter, install `sounddevice` into
that same interpreter, for example:

```powershell
C:\Python314\python.exe -m pip install sounddevice
```

## Requirements

* Python 3.13 or newer (see `pyproject.toml`).
* The standard library only, for parsing and `--list`.
* `sounddevice` for playback. It is imported lazily, so listing and the test
  suite work without it.

```powershell
python -m pip install sounddevice
```

To see the devices PortAudio offers:

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

## Supported formats

| name | magic | arrangement | sample source | output |
|---|---|---|---|---|
| `rave` | `0x0A07` | 351 x 16-word grid records | `EJAY/PXD` index + standalone `.pxd`/WAVE files | mono |
| `dance` | `0x0A06` | 351 blocks x two bars x eight tracks | `DMACHINE/PXD.TXT` or `EJAY/PXDDANCE` catalog + `.pxd`/WAVE files | mono |
| `dance2` | `0x0A19` | per-track event table + a text track | `DANCE20.INF` and `DANCESK4`-`DANCESK6` indexes + archive slices | stereo |
| `hiphop` | `0x0A08` | 351 blocks x two bars x eight tracks | `HIPHOP/EJAY/PXD` catalog + `.pxd`/WAVE files | mono |
| `techno` | `0x0889` | per-track event table in the trailer | `RAVE20.INF` + slices of the `RAVE20` archive | stereo |

Format details are in [`player/docs/formats.md`](player/docs/formats.md).

## Quick start

All commands below assume the current directory is the repository root.

### List without opening an audio device

**Rave eJay**

```powershell
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" --list
```

**Dance eJay**

```powershell
python -m player "disks\Dance_eJay\MIX\DREAM.MIX" --pxd "disks\Dance_eJay\DANCE" --list
python -m player "disks\Dance_eJay_old\MIX\FREAK.MIX" --list
```

**Dance eJay 2.0**

```powershell
python -m player "disks\Dance_2\MIX\CAMRON.MIX" --list
```

**Hiphop eJay**

```powershell
python -m player "disks\Hiphop_eJay\MIX\START.MIX" --pxd "disks\Hiphop_eJay\HIPHOP" --list
```

**Techno eJay**

```powershell
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD" --list
```

### Play

**Rave eJay**

```powershell
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE"
```

**Dance eJay**

```powershell
python -m player "disks\Dance_eJay\MIX\FREAK.MIX" --pxd "disks\Dance_eJay\DANCE"
```

**Dance eJay 2.0**

```powershell
python -m player "disks\Dance_2\MIX\CAMRON.MIX"
```

**Hiphop eJay**

```powershell
python -m player "disks\Hiphop_eJay\MIX\START.MIX" --pxd "disks\Hiphop_eJay\HIPHOP"
```

**Techno eJay**

```powershell
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD"
```

Bash users can use the same commands with forward slashes, for example
`disks/Rave_eJay/MIX/TRANCE.MIX`.

## Options

### Common options

| option | meaning | default |
|---|---|---|
| `MIX` | `.MIX` file to load | required |
| `--format {rave,dance,dance2,hiphop,techno}` | force a plugin instead of detecting it | detect |
| `--pxd DIR` | folder holding the sample data: the sample subfolders, or the sample archive | search near the mix |
| `--index FILE` | explicit sample index file | the index under `--pxd`, or near the mix |
| `-b`, `--bpm BPM` | tempo override | format default |
| `-l`, `--list` | print the arrangement and exit; no device is opened | off |
| `--strict` | fail instead of skipping unusable samples | off |
| `-d`, `--device DEV` | output device index or name substring | system default |
| `--block N` | mix and write block size in frames; values below 64 are clamped | 2048 |
| `-g`, `--gain F` | linear mix gain; above 1.0 can clip | 1.0 |
| `-q`, `--quiet` | suppress playback status lines, skip warnings, and per-sample output | off |
| `-v`, `--verbose` | print each sample when it starts playing | off |

`-q` never hides the `--list` table or its summary. During playback it
suppresses the summary and `done` lines; in both modes it hides per-sample
skip warnings. `-v` is ignored when `-q` is set.

### Format options

`--pxd` and `--index` cover the sample source for every format. Only Rave
adds options of its own; Dance, Dance 2, Hiphop and Techno add none.

| option | meaning | default |
|---|---|---|
| `--beats N` | beats per Rave grid record | 8 (two 4/4 bars) |
| `--step SECONDS` | length of one Rave record; overrides `--bpm` and `--beats` | derived |

## Finding the sample data

The mix file and its samples are separate. The shipped disks keep them in
different folders, so `--pxd` (or `--index`) is normally required. `--pxd`
names the folder holding the sample data and `--index` the index file inside
it. With only `--index`, the sample root is inferred: the grandparent for the
Rave, Dance and Hiphop catalogs, the parent for Techno's `RAVE20.INF`, and
the index's own folder for Dance eJay 2.0 (the other known indexes there are
still merged).

### Rave eJay

`--pxd` must point at the folder that contains `EJAY/PXD` and the sample
subfolders (`AA`..`BS`, `HYPER`):

```text
disks/Rave_eJay/RAVE/
├── EJAY/PXD          sample list
├── AA/ ... BS/       sample folders
└── HYPER/
```

The sample index maps `sample_id - 731` to a relative path under that folder.
Paths are resolved case-insensitively.

Without `--pxd` or `--index`, the player searches for `EJAY/PXD` in the mix
folder, `<mix folder>/disk/RAVE`, the mix parent and grandparent, the current
directory, and `<cwd>/disk/RAVE`. The shipped layout does not match those
locations from the repository root, hence the explicit `--pxd`.

### Dance eJay

Both disc layouts are read. The older one:

```text
disks/Dance_eJay_old/
├── MIX/FREAK.MIX
└── DANCE/
    ├── DMACHINE/
    │   ├── PXD.TXT    sample catalog
    │   └── MAX.TXT    sample paths
    └── AA/ ... BW/    sample folders
```

The newer one:

```text
disks/Dance_eJay/
├── MIX/FREAK.MIX
└── DANCE/
    ├── EJAY/
    │   ├── PXDDANCE   sample catalog (path, category, bars, name)
    │   └── MAX        2,845 paths (1,352 base + three add-on banks)
    └── AA/ ... BW/    sample folders
```

The old `PXD.TXT` and `MAX.TXT` are separate lists. The sample id selects a
catalog record, and the record's low key word selects the `MAX.TXT` line; the
lists are not parallel. The new `PXDDANCE` records carry the path directly,
and high IDs 3400+ select rows of `EJAY/MAX` through the bank formula in
[`docs/formats/MIX_FORMAT_DANCE.md`](docs/formats/MIX_FORMAT_DANCE.md)
section 4.3. Paths are resolved case-insensitively under the Dance folder.

Without `--pxd`, the player searches next to the mix for a `DANCE`
folder containing either catalog, so the shipped disc layouts work directly.
`--pxd` accepts the `DANCE` folder for either disc, or the catalog folder
(`DMACHINE`/`EJAY`) itself.

The `dmkit1`..`dmkit3` sample files referenced by the high-ID banks are not
on either disc or in the ISOs. The eight new mixes that use them still load:
their high-ID samples are reported as skipped and the base samples play.

### Dance eJay 2.0

```text
disks/Dance_2/
├── MIX/*.MIX
└── D_ejay2/PXD/
    ├── DANCE20.INF    base index       DANCE20   archive
    ├── DANCESK4.INF   add-on index     DANCESK4  archive
    ├── DANCESK5.INF   add-on index     DANCESK5  archive
    └── DANCESK6.INF   add-on index     DANCESK6  archive
```

Each `.INF` has 12-line records after `[SAMPLES]`; fields 3 and 4 are the
byte offset and length of a slice inside the sibling archive (the `.INF`
name without its extension). The four id ranges do not overlap, so the
sample id alone resolves the kit. Without `--pxd`, the player searches the
mix folder, its parent and `PXD` children, `EJAY/PXD` and `D_ejay2/PXD`,
the current directory, and one level of subdirectories. On the shipped disc
the `D_ejay2/PXD` folder is found from `MIX/` automatically. `--index` names
one index and makes its folder the sample root; the other known indexes
there are still merged.

### Hiphop eJay

```text
disks/Hiphop_eJay/
├── MIX/
│   └── *.MIX
└── HIPHOP/
    ├── EJAY/
    │   ├── PXD      sample catalog (1,341 records)
    │   ├── MAX      1,381 paths (unused by MIX grid)
    │   └── MIN      743 paths (unused by MIX grid)
    ├── AA/ ... BR/  sample folders (.pxd files)
    └── SCRATCH/     40 scratch WAV files
```

The `PXD` catalog has 1,341 six-line records with the path stored directly in
field 0; no `MAX`/`MIN` indirection is needed. The ID rule is `sample_id - 731`,
giving base IDs 731-2071. All catalog paths resolve to existing `.pxd` files
under `HIPHOP/`. Paths are resolved case-insensitively under `--pxd`.

Without `--pxd`, the player searches next to the mix for a `HIPHOP`
folder containing `EJAY/PXD`, so the shipped disc layout works directly.

### Techno eJay

```text
disks/Techno_eJay/
├── MIX/WAMBAM.MIX
└── EJAY/PXD/
    ├── RAVE20.INF    sample index
    └── RAVE20        sample archive
```

The index is read first; the archive is sliced at the offset and length each
record stores. `--pxd` names the `EJAY/PXD` folder holding the archive, and
`--index` the `RAVE20.INF` file beside it; pass them when the files are not
next to the mix.

## Output

### Startup banner

The logo, version and format list are printed only when stdout is an
interactive terminal and neither `-q` nor `--list` is set, so redirected
output contains only results. On a terminal the colour logo is used when the
console understands ANSI codes (`NO_COLOR` turns them off), the same glyphs
without colour when it cannot, and an ASCII box when the code page cannot
encode the glyphs.

### Summary line

Every run prints one summary line:

```text
<title>  <format>  <N> events  <minutes:seconds.hundredths>
```

Playback adds `via sounddevice` when the player opened the device itself.
`--list` never adds it.

### Rave listing

```text
  351 records, 79 used, 2.6667 s per record
    #   time     Tk Ln  ID   filename
    0   0:00.00  T1 A  0637  light layer 1
    6   0:16.00  T3 A  0338  just walking         x30
```

| column | meaning |
|---|---|
| `#` | zero-based grid record |
| `time` | start time in the rendered timeline |
| `Tk` | track number, 1-8 |
| `Ln` | lane, `A` or `B` |
| `ID` | sample id in hexadecimal |
| `filename` | sample display name |
| `xN` | run length in grid records, shown when longer than one |

### Dance listing

```text
  351 blocks, 36 used, 140 bpm, 75600 frames/bar
  blk bar   time      Tk  ID    sample
   35  71   2:00.00  T4  04E7  Wood- Bowls
```

| column | meaning |
|---|---|
| `blk` | zero-based grid block |
| `bar` | one-based absolute bar, 1-702 |
| `time` | start time in the rendered timeline |
| `Tk` | track number, 1-8 |
| `ID` | sample id in hexadecimal |
| `sample` | display name from `PXD.TXT` |
| `xN` | run length in bars, shown when longer than one |

### Dance eJay 2.0 listing

```text
  140 bpm  6 placements  16 text events
     time       Tk    bar     id  sample
   0:03.43  T1    3.000  02C2  whip basic 1
```

| column | meaning |
|---|---|
| `time` | start time in the rendered timeline |
| `Tk` | track number, 1-16 |
| `bar` | bar position from the 128-unit grid |
| `id` | sample id in hexadecimal |
| `sample` | category and part label from the `.INF` record |

The summary line also reports how many text-track records the mix contains;
those records are not rendered.

### Techno listing

```text
  140 bpm  171 placements
     time       Tk    bar     id  sample
   0:00.00  T1    1.000  39CD  zap / up 4
```

| column | meaning |
|---|---|
| `time` | start time in the rendered timeline |
| `Tk` | track number, 1-17 |
| `bar` | fixed-point bar position from the file |
| `id` | sample id in hexadecimal |
| `sample` | `category / part` label from `RAVE20.INF` |

## Timing

| format | tempo source | default | unit |
|---|---|---|---|
| `rave` | `--bpm` and `--beats`, or `--step` | 180 BPM, 8 beats | one record = two bars |
| `dance` | `--bpm` | 140 BPM | one bar = four beats |
| `dance2` | header word 4, overridden by `--bpm` | 140 BPM | one bar = four beats |
| `hiphop` | `--bpm` | 96 BPM | one bar = four beats |
| `techno` | header word 4, overridden by `--bpm` | 140 BPM | one bar = four beats |

At 44.1 kHz, the Rave default record is 117 600 frames (2.667 s), a Dance or
Techno bar at 140 BPM is 75 600 frames (1.714 s), and a Hiphop bar at 96 BPM
is 110 250 frames (2.5 s).

## Playback behaviour

### Common

* Blocks are rendered in increasing, contiguous ranges.
* Mono plans sum all events, then clip each frame to -32768..32767 once.
* Stereo plans sum interleaved left/right values with per-event channel
  gains, then clip each channel once.
* Clipping happens after summation, so the result does not depend on event
  order.
* `--gain` multiplies each event before summing and clipping.
* `Space` pauses or resumes playback. Paused output resumes at the same
  position.
* `Esc` stops playback and exits with status 0.
* `Ctrl+C` stops playback and exits with status 130.

Samples are decoded in block-sized windows while the mix plays, not when the
mix is loaded. Loading only reads each sample header, so `--list` never
decodes audio.
Playback also prints how long loading the samples and initializing the audio
device took. `-q` suppresses both timing lines.

### Rave

* A record is two bars. The default is 180 BPM and 8 beats per record, i.e.
  8/3 s = 117 600 frames at 44.1 kHz. `--step` sets the record length
  directly; `--bpm` and `--beats` derive it.
* A run is the same id repeated in consecutive records on one lane/track.
  Repetition is one sounding, not one hit per record.
* A run longer than its sample repeats the sample to fill the run when the
  sample is at least one record long.
* A run shorter than its sample still plays the whole sample, except that an
  earlier sample is cut when the arrangement's final record begins.
* A placement in the final record rings out past the grid.
* A sample shorter than one record is a one-shot: it plays once and leaves the
  rest of its run silent.
* Output is mono.

### Dance

* A bar is four beats. At the default 140 BPM that is 75 600 frames at
  44.1 kHz; a block is two bars. `--bpm` overrides the tempo.
* A run is the same id repeated in consecutive bars on one track. Repetition
  is one sounding, not one hit per bar.
* A run longer than its sample repeats the sample to fill the run when the
  sample is at least one bar long.
* A run shorter than its sample plays the whole sample. The next sample on
  the same track cuts it when that next sample starts.
* A sample with no following sample on its track rings out past the grid.
  This is why the rendered length can exceed the last used block.
* Output is mono.

### Dance eJay 2.0

* A bar is four beats. Header word 4 gives 140 BPM, i.e. 75 600 frames at
  44.1 kHz. `--bpm` overrides the header tempo.
* Every event-table entry is a one-shot at its 128-unit bar position.
* A track plays one sample at a time. A later event on the same track cuts
  the previous sample; the last event on a track rings out.
* Tracks 1-16 use the mix's pan/volume pairs: pan 0 is centred, 1 is left
  and 2 is right; the volume scales the sample. Track 17 holds text records
  and is not rendered.
* Output is interleaved stereo.

### Techno

* A bar is four beats. At the default 140 BPM that is 75 600 frames at
  44.1 kHz. `--bpm` overrides the header tempo.
* Every event-table entry is a one-shot at its bar position.
* Tracks 4, 13, and 15 are left-only; 5, 14, and 16 are right-only; the rest
  are centred at full scale in both channels. The original engine has no 0.5
  factor on its gain path, so a centred track is not attenuated; see
  [`docs/formats/MIX_FORMAT_TECHNO.md`](docs/formats/MIX_FORMAT_TECHNO.md) §13.
* Output is interleaved stereo.

## Exit status

| code | meaning |
|---|---|
| 0 | success, including a normal `Esc` stop |
| 1 | a mix, sample, or output error |
| 2 | invalid command line (argparse) |
| 130 | interrupted with `Ctrl+C` |

## Examples

```powershell
# verbose playback: one line per sample as it starts
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" -v

# quiet playback: suppress status lines, warnings, and per-sample output
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD" -q

# choose an output device by index or name substring
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD" -d "Speakers"

# tempo override
python -m player "disks\Techno_eJay\MIX\WAMBAM.MIX" --pxd "disks\Techno_eJay\EJAY\PXD" -b 150

# Rave record length in seconds (overrides --bpm/--beats)
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" --step 2.5

# Dance with an explicit sample folder
python -m player "disks\Dance_eJay\MIX\START.MIX" --pxd "disks\Dance_eJay\DANCE" --list

# Dance eJay 2.0, either with auto-discovery or an explicit PXD folder
python -m player "disks\Dance_2\MIX\CAMRON.MIX" --list
python -m player "disks\Dance_2\MIX\CAMRON.MIX" --pxd "disks\Dance_2\D_ejay2\PXD" --list

# lower gain and a smaller block
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" -g 0.7 --block 1024

# force a plugin explicitly
python -m player "song.mix" --format rave --pxd "disks\Rave_eJay\RAVE"

# fail instead of skipping a missing sample
python -m player "disks\Rave_eJay\MIX\TRANCE.MIX" --pxd "disks\Rave_eJay\RAVE" --strict --list
```

### List the first mix in each folder

```powershell
python -m player (Get-ChildItem "disks\Rave_eJay\MIX\*.MIX" | Select-Object -First 1).FullName --pxd "disks\Rave_eJay\RAVE" --list

python -m player (Get-ChildItem "disks\Techno_eJay\MIX\*.MIX" | Select-Object -First 1).FullName --pxd "disks\Techno_eJay\EJAY\PXD" --list
```

### Batch list every mix

```powershell
Get-ChildItem "disks\Rave_eJay\MIX\*.MIX" | ForEach-Object {
    python -m player $_.FullName --pxd "disks\Rave_eJay\RAVE" --list
}
```

```bash
for mix in disks/Rave_eJay/MIX/*.MIX; do
    python -m player "$mix" --pxd disks/Rave_eJay/RAVE --list
done
```

## Troubleshooting

| message | cause | fix |
|---|---|---|
| `Relative module names not supported` | `-m` was given a path or a leading dot, e.g. `-m .\player` | use `python -m player` from the repository root |
| `playback needs the 'sounddevice' package ('pip install sounddevice')` | dependency missing | install `sounddevice`, or use `--list` |
| `cannot find the eJay sample index (EJAY/PXD); pass --pxd or --index` | Rave index not in a searched location | pass `--pxd` or `--index` |
| `<path>: sample index not found` | the resolved `EJAY/PXD` does not exist | check `--pxd`/`--index` |
| `<path>: sample archive not found` | the resolved `RAVE20` does not exist | check `--pxd` |
| `<name>: unknown mix format` | header matches no plugin | pass `--format` |
| `unknown mix format 'x' (known: dance, dance2, hiphop, rave, techno)` | bad `--format` value | use a listed name |
| `cannot find the Dance eJay catalog (DMACHINE/PXD.TXT or EJAY/PXDDANCE); pass --pxd or --index` | catalog not in a searched location | pass `--pxd` or `--index` |
| `DANCE20.INF not found (looked in ...)` | Dance eJay 2.0 sample folder not in a searched location | pass `--pxd` or `--index` |
| `id N: not in DANCE20.INF or the add-on kits` | the mix references an id absent from all four indexes | check that the add-on kits are present |
| `<name>: nothing to play` | no events or zero length | check the mix and tempo |
| `cannot open the output device: ...` | PortAudio could not open the device | use `-d` or fix the device |
| `--bpm must be positive` | zero or negative tempo | pass a positive `--bpm` |
| `the record length must be positive` | zero or negative `--step` | pass a positive `--step` |
| `skipped sample 0x...: not found` | Rave or Dance sample missing from the index or disk | check `--pxd`/`--index`, or use `--strict` to fail |
| `skipped id N: not in RAVE20.INF` | Techno id absent from the index | check `--index` |
| `event marker ... not found` | not a Techno arrangement, or a damaged file | verify the file or use the correct format |
| `event table: expected track N, got M` | damaged or unsupported Techno trailer | verify the file |
| `missing 0x018A7AA9 footer` | truncated or non-Techno file | verify the file |

Warnings are printed as `player: skipped ...` on stderr. `--strict` turns
the collected warnings into a `SampleError`, so the run stops before playback.

## Library use

The CLI is a thin wrapper around `MixPlayer`. Options are a plain mapping.
The sample source is common — `pxd` and `index`, like `bpm` — and
format-specific options live under `formats`.

```python
from pathlib import Path

from player import MixPlayer

options = {
    "pxd": "../disks/Rave_eJay/RAVE",
    "quiet": True,
}

player = MixPlayer()
session = player.load(Path("../disks/Rave_eJay/MIX/TRANCE.MIX"), options)
print(session.plan.duration_seconds, len(session.plan.events))
```

Rave timing overrides go in the format slice:
`{"formats": {"rave": {"beats": 8, "step": None}}, "pxd": ...}`.

`MixPlayer.play` accepts any object with `write(samples)` and `close()`, which
is how the tests run without a device:

```python
class Recorder:
    def __init__(self):
        self.samples = []

    def write(self, samples):
        self.samples.extend(samples)

    def close(self):
        pass


player.play(Path("song.mix"), options, output=Recorder())
```

Use `MixPlayer.show` for a listing, or `MixPlayer.load` plus
`MixPlayer.show_session` when you already hold a session.

## Adding a format

A new container is a `MixFormat` subclass registered in a `MixRegistry`.
The common mixer, player, and CLI do not change. The full guide, including a
skeleton and checklist, is in
[`player/docs/adding-a-format.md`](player/docs/adding-a-format.md).

## Tests

```powershell
python -m player.test_mix_player
```

The suite builds synthetic Rave, Dance, Dance 2, Hiphop, and Techno
containers and sample banks, then checks parsing, sample collection, timing,
looping, panning, strict mode, listing, and the CLI. It also registers a third-party `DummyFormat` to prove
that a new format needs no changes to the common player. A real `tPxd` fixture
is used when `data/hyper-test.pxd` is present; otherwise that check is
skipped.

## Limitations

* Techno long-entry parameter bytes are preserved but not applied. The manual's
  per-placement volume and cut controls are plausible owners.
* Techno's compact grid before the trailer is not interpreted; the arrangement
  comes from the event table.
* Rave's record length is not stored in the file. The default of two bars is a
  documented assumption; use `--step` or `--bpm`/`--beats` when it is wrong.
* Dance's tempo is not stored either; 140 BPM is the documented default. Its
  catalog header and the high word of each catalog key are not interpreted.
* Dance 2's header words 2, 5 and 7, its 22 song-settings bytes, the palette
  parameters, the long entry's extra bytes and the text-track prefix are
  preserved but not interpreted. Text events are not rendered.
* Hiphop's tempo is not stored. 96 BPM is inferred because the catalog's bar
  field times 110,250 frames equals every decoded `tPxd` length.
* Playback uses PortAudio through `sounddevice`; the original DirectSound path
  is not reproduced.
* Mix samples are decoded to mono at 44.1 kHz. Techno's stereo image comes from
  track gains, not from stereo sample data: the paired `...L`/`...R` samples
  play on separate tracks at full scale, and a centred track is at full scale
  in both channels.

## See also

* [`player/README.md`](player/README.md) — package overview and map.
* [`player/docs/architecture.md`](player/docs/architecture.md) — pipeline, data
  model, error model, playback rules.
* [`player/docs/formats.md`](player/docs/formats.md) — Rave, Dance, Dance 2,
  Hiphop, and Techno container details.
* [`player/docs/adding-a-format.md`](player/docs/adding-a-format.md) — extension
  guide.
* [`docs/formats/MIX_FORMAT_RAVE.md`](docs/formats/MIX_FORMAT_RAVE.md) — Rave
  reverse engineering notes.
* [`docs/formats/MIX_FORMAT_DANCE.md`](docs/formats/MIX_FORMAT_DANCE.md) —
  Dance reverse engineering notes.
* [`docs/formats/MIX_FORMAT_DANCE2.md`](docs/formats/MIX_FORMAT_DANCE2.md) —
  Dance eJay 2.0 reverse engineering notes.
* [`docs/formats/MIX_FORMAT_TECHNO.md`](docs/formats/MIX_FORMAT_TECHNO.md) —
  Techno reverse engineering notes.
