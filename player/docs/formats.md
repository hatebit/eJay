# Built-in formats

Five plugins ship with the player. The reverse-engineering notes remain the
source of truth:

* Rave: [`../../docs/formats/MIX_FORMAT_RAVE.md`](../../docs/formats/MIX_FORMAT_RAVE.md)
* Dance: [`../../docs/formats/MIX_FORMAT_DANCE.md`](../../docs/formats/MIX_FORMAT_DANCE.md)
* Dance 2: [`../../docs/formats/MIX_FORMAT_DANCE2.md`](../../docs/formats/MIX_FORMAT_DANCE2.md)
* Hiphop: [`../../docs/formats/MIX_FORMAT_HIPHOP.md`](../../docs/formats/MIX_FORMAT_HIPHOP.md)
* Techno: [`../../docs/formats/MIX_FORMAT_TECHNO.md`](../../docs/formats/MIX_FORMAT_TECHNO.md)
* `tPxd`: [`../../docs/formats/PXD_FORMAT.md`](../../docs/formats/PXD_FORMAT.md)
* `RAVE20.INF`: [`../../docs/formats/INF_FORMAT.md`](../../docs/formats/INF_FORMAT.md)

## Rave eJay (`rave`)

### Container

| item | value |
|---|---|
| magic | `0x0A07` at offset 0 |
| grid | starts at offset 2, 32-byte records of 16 little-endian u16 |
| trailer | first 32-byte-aligned `0x0A08` after the grid |
| version | NUL-terminated string after the trailer tag |
| tracks | 8 per lane, two lanes: words 0-7 (`A`) and 8-15 (`B`) |
| empty cell | any value below 731 |

The grid is read until the trailer, or to the end of a truncated file. Only
cells whose value the sample index can resolve count as content; the unused
tail is not reliably zero.

### Samples

`EJAY/PXD` is a CRLF text list of six quoted lines per record:

```
"bq\r1bs001.pxd"   relative sample path under the resource root
""                  unused
"bass"              category
"2"                 length in bars
"wood walk"         display name, part 1
"1"                 display name, part 2
```

The id rule is `record_index = sample_id - 731`. Paths are resolved under
`--pxd` case-insensitively. Each file is decoded as `tPxd` or RIFF/WAVE by the
shared decoder.

### Timing and events

* A record is **two bars**. The default is 180 BPM and 8 beats per record,
  i.e. 8/3 s = 117 600 frames at 44.1 kHz.
* `--step` overrides the record length; `--bpm` and `--beats` derive it.
* A run is the same id repeated in consecutive records on one lane/track.
  Repetition is one sounding, not one hit per record.
* A run longer than its sample repeats the sample to fill the run when the
  sample is at least one record long.
* A run shorter than its sample still plays the whole sample, except that an
  earlier sample is cut when the arrangement's final record begins.
* A placement in the final record is the ending and rings out past the grid.
* A sample shorter than one record is a one-shot: it plays once and leaves
  the rest of its run silent.
* Output is mono.

### CLI options

`--beats N` and `--step SECONDS`; the sample folder and index come from the
common `--pxd` and `--index`. Common `--bpm` applies to the record length.

## Dance eJay (`dance`)

### Container

| item | value |
|---|---|
| magic | `0x0A06` at offset 0 |
| grid | starts at offset 2, exactly 351 blocks of 32 bytes |
| block | two bars x eight tracks, 16 little-endian u16 |
| bar order | words 0-7 are bar 1; words 8-15 are bar 2 |
| empty cell | any value below 731 |
| grid end | offset 11,234 |
| metadata | optional 43, 99 or 179 bytes after the grid; ignore it |

The 351 blocks cover 702 bars. `FREAK.MIX` and eleven other mixes also contain
stray values below 731 outside their arrangement; those are not samples and
are ignored. Files may end at 11,234 or carry a creator/version/sample-kit
block; see
[`../../docs/formats/MIX_FORMAT_DANCE.md`](../../docs/formats/MIX_FORMAT_DANCE.md)
section 1.1. The parser accepts any length at or above 11,234 and ignores the
block.

### Samples

The shipped discs use two catalog generations. The older
`DMACHINE/PXD.TXT` has 18 quoted header values followed by 1,352 records of
four quoted lines:

```text
"917984"       32-bit catalog key
"2"            length in bars
"Grp. 1"       display name, part 1
"Vers1"       display name, part 2
```

`DMACHINE/MAX.TXT` is a separate list of 1,352 quoted relative paths. The two
lists are not parallel. The id selects a catalog record; the record's key
selects the path:

```text
record_index = sample_id - 731
path_index   = (key & 0xFFFF) - 3
path         = MAX.TXT[path_index]
```

Paths are resolved under `--pxd` case-insensitively. Each file is decoded as
`tPxd` or RIFF/WAVE by the shared decoder.

The newer `EJAY/PXDDANCE` catalog has six quoted fields per record, including
the relative path directly, and its `MAX` list holds 2,845 paths. The extra
rows are the `dmkit1`, `dmkit2` and `dmkit3` banks used by IDs 3400-3822,
3900-4419 and 4500-5049. The collector reads either catalog and resolves the
high IDs through those rows, but the banks' `.pxd` files are not present on
the discs, so those samples are skipped with a warning. The owner document
gives the record shapes and the bank formula.

