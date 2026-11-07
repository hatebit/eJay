# Dance eJay 2.0 `.MIX` format (from `disks/Dance_2`)

Source: the 13 mixes in `disks/Dance_2/MIX/`, plus `DANCE20.INF`,
`DANCESK4.INF`, `DANCESK5.INF`, `DANCESK6.INF` and the four archives beside
them in `disks/Dance_2/D_ejay2/PXD/`. Everything below comes from parsing
those bytes; no original executable was loaded or run. Confidence tags are
`[certain]`, `[likely]` and `[guess]`.

The implementation is
[`player/formats/dance2/`](../../player/formats/dance2/). It is a distinct
format from Dance eJay 1 (`0x0A06`, documented in
[`MIX_FORMAT_DANCE.md`](MIX_FORMAT_DANCE.md)): the magic is different and the
arrangement is an event table, not a 351-block grid.

## 1. The shipped mixes

All 13 files parse from offset 0 to the footer with no leftover bytes, and
every sample id resolves in exactly one `.INF`. `[certain]`

| file | bytes | title | description | sample events | text events |
|---|---:|---|---|---:|---:|
| `CAMRON.MIX` | 7,330 | `Yo!B` | The Land of Camron | 361 | 93 |
| `HAPPY.MIX` | 8,219 | `MC Magic` | Rock the Beat Remix | 222 | 138 |
| `HOUSE.MIX` | 3,553 | `MC Magic` | House Mix | 379 | 0 |
| `LATIN.MIX` | 3,999 | `MC Magic` | Latin Dance Mix | 437 | 0 |
| `LIFEXL.MIX` | 6,280 | `Yo!B` | Art and Style Mix | 266 | 78 |
| `OTHER.MIX` | 2,455 | `MC Magic` | He does it like no other | 205 | 0 |
| `PARTY.MIX` | 2,948 | `MC Magic` | Short Cut Mix | 247 | 8 |
| `SENNER.MIX` | 2,517 | `MC Magic` | Rock on the Mountains Remix | 128 | 17 |
| `START.MIX` | 6,124 | `MC Magic` | Take me by the Hand | 322 | 71 |
| `STEP.MIX` | 1,553 | `MC Magic` | Duck Dance | 6 | 16 |
| `TRANCE.MIX` | 4,271 | `MC Magic` | Trance Mix | 481 | 0 |
| `TRIBUTE.MIX` | 2,870 | `DJ Andy` | Bring It On ! | 282 | 0 |
| `YOURTIME.MIX` | 4,485 | `MC Magic` | Don't Waste My Time Mix | 334 | 28 |

## 2. File layout

All integers are little-endian. Strings are Latin-1 unless they are the
names in the sample index. A stored name ends with `00 01`; the `01` is a
terminator, not part of the text. `[certain]`

| region | size | content |
|---|---:|---|
| header | 16 | eight `u16` words |
| title | variable | NUL-terminated string at `0x10` |
| subtitle | variable | NUL-terminated `#SKKENNUNG#:0000000` |
| description | `3 + n` | `u8 0x01`, `u16 n`, `n` bytes ending `00 01` |
| track settings | 64 | 16 x (`u16` pan, `u16` volume) |
| reserved | 8 | eight zero bytes |
| catalog | variable | name, kit count, then the kit records |
| palette | variable | 4-byte tag header, then ten tagged entries |
| song settings | 22 | opaque bytes, preserved |
| sample tracks | variable | blocks for tracks 1 to 16 |
| text track | variable | block 17, lyric records |
| footer | 4 | `a9 7a 8a 01` |

The palette and event table move with the length of the names before them.
The observed table starts are: CAMRON `0x328`, HAPPY `0x320`, HOUSE `0x32B`,
LATIN `0x32B`, LIFEXL `0x32F`, OTHER `0x32B`, PARTY `0x322`, SENNER `0x332`,
START `0x32E`, STEP `0x319`, TRANCE `0x32F`, TRIBUTE `0x327`, YOURTIME
`0x32F`. `[certain]`

