# Rave eJay `.MIX` File Format (reverse-engineered notes)

Status: **grid layout, record length and sample-ID resolution understood; trailer and some cell
semantics still unknown**.
Derived from one sample file, `TRANCE.MIX` (11,276 bytes, written by "Rave eJay 1.01"), plus the
install's sample index `disks/Rave_eJay/RAVE/EJAY\PXD`. Items marked *(inferred)* fit the data but are not confirmed
against the original program.

All integers are **little-endian 16-bit words** unless noted.

## 1. File layout

| Offset  | Size              | Content                                                    |
|---------|-------------------|------------------------------------------------------------|
| 0       | 2                 | Header word `0x0A07` (version/magic *(inferred)*)          |
| 2       | 351 x 32 = 11,232 | Arrangement grid: 351 records of 16 words                  |
| 11,234  | 2                 | Trailer tag `0x0A08`                                       |
| 11,236  | 2                 | `0x0001`                                                   |
| 11,238  | 2                 | `0x0010` (16, probably the length of the string field)     |
| 11,240  | 16                | `"Rave eJay 1.01"` + NUL (+ one stray `0x01` byte)         |
| 11,256  | 20                | Small values, see section 4 (16 shown; final 4 words not yet captured) |

Check: `2 + 351*32 = 11,234`, exactly where the trailer tag begins. So the grid is 351 records
after a single header word. (Reading the file as 32-byte rows from offset 0 misaligns every cell
by one word; the 1-word header shift matters.)

The only printable ASCII in the file is the version string at offset 11,240.

## 2. Arrangement grid

Each record is 16 words:

```
word:   0  1  2  3  4  5  6  7 | 8  9 10 11 12 13 14 15
        T1 T2 T3 T4 T5 T6 T7 T8| B0 B1 B2 B3 B4 B5 B6 B7
        '---- track cells A ---'  '--- second-layer cells B --'
```

- **A lane (words 0-7)**: one cell per track, 8 tracks (matches eJay's 8-track design). A
  non-zero value is a **sample ID** (section 3); `0` is empty.
- **B lane (words 8-15)**: a second cell per track, same ID space. `B(k)` belongs to track
  `T(k+1)` *(inferred, fits every case checked)*. It looks like an overlay/overflow slot for a
  second sample sounding on the same track at the same time (section 6).
- A record is one time step. It is **two bars** long: 117 600 frames at 44.1 kHz (2.667 s),
  i.e. 8 beats at 180 BPM (section 2.1). Nothing in the file stores that; it follows from the
  arrangement and from the bank, and both players default to it (`--step` overrides).
- Only records 0-78 are used (79 steps). Records 79-350 are zero padding, apart from stray bytes
  (section 7). 351 is presumably a fixed maximum.
- **Cells below `0x2DB` (731) are not samples.** 731 is the lowest ID the index resolves
  (section 3), and the stray values in the padding are all in `1..15`, so a reader must treat any
  cell `< 731` as empty. Skipping that filter turns the padding counter into 15 phantom samples
  (`0x001`-`0x00F`) and reports 249 used records instead of 79.
- A sample placed over several steps is stored as the **same ID repeated in every record it
  covers** (e.g. `0x338` on T3 for records 6-35). There is no explicit length field, but a
  sample's own length is a whole number of **bars** of 58 800 frames (the number every bank PXD
  carries in its comment, section 2.1), so it is either a whole record or half of one. A run
  longer than its sample is the sample repeated: `0x338` is a one-bar bass loop placed over 30
  records. A run shorter than its sample still plays the whole sample - samples are not cut
  mid-song. The only structural stop is the start of the final record: earlier samples stop
  there, while a placement in that record is the song's ending and rings out past it (the final
  `0x6DA` voice plays its whole 2.667 s).

### 2.1 Record length: two bars, 117 600 frames

No field in the `.MIX` holds a tempo, and the sample index says nothing about one either. Two
independent measurements pin the record:

- **The bank is quantised in bars of 58 800 frames** (1.333 s, 4 beats at 180 BPM): every one of
  the 34 samples `TRANCE.MIX` uses decodes to an exact multiple of 58 800 frames, and the last
  line of every bank PXD's comment is that same `58800` — the **bar size**, not the sample's own
  length (verified in 1 277 of the 1 278 `tPxD` files on the image; the comment is the sample's
  six-line library record, see [`PXD_FORMAT.md`](PXD_FORMAT.md), "Comment-line
semantics"), whatever its own
  length (e.g. `R1BS094` = 2 x 58 800, `R1SQ084R` = 8 x 58 800).
- **The arrangement places samples so that each one ends exactly when the next one on its track
  starts** - but only if a record is 2 x 58 800 = 117 600 frames. Over `TRANCE.MIX`'s 90
  consecutive same-track placements, no sample then runs into its successor; at 58 800 frames
  35 of them do (a 2.667 s sample placed one record later, as `0x637`/`0x638` are, would be cut
  in half). The 8-bar samples (`0x340`, `0x5EC`/`0x5ED`, `0x665`) are placed 4 records apart,
  exactly their own length; the 4-bar `0x637`/`0x638` alternate every 2 records; the one-bar
  `0x6E1` sits on single records.

A record of 58 800 frames - one bar, the previous default - makes the play time exactly half the
song's: `TRANCE.MIX` lasts 1:46 instead of 3:30, which is why both players now default to
117 600 frames. Which of the two is "the BPM" (180 BPM at two bars per record, or 90 BPM at one)
cannot be told from the data; only the record length matters for playback.


## 3. Resolving sample IDs to files (`disks/Rave_eJay/RAVE/EJAY\PXD`)

The sample index is the plain-text file `disks/Rave_eJay/RAVE/EJAY\PXD` (CRLF line endings, 66,525 bytes). It is a list
of **1,149 records of 6 quoted lines each**:

```
"bq\r1bs001.pxd"      line 1: directory\filename (relative to disks/Rave_eJay/RAVE)
""                    line 2: (always empty in the records seen)
"bass"                line 3: category
"2"                   line 4: length in bars of 58 800 frames (1,2,3,4,8 seen; section 2.1)
"wood walk"           line 5: name part 1
"1"                   line 6: name part 2 (often empty)
```

(the file ends with an empty trailing line after the last record, `aj\r1vx135.pxd`, a voice entry
named "http://www.eJay.com")

Categories (record counts): drum 224, sequence 165, sphere 164, loop 142, voice 141, bass 120,
special 116, effect 77. These match the file-name prefixes: `BS` bass, `DA..DF` drum, `FX` effect,
`LA..LC` loop, `SF` special, `SQ` sequence, `SR` sphere, `VX` voice.

### The ID -> record rule

```
record_index (0-based) = sample_id - 731
```

Evidence for the 731 offset (the other offsets that satisfy L/R pairs, 664 and 867, were rejected:
867 gives a negative index for `0x338`; 664 gives incoherent names):

- Consecutive IDs on one track resolve to consecutive, musically related records:
  `0x3d6..0x3d9` = "hihat smooth 1..4" (all on T5), `0x514..0x516` = "gum 1..3" (T4),
  `0x535..0x537` = "two tunes delayed 2..4" (T3), `0x637/0x638` = "light layer 1/2" (T1).
- IDs on the same track are in the same category (T3 bass, T5 drums, T7/T8 spheres/sequences).
- The three adjacent pairs that occupy T7/T8 resolve to real stereo `L`/`R` file pairs
  (`SQ084L/R`, `VX015L/R`, `SR021L/R`).
- The file is called `TRANCE.MIX` and uses a voice sample named "trance" (`0x6e1`).
- The "bad crash" (`0x3fe`) lands on section boundaries, and a "rip" effect (`0x47f`) and snare
  fills sit just before the transition at record 36.
- 1,149 records, in 30 folders of 39 files each (`AK` has 27, `BS` has 30), so the folder names are
  just disc/storage buckets, not categories.

It is not known why the offset is 731 (IDs below 731 are not in this index; they may be reserved
or belong to another list). The rule is derived from this single mix, so treat it as strongly
supported but not proven.

Folder and file existence was checked on disk for `AA`, `AB`, `AC`, `AJ`, `BF`, `BS`; every
file the rule predicts for those folders is present.

## 4. Trailer

Words from offset 11,234:

```
0A08 0001 0010 | "Rave eJay 1.01\0" + 01 | 0000 0008 0000 0000 0000 0000 0000 0001 0002
```

- `0x0A08`: trailer tag, one higher than the header word `0x0A07`.
- `0x0010`: 16, matches the length of the string field including padding.
- After the string: `0x0008` at offset 11,258 and `0x0001`, `0x0002` in the last 4 bytes. `8` may
  be the track count; the others are unknown (could be tempo/flags). **Unconfirmed**, single file.

## 5. Arrangement of TRANCE.MIX with sample names

Records are 0-78. Format `ID name [records]`; repeated hits are condensed. Full path of each
sample is in the table in section 5.1.

- **T1**: `637` light layer 1 and `638` light layer 2 alternating every 2 records (0-18, 36-38);
  `710` blue & white jewel at 21/29/33; `48a` muffled FX at 40-55 and 66-77; `3fe` bad crash at 56.
- **T2**: `6e1` trance at 3/5/7/42; `710` at 17; `48a` at 20-35; `711` sky blue sphere at 36/39;
  `3fe` at 48; `3c8` at 52; `6da` eJay 4 R at 78.
- **T3**: `338` just walking (bass) at 6-35; `535`/`536`/`537` two tunes delayed 2/3/4 at 36/37-39/
  40-43; `340` the soul interlocked (bass) at 44/48/52; `3c8` at 74.
- **T4**: `514`/`515`/`516` gum 1/2/3 build at 8-16 (with `6e1` trance at 15), `516` at 18-35; `536` at 40-43; `3fe` at 44;
  `626`/`625` infantila 2/1 at 48-55; `665` trancepiration L at 62/66/70/74.
- **T5**: `3d6` hihat smooth 1 at 14-23, `3d7` smooth 2 at 24-31, `3d8` smooth 3 at 32-35 and 41-55
  and 74-77; `3ce` pipe snare fill 1 at 38; `3d9` smooth 4 at 40.
- **T6**: `3ce` at 30/34; `47f` rip at 32; `3fe` at 36/39/40; `6e1` at 38; `3c6` snare fill nature 3
  at 42; `3c8` snare fill long and phasing at 44; `420` shaker 2 at 52-55; `710` at 59; `711` at
  63-72 (every other record: 63, 64, 66, 68, 70, 72).
- **T7**: `3fe` at 35; `5ed` slippery multi sweeper R at 36/40/44; `6da` eJay 4 R at 48-54;
  `649` fairy tale 3 L at 56-77.
- **T8**: `5ec` sweeper L at 36/40/44; `6d9` eJay 4 L at 48-55; `64a` fairy tale 3 R at 56-77.

Rough structure *(inferred)*: intro 0-13, build 14-35, transition 36-47, main 48-55, outro 56-77.
Note that L/R stereo pairs are split across T7/T8 but not always in the same order (L on T7 for
`649`, R on T7 for `5ed`/`6da`).

### 5.1 All 33 sample IDs used (A lane, plus IDs only seen in the B lane)

`PXD` = `disks/Rave_eJay/RAVE/EJAY\<dir>\<file>`. `N` is the number from index line 4.

| ID    | dec  | rec  | Path                    | Cat      | N | Name                         |
|-------|------|------|-------------------------|----------|---|------------------------------|
| 0x338 | 824  | 93   | BD\R1BS094.PXD          | bass     | 2 | just walking                 |
| 0x340 | 832  | 101  | AJ\R1BS102.PXD          | bass     | 8 | the soul interlocked         |
| 0x3c6 | 966  | 235  | AC\R1DB026.PXD          | drum     | 4 | snare fill nature 3          |
| 0x3c8 | 968  | 237  | AI\R1DB028.PXD          | drum     | 8 | snare fill long and phasing  |
| 0x3ce | 974  | 243  | AE\R1DB034.PXD          | drum     | 4 | pipe snare fill 1            |
| 0x3d6 | 982  | 251  | BS\R1DC001.PXD          | drum     | 2 | hihat smooth 1               |
| 0x3d7 | 983  | 252  | BN\R1DC002.PXD          | drum     | 2 | hihat smooth 2               |
| 0x3d8 | 984  | 253  | BP\R1DC003.PXD          | drum     | 2 | hihat smooth 3               |
| 0x3d9 | 985  | 254  | BQ\R1DC004.PXD          | drum     | 2 | hihat smooth 4               |
| 0x3fe | 1022 | 291  | BB\R1DD001.PXD          | drum     | 1 | bad crash                    |
| 0x420 | 1056 | 325  | BF\R1DF010.PXD          | drum     | 2 | shaker 2                     |
| 0x47f | 1151 | 420  | BB\R1FX072.PXD          | effect   | 1 | rip                          |
| 0x48a | 1162 | 431  | BI\R1LA011.PXD          | loop     | 2 | muffled FX                   |
| 0x4ef | 1263 | 532  | BC\R1LB001.PXD          | loop     | 1 | trash break                  |
| 0x514 | 1300 | 569  | BF\R1SF007.PXD          | special  | 2 | gum 1                        |
| 0x515 | 1301 | 570  | BI\R1SF008.PXD          | special  | 2 | gum 2                        |
| 0x516 | 1302 | 571  | BM\R1SF009.PXD          | special  | 2 | gum 3                        |
| 0x535 | 1333 | 602  | BF\R1SF036.PXD          | special  | 2 | two tunes delayed 2          |
| 0x536 | 1334 | 603  | BE\R1SF037.PXD          | special  | 2 | two tunes delayed 3          |
| 0x537 | 1335 | 604  | BR\R1SF038.PXD          | special  | 2 | two tunes delayed 4          |
| 0x5ec | 1516 | 785  | AJ\R1SQ084L.PXD         | sequence | 8 | slippery multi sweeper L     |
| 0x5ed | 1517 | 786  | AJ\R1SQ084R.PXD         | sequence | 8 | slippery multi sweeper R     |
| 0x625 | 1573 | 842  | BQ\R1SQ129.PXD          | sequence | 2 | infantila 1                  |
| 0x626 | 1574 | 843  | BM\R1SQ130.PXD          | sequence | 2 | infantila 2                  |
| 0x637 | 1591 | 860  | AB\R1SR011.PXD          | sphere   | 4 | light layer 1                |
| 0x638 | 1592 | 861  | AB\R1SR012.PXD          | sphere   | 4 | light layer 2                |
| 0x649 | 1609 | 878  | BE\R1SR021L.PXD         | sphere   | 2 | fairy tale 3 L               |
| 0x64a | 1610 | 879  | BF\R1SR021R.PXD         | sphere   | 2 | fairy tale 3 R               |
| 0x665 | 1637 | 906  | AI\R1SR038L.PXD         | sphere   | 8 | trancepiration L             |
| 0x6d9 | 1753 | 1022 | BP\R1VX015L.PXD         | voice    | 2 | eJay 4 L                     |
| 0x6da | 1754 | 1023 | BQ\R1VX015R.PXD         | voice    | 2 | eJay 4 R                     |
| 0x6e1 | 1761 | 1030 | BP\R1VX022.PXD         | voice    | 2 | trance                       |
| 0x710 | 1808 | 1077 | AA\R1VX068.PXD          | voice    | 3 | blue & white jewel           |
| 0x711 | 1809 | 1078 | AB\R1VX069.PXD          | voice    | 3 | sky blue sphere              |

## 6. Meaning of previously unclear values (corrected)

An earlier version of these notes guessed `0x710`/`0x711` were markers. That was wrong:
they are two consecutive **voice samples** ("blue & white jewel" then "sky blue sphere").

- `0x710` in an A cell is followed one record later by `0x711` in the **B cell of the same track**
  (T1 `710` at 21/29/33 then B0 `711` at 22/30/34; T2 `710` at 17 then B1 `711` at 18). So B is the
  slot where a second sample starts while the first is still sounding.
- B cells that repeat the A cell of the same track at the same record: B6=`3fe` at 35 (T7 `3fe`),
  B5=`3fe` at 39 (T6 `3fe`), B5=`47f` at 32 (T6 `47f`). B5=`6e1` at 40 sits on T6 beside `3fe`,
  i.e. two samples at once on one track.
- `0x3fe` "bad crash" and `0x6e1` "trance" are one-shots used on many tracks, so tracks are not
  bound to a single category.
- `0x4ef` "trash break" only appears in B0 (T1 second layer), records 55 and 77, the last record of
  the main and outro sections.
- Not fully explained: B6 and B7 both holding `47f` at record 31 (one sample across two columns).

## 7. Stray data in the padding

Single bytes outside the used grid, probably leftover memory from the struct dump (not data).
Because of them a plain "last non-zero record" is not the end of the song, and any non-zero value
there is not a cell:
[`../../work/src/mixplay.py`](../../work/src/mixplay.py) ignores cells below 731
(section 2).

- Offset 6,638 = `0x0C`, offset 6,640 = `0x07` (record 207).
- Offsets 7,660-7,948: a sequence in steps of 16 bytes with every 4th slot empty:
  `5 a f _ 4 9 e _ 3 8 d _ 2 7 c _ 1 6 b` (this is `(5*n) mod 16` counting, so it looks like
  a counter pattern, not music data).

## 8. Not known / next steps

1. Why the ID offset is 731, and which list holds IDs 0-730 (check `EJAY\HYPSOUND`, `HYPRESET`,
   `MAX`, `MIN`). Partly answered: the values below 731 that occur in the grid are the padding
   leftovers of section 7, not a second ID space.
2. Confirm the meaning of the index's `N` field and where tempo is stored: save mixes with known
   edits (one sample at a known position, a known BPM) and diff. The time unit of a record is
   settled to 117 600 frames by the arrangement itself (section 2.1); `N` counts the sample's
   own length in bars of 58 800 frames, which is verified against the decoded durations of all
   34 samples `TRANCE.MIX` uses.
3. Confirm the B-lane meaning with a mix that layers two samples on one track.
4. The trailer values.
5. Verify on-disk presence of the remaining mapped folders (`AE`, `AI`, `BB`, `BC`, `BD`, `BE`,
   `BI`, `BM`, `BN`, `BP`, `BQ`, `BR`).

## 9. Reference parser (Python)

```python
import struct

ID_OFFSET = 731  # record_index = sample_id - ID_OFFSET (see section 3)

def read_mix(path):
    d = open(path, "rb").read()
    header = struct.unpack_from("<H", d, 0)[0]            # 0x0A07
    tag = d.find(b"\x08\x0a", 2)                          # trailer tag 0x0A08 (verify alignment)
    while tag != -1 and (tag - 2) % 32:
        tag = d.find(b"\x08\x0a", tag + 1)
    n = (tag - 2) // 32                                   # 351 for TRANCE.MIX
    recs = [struct.unpack_from("<16H", d, 2 + 32 * i) for i in range(n)]
    tracks = [r[:8] for r in recs]                        # A lane: sample IDs, T1..T8
    layer2 = [r[8:] for r in recs]                        # B lane: second sample per track
    return header, tracks, layer2

def read_index(path):
    lines = open(path, "rb").read().decode("latin-1").split("\r\n")
    recs = [[x.strip('"') for x in lines[i:i + 6]] for i in range(0, len(lines) - 1, 6)]
    return recs   # [path, '', category, n, name1, name2]

def sample_for(sample_id, index):
    r = index[sample_id - ID_OFFSET]
    return r[0].replace("\\", "/").upper(), r[2], " ".join(x for x in r[4:] if x)
```

The `find` for the trailer tag is a heuristic (`0x0A08` could also occur inside the grid);
the first 32-byte-aligned match was correct for `TRANCE.MIX`.

## 10. Player

[`../../work/src/mixplay.py`](../../work/src/mixplay.py) implements this: it
reads the grid, resolves every ID through
the index (`sample_id - 731`), and queues the arrangement on the engine's play
ring ([`../../work/docs/PLAYBACK.md`](../../work/docs/PLAYBACK.md)). Runs of one
ID become a single request spanning those
records, so a repeated cell is one sounding rather than one hit per record; a
sample shorter than its run ends early, a longer one is cut at the run's end.
The engine's request queue cannot repeat a file, so `mixplay` plays one copy of
a sample even when its run is longer (section 2); `sdmixplay` below repeats it.

Nothing in the file stores the record length, so it is a CLI parameter:
`--bpm` (default 180) at eight beats per record, i.e. two bars = 117 600 frames
(section 2.1), or `--step SECONDS` directly.
`--list` prints the resolved arrangement (record, time, track, lane, ID, file)
without opening a device; `--strict` fails on unresolvable samples instead of
skipping them. Cells below `MIN_SAMPLE_ID` (731) are dropped as padding, so the
stray bytes of section 7 neither become events nor stretch the song length. The
sample bank is `--pxd` (the folder holding `EJAY/PXD`), searched next to the
mix by default, and lookups ignore letter case because the index names its
folders in lower case while the install may not.

Requests are armed `LEAD_BYTES` (0.57 s) ahead of the play front, so a voice is
reused as soon as it frees up; if that front stops moving for
`STALL_SECONDS` (4 s) the player reports where it stopped, how many events are
left and the last mixer error, rather than waiting out the arrangement's
timeout. A stream the decoder cannot render is skipped (it is named on stderr)
instead of freezing playback.

### Independent player

[`../../work/src/sdmixplay.py`](../../work/src/sdmixplay.py) plays the same grid
without the engine. It reads the
container itself (header, 351-record grid, `0x0A08` trailer, padding rule,
index resolution and run collapsing as above), decodes each sample (the `tPxd`
codec of [`PXD_FORMAT.md`](PXD_FORMAT.md), plus RIFF/WAVE PCM), mixes the events
into mono
44.1 kHz blocks and writes those blocks to a `sounddevice.RawOutputStream`.
It imports neither `pxd32d5` nor `pxdsink`, so the play ring, player thread and
request queue of [`../../work/docs/PLAYBACK.md`](../../work/docs/PLAYBACK.md) are
not involved and the process cannot
stall on a voice that does not advance. A sample that cannot be decoded is
named on stderr and its events are dropped.

The record length is the same CLI parameter (`--bpm` 180 at `--beats` 8, or
`--step`), i.e. 117 600 frames per record (section 2.1). `--list` needs no
device; `--block FRAMES` sets the mix/write granularity (default 2048); `--gain`
scales the mix. A run longer than its sample repeats it to fill the run (every
bank sample is a whole number of bars - half a record - so this is exact). A run
shorter than its sample still plays the whole sample: mid-song samples are never
cut, even when another event starts on the same track. The only structural stop
is the start of the final record; a placement in that record is the ending and
rings out to its own length, so the mix runs past the last grid record. A sample
shorter than one record is a one-shot: it plays once, silent for the rest of its
run.