### Timing and events

* A bar is four beats. The default is 140 BPM, i.e. 75,600 frames at 44.1 kHz;
  a block is two bars (151,200 frames). `--bpm` overrides the tempo.
* A run is the same id repeated in consecutive bars on one track. Repetition
  is one sounding, not one hit per bar.
* A run longer than its sample repeats the sample to fill the run when the
  sample is at least one bar long.
* A run shorter than its sample plays the whole sample. The next sample on
  the same track cuts it when that next sample starts.
* A sample with no following sample on its track rings out past the grid.
* `total_frames` includes the full run length as well as any ring-out.
* Output is mono.

### CLI options

Common `--pxd DIR` points at the `DANCE` folder that holds `DMACHINE` or
`EJAY` and the sample subfolders; common `--index FILE` overrides the catalog
file. Dance adds no options of its own. Common `--bpm` sets the tempo.

## Dance eJay 2.0 (`dance2`)

### Container

| item | value |
|---|---|
| magic | `0x0A19` at offset 0 |
| header | 8 little-endian u16 words; word 4 is the tempo (140) |
| catalog | name, kit count 9, then 9 kit records |
| palette | `0x01000002` header plus 10 tagged entries |
| song settings | 22 opaque bytes |
| tracks | blocks 1-16 are sample events; block 17 is text |
| footer | `a9 7a 8a 01` |

Each sample track is `u8 track, u32 count`. An entry is 7 bytes when its
i16 time is negative and 17 bytes otherwise:

| form | size | layout |
|---|---|---|
| short | 7 | `u8 flag`, `i16 time`, `i16 second`, `u16 id` |
| long | 17 | the same head plus 10 opaque bytes |

`units = -(time + 1)` for the short form and `time` for the long form;
`bar = units / 128 + 1`. The flag is 0 for `DANCE20` and 3 for an add-on
kit. The owner document gives the catalog, palette and text-track framing:
[`../../docs/formats/MIX_FORMAT_DANCE2.md`](../../docs/formats/MIX_FORMAT_DANCE2.md).

### Samples

`DANCE20.INF`, `DANCESK4.INF`, `DANCESK5.INF` and `DANCESK6.INF` sit beside
their archives in `D_ejay2/PXD`. Each has 12-line records after `[SAMPLES]`;
fields 3 and 4 are the archive offset and byte length. The four id sets are
disjoint, so the id resolves the sample without consulting the flag. The
shared decoder reads each slice as `tPxd` or RIFF/WAVE.

### Timing and events

* A bar is four beats. Header word 4 gives 140 BPM, i.e. 75,600 frames at
  44.1 kHz. `--bpm` overrides it.
* Every entry is a one-shot at `(bar - 1) * 75,600` frames.
* A track is monophonic: a later event cuts the previous sample there; the
  last event on a track rings out.
* Tracks 1-16 use the catalog's pan/volume pairs: pan 0 is centred, 1 is
  left and 2 is right; volume scales by `volume / 32767`.
* Track 17 is a lyric/text track. It is parsed and preserved but not
  rendered.
* Output is interleaved stereo.

### CLI options

Common `--pxd DIR` points at the folder holding the four `.INF` files and
archives (the `D_ejay2/PXD` folder on the disc); common `--index FILE`
names one index explicitly and uses its folder as the sample root. Dance 2
adds no options of its own. Common
`--bpm` overrides the header tempo.

## Hiphop eJay (`hiphop`)

### Container

| item | value |
|---|---|
| magic | `0x0A08` at offset 0 |
| grid | starts at offset 2, exactly 351 blocks of 32 bytes |
| block | two bars x eight tracks, 16 little-endian u16 |
| bar order | words 0-7 are bar 1; words 8-15 are bar 2 |
| empty cell | any value below 731 |
| grid end | offset 11,234 |
| metadata | block at 11,234 (tag `0x0A08`, version 1, creator `"HipHop eJay 1.01"`); trailer at end |

The 351 blocks cover 702 bars. The grid shares its shape with Dance eJay, but
the magic word is `0x0A08` instead of `0x0A06`. A metadata block always follows
the grid (all 17 shipped mixes carry one), and a variable-length trailer ends
the file. See
[`../../docs/formats/MIX_FORMAT_HIPHOP.md`](../../docs/formats/MIX_FORMAT_HIPHOP.md)
for the full layout, including the unverified trailer fields. The parser
accepts any length at or above 11,234 and ignores the metadata block and trailer.

### Samples

The catalog is `HIPHOP/EJAY/PXD` under the resource root, with 1,341 records of
6 quoted lines each (path, unused, category, bars, name part 1, name part 2).
The path is stored directly in the record, as in Dance's `PXDDANCE`; there is
no `PXD.TXT`/`MAX.TXT` key indirection and no high-ID banks.

```text
record_index = sample_id - 731
```