## 3. Header

```
word:  0      1  2      3  4      5      6  7
       0A19   00 NNNN   00 008C   MMMM   00 LLLL
```

| word | observed | meaning | confidence |
|---|---|---|---|
| 0 | `0x0A19` | magic | certain |
| 1 | 0 | constant | certain |
| 2 | 27-304 | varies per file, unresolved | guess |
| 3 | 0 | constant | certain |
| 4 | 140 in all 13 | tempo in BPM | likely |
| 5 | 136-152 | varies; 140 in 9 files | guess |
| 6 | 0 | constant | certain |
| 7 | 26, 29 or 30 | varies per file, unresolved | guess |

Word 4 is treated as the tempo because 140 BPM with four beats per bar gives
75,600 frames per bar, which matches the sample lengths and every placement.
Word 5 is not a second tempo: HOUSE stores 136 and HAPPY 152 while both use
the same 75,600-frame bar. It may be a source tempo for a stretched vocal
track, but that is unproven. `[guess]`

## 4. Text block

The block starts at `0x10`. CAMRON is a compact example: `[certain]`

```
0x10  "Yo!B\0"                         title
0x15  "#SKKENNUNG#:0000000\0"          subtitle
0x29  01                               description marker
0x2A  14 00                            u16 length = 20
0x2C  "The Land of Camron\0\1"         description
0x40                                   next section
```

The title is not always the song name: `Yo!B` and `MC Magic` are artist
names, and the description is the mix name. The player displays
`"<title> - <description>"`. The subtitle is constant in all 13 files. `[certain]`

## 5. Track settings

Immediately after the description are 16 (`u16` pan, `u16` volume) pairs,
one per sample track, then eight zero bytes. CAMRON shows the range: `[certain]`

```
track  1: pan 0, volume 29127      track  9: pan 2, volume 14563
track  2: pan 0, volume 26699      track 10: pan 1, volume 14563
...
track  8: pan 0, volume 30340      track 16: pan 2, volume  9304
```

Only pan codes 0, 1 and 2 occur. The player maps 0 to both channels, 1 to
left only and 2 to right only, and scales by `volume / 32767`. This is a
`[likely]` interpretation: the code values line up with the left/right halves
of the stereo sample pairs on tracks 9-16, but no engine code has been read
for Dance eJay 2.0.

## 6. Catalog and kit records

The catalog starts with `u16 0`, a `u16` name length, the name
`"Dance eJay 2.0\0\1"`, then `u16 count = 9`, `u32 2000` and `u32 3399` in
all 13 files. `[certain]`

`count` is the number of kit records, not the number of named kits. Each
record is: `[certain]`

```
u16 name_length
name_length bytes, ending 00 01
u32 first_id
u32 last_id
```

Seven records are named and two are empty; the count of 9 covers all of
them. CAMRON's rows:

| # | name | first | last |
|---:|---|---:|---:|
| 0 | DanceMachine Samples | 3400 | 3899 |
| 1 | DanceMachine Samplekit Vol. 1 Raps & Voices | 3900 | 4499 |
| 2 | DanceMachine Samplekit Vol. 2 Drums & Synthies | 4500 | 5099 |
| 3 | DanceMachine Samplekit Vol. 3 Space Sounds | 5100 | 5799 |
| 4 | Dance eJay Samplekit Vol. 4 House | 5800 | 6499 |
| 5 | Dance eJay Samplekit Vol. 5 Trance | 6500 | 7199 |
| 6 | Dance eJay Samplekit Vol. 6 Latin Dance | 0 | 0 |
| 7 | (empty) | 0 | 0 |
| 8 | (empty) | 0 | 0 |

The ranges are catalog slot ranges, not ids inside the archives: DANCE20
holds `1-1957`, not `3400-3899`. Kit 6 already has `0, 0`, so zero does not
mark the end of the list; the count does. `[certain]`