The base ID range is 731-2071. All 1,341 catalog paths resolve to existing
`.pxd` files under `HIPHOP/` (folders `AA` through `BR`). Paths are resolved
case-insensitively under `--pxd`. Each file is decoded as `tPxd` or RIFF/WAVE
by the shared decoder.

### Timing and events

* A bar is four beats. The default is 96 BPM, i.e. 110,250 frames at 44.1
  kHz; a block is two bars (220,500 frames). `--bpm` overrides the tempo.
  The catalog's bar field times 110,250 matches every decoded `tPxd` length,
  so Hiphop does not share Dance's 75,600-frame bar.
* A run is the same id repeated in consecutive bars on one track. Repetition
  is one sounding, not one hit per bar.
* A run longer than its sample repeats the sample to fill the run when the
  sample is at least one bar long.
* A run shorter than its sample plays the whole sample. The next sample on
  the same track cuts it when that next sample starts.
* A sample with no following sample on its track rings out past the grid.
* Output is mono.

### CLI options

Common `--pxd DIR` points at the `HIPHOP` folder that holds `EJAY/PXD` and
the sample subfolders; common `--index FILE` overrides the catalog file.
Hiphop adds no options of its own. Common `--bpm` sets the tempo.

## Techno eJay (`techno`)

### Container

| item | value |
|---|---|
| magic | `0x0889` at offset 0 |
| header | 8 little-endian u16 words; word 4 is the tempo |
| footer | `a9 7a 8a 01` (`0x018A7AA9`) |
| event marker | `>?~>` (`3e 3f 7e 3e`) |
| event table | 4 unknown prefix bytes, then blocks for tracks 1..17 |

Each track block is `u8 track, u32 count`, followed by `count` entries.
An entry is 7 bytes when its time field is negative and 17 bytes when it is
zero or positive:

| form | size | layout |
|---|---|---|
| short | 7 | `u8 flag`, `i16 time`, `i16 second`, `u16 id` |
| long | 17 | the same 7 bytes plus 10 parameter bytes |

The time is a fixed-point bar position with seven fraction bits. Short entries
store it negated. `units = abs(time) - (1 if time < 0 else 0)` and
`bar = units / 128 + 1`; bar 1 is the start of the mix. The ten extra bytes of
the long form are preserved as `parameters["long"]` but not interpreted.

### Samples

`RAVE20.INF` holds 12-line records after `[SAMPLES]`. The first field is the id
the mix references; field 3 is the byte offset inside the `RAVE20` archive and
field 4 the byte length. The archive slice is decoded by the shared decoder.
Techno eJay has no per-sample `.pxd` files.

### Timing and events

* A bar is four beats. At the default 140 BPM that is 75 600 frames at
  44.1 kHz. `--bpm` overrides the header tempo.
* Every entry is a one-shot at its bar position.
* Tracks 4, 13, and 15 are left-only; 5, 14, and 16 are right-only; the rest
  are centred. A centred track is at full scale in both channels, not at half
  scale: the engine has no 0.5 factor on its gain path and pans by selecting
  the output channel (`../../docs/formats/MIX_FORMAT_TECHNO.md` §13).
* Output is interleaved stereo.

### CLI options

Common `--pxd DIR` points at the folder holding the `RAVE20` archive and
common `--index FILE` at the `RAVE20.INF` file. Techno adds no options of its
own. Common `--bpm` overrides the header tempo.

## Rave vs Dance vs Dance 2 vs Hiphop vs Techno

| item | Rave | Dance | Dance 2 | Hiphop | Techno |
|---|---|---|---|---|---|
| magic | `0x0A07` | `0x0A06` | `0x0A19` | `0x0A08` | `0x0889` |
| arrangement | grid records | 351 two-bar blocks | per-track event table | 351 two-bar blocks | per-track event table |
| sample ids | `id - 731` into `EJAY/PXD` | `id - 731` into `PXD.TXT`, then key into `MAX.TXT` | id into four `.INF` indexes | `id - 731` into `EJAY/PXD` | id into `RAVE20.INF` |
| sample storage | standalone files | standalone files | archive slices | standalone files | slices of `RAVE20` |
| tempo | not stored; CLI/default | not stored; 140 BPM default | header word 4 | not stored; 96 BPM default | header word 4 |
| tracks | 8, two lanes | 8 | 16 plus a text track | 8 | 16, plus an empty 17th block |
| event length | run of repeated ids | run of repeated cells | one-shot | run of repeated cells | one-shot |
| output | mono | mono | stereo | mono | stereo |
| pan | none | none | per-track pan/volume | none | track-based |

## Known limits

* Techno's long-entry parameter bytes are kept but not applied. The manual's
  per-placement volume and cut controls are plausible owners.
* Techno's compact grid before the trailer is still not interpreted; the
  arrangement comes from the event table.
* Rave's record length is not stored. The default of two bars is derived from
  the sample bank and the placement pattern, as documented in the format
  notes.
* Dance's `PXD.TXT` header values and the high word of its catalog key are not
  interpreted. Only the low word, which selects the path, is used.
* Dance 2's header words 2, 5 and 7, the 22-byte song settings, the palette
  parameters, the long entry's 10 bytes and the text prefix are preserved but
  not interpreted.