## 7. Sample palette

Next is a 4-byte header equal to `0x01000002`, followed by tagged entries.
Each entry is: `[certain]`

```
u32 tag = 0x01000002
u16 sample_id
u16 name_length
name_length bytes, ending 00 01
u32 first
u32 second
```

All 13 files have exactly ten entries. CAMRON's palette, which is also its
most-used sample set: `[certain]`

| id | name | first | second |
|---:|---|---:|---:|
| 1453 | 808kick | 0 | 26578 |
| 1488 | nordlead2 | 0 | 10559 |
| 1545 | linnsn 2 | 0 | 26578 |
| 1643 | elec.hat | 0 | 26578 |
| 1647 | clsd.hat5 | 0 | 26578 |
| 1723 | badsplash | 0 | 26578 |
| 1796 | HR16clap | 0 | 26214 |
| 1780 | egg2 | 0 | 26578 |
| 1918 | hit5 | 0 | 26577 |
| 1952 | fear1 | 65533 | 26578 |

The second field clusters at 26,578, which looks like a frame or block count,
but it is not the decoded length of the records and the player does not use
it. `[guess]`

## 8. Song settings

Exactly 22 bytes follow the palette. CAMRON (`0x312`):

```
00 00 ff 7f 9e 3f 00 00 5f 20 7f 3e
00 00 3e 3f 13 3f 7a 19 00 00
```

The contents are not understood; the parser preserves them as
`song_settings`. `[guess]`

## 9. Event table

The table starts right after the 22 bytes. Tracks 1 to 16 use 7-byte or
17-byte entries; track 17 holds text. `[certain]`

### 9.1 Sample tracks (1-16)

Each block is `u8 track, u32 count`, in order, with `track` equal to the
1-based track number.

| form | size | layout |
|---|---:|---|
| short | 7 | `u8 flag`, `i16 time`, `i16 second`, `u16 sample_id` |
| long | 17 | the same 7 bytes plus 10 opaque bytes |

An entry is long exactly when `time >= 0`, otherwise short. The two forms
encode the position differently: `[certain]`

```
short: units = -(time + 1)     second is -1 in every observed entry
long:  units = time            second is 0 in every observed entry
bar = units / 128 + 1
```

So one bar is 128 units and bar 1 is the start of the mix. This is the same
fixed-point grid Techno uses; a long entry is not a different time base.
OTHER's track 8 has long entries at 0, 128, 256 ... 1408, i.e. one per bar
for twelve bars. `[certain]`

The head byte selects the archive: 0 uses DANCE20, 3 uses one of the add-on
archives. The id alone is enough to resolve a sample because the archive id
ranges do not overlap. `[certain]`

The long form's 10 trailing bytes are zero except for a final `u16` that
varies per record (e.g. `af eb`, `f0 fb`). The parser keeps them as
`extension` and the player ignores them. `[certain]`

Only 16 long entries exist on the disc: four in LATIN and twelve in OTHER.
The rest are short. `[certain]`

### 9.2 Text track (17)

Track 17 begins with the same `u8 17, u32 count` header. Each record is:
`[certain]`

```
u8 flag, i16 time, i16 second     5 bytes, same time rule as above
22 opaque bytes
u16 name_length, name bytes ending 00 01
u16 value_length, value bytes
```

The names are lyric words or phrases (`You`, `can`, `even`, `B!Yo_1`) and
the values are short tags (`1`, `2`, `5`, or empty). They are a
text/vocoder track, not sample references: no sample id is stored and the
22-byte prefix does not resolve against any archive. The player preserves
the records in `Dance2MixData.text_events` and does not render them.
`[certain]` for the layout; `[likely]` for the lyric interpretation.

### 9.3 Footer

The last four bytes are `a9 7a 8a 01` in all 13 files. The table must end
exactly at the footer; a mismatch is a container error. `[certain]`

## 10. Samples

The four `.INF` files are 12-line records after a `[SAMPLES]` line: id,
group, quoted name, byte offset, byte size, quoted category, quoted part,
two numbers, an empty string, a number and another empty string. The archive
is the sibling file with the same stem, without the extension. `[certain]`

| archive | records | id range | used by flag |
|---|---:|---|---|
| `DANCE20` | 1,957 | 1-1957 | 0 |
| `DANCESK4` | 598 | 5100-5703 | 3 |
| `DANCESK5` | 677 | 5800-6476 | 3 |
| `DANCESK6` | 564 | 0-7063, sparse | 3 |

The four id sets are disjoint. Every sample event in all 13 mixes resolves
to exactly one record; DANCE20 covers every flag-0 event, while flag-3
events use DANCESK4 (HOUSE), DANCESK5 (TRANCE) or DANCESK6 (LATIN).
`[certain]`

Each record points at a slice that starts with `tPxD`; the shared decoder
reads it in place, so there are no per-sample `.pxd` files. `[certain]`

The player finds the folder by checking, in order: `--pxd`, the mix folder
and its `PXD` child, the mix parent and its `PXD`, `EJAY/PXD` and
`D_ejay2/PXD` children, the current directory, then one level of
subdirectories and their `PXD` children. `--index` can name one `.INF`
explicitly; its folder is then used as the sample root, so the other known
indexes there are still merged in. `[certain]`

## 11. Playback model

* The tempo is header word 4 (140 BPM), four beats per bar, 75,600 frames
  per bar at 44.1 kHz. `--bpm` overrides it. `[likely]`
* Every event is a one-shot at `(bar - 1) * frames_per_bar`. `[likely]`
* A track is monophonic: when another event starts on the same track, the
  earlier sample is cut there. The last event on a track rings out for its
  whole decoded length. `[likely]`
* Output is interleaved stereo. Track gain and pan come from section 5.
  `[likely]`
* Text events are not rendered. `[certain]`
* A missing id becomes a per-sample warning; `--strict` turns the collected
  warnings into an error before playback. `[certain]`

## 12. Differences from Dance eJay 1 and Techno eJay

| item | Dance eJay 1 | Dance eJay 2.0 | Techno eJay |
|---|---|---|---|
| magic | `0x0A06` | `0x0A19` | `0x0889` |
| arrangement | 351 x two-bar blocks | per-track event table | per-track event table |
| time base | block index | 128 units per bar | 128 units per bar |
| tracks | 8 | 16 sample tracks + a text track | 16 sample tracks + an empty block |
| sample source | `DMACHINE/PXD.TXT` + `MAX.TXT`, or `EJAY/PXDDANCE` | four `.INF` indexes + four archives | `RAVE20.INF` + `RAVE20` |
| footer | none | `a9 7a 8a 01` | `a9 7a 8a 01` |
| output | mono | stereo | stereo |

## 13. Open questions

* Header words 2, 5 and 7. Word 5 is 136-152 and does not affect the bar
  length; the others vary without an identified meaning. `[guess]`
* The 22 song-settings bytes. They are preserved but never applied. `[guess]`
* The palette's `first` and `second` parameters, especially the `0x67D2`
  cluster. `[guess]`
* The long entry's 10-byte extension. `[guess]`
* The text record's 22-byte prefix. It is preserved byte for byte. `[guess]`
* Whether the kit ranges are installed-slot ranges or something else; they
  do not match archive ids. `[guess]`

## 14. Verification

The reader parses all 13 files to the footer, reconstructs 3,670 sample
events and 449 text events, and every sample id resolves. Loading every mix
with `strict` reports zero warnings. The player suite includes synthetic
fixtures for detection, parsing, cutting, pan/volume, long entries, add-on
archives, text preservation, listing and strict mode:

```sh
python -m player.test_mix_player
python -m player "disks/Dance_2/MIX/CAMRON.MIX" --list
```
