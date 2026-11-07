# Dance eJay `.MIX` File Format

Status: **grid, block timing, sample resolution, the optional metadata block and
both catalog generations are understood; the numeric category ids, a few
sub-731 cells and samples from add-on banks that are not on the disc remain
open.**

Derived from the 20 files in `disks/Dance_eJay/MIX/` (16) and
`disks/Dance_eJay_old/MIX/` (4). The four names that appear in both folders
(`FREAK`, `LOVE`, `START`, `WELCOME`) are byte-identical, so the earlier notes
still describe them. Cross-referenced with both catalog generations and with
the `tPxd` headers of the base sample files.

All integers are **little-endian 16-bit words** unless another width is stated.

## 1. File layout

| Offset | Size | Content |
|--------|------|---------|
| 0 | 2 | Header word `0x0A06` (magic/version) |
| 2 | 351 x 32 = 11,232 | Arrangement grid: 351 blocks of 16 words |
| 11,234 | 0, 43, 99 or 179 | Optional metadata block (section 1.1) |

`2 + 351 * 32 = 11,234`. Five of the 16 files in
`disks/Dance_eJay/MIX/` end exactly there (`FREAK`, `LOVE`, `START`,
`WELCOME`, `XPIPE`); the other eleven carry a metadata block of 43, 99 or
179 bytes. [certain]

The header word is `0x0A06` in all 20 files. It is one lower than the Rave
eJay header `0x0A07`, but the two layouts must not be mixed: a Dance block has
a different meaning (section 2) and a different duration (section 3).
[certain]

### 1.1 Optional metadata block

The block starts at offset 11,234. Its size depends on the writer:

| Offset from 11,234 | Size | Content |
|--------------------|------|---------|
| 0 | 2 | Tag `0x0A08`, or `0x0A06` in the 99-byte variant |
| 2 | 2 | Version: 1 or 2 |
| 4 | 2 | Creator length N |
| 6 | N | Creator string, ASCII |
| 6+N | 2 | Kit count K |
| 8+N | 6 x K plus names | K kit records |

A kit record is `u16 first_id`, `u16 last_id`, `u16 name_length`, then
`name_length` ASCII bytes. The creator string normally ends with `00 01` inside
the length; the 99-byte variant stores exactly the 17-byte text with no
terminator. [certain for the observed bytes]

| Block | Files | Tag | Ver | Creator | Kits |
|-------|-------|-----|-----|---------|------|
| 43 | `MCXTREME`, `ORGANICS`, `SOFTVOX`, `THEFLOW`, `WETDANCE`, `X_PERM` | `0x0A08` | 1 | `Dance eJay 1.01` | none |
| 99 | `DRUMSYNT`, `RAPSVOIC`, `START_RE` | `0x0A06` | 2 | `DanceMachine 1.05` | 3400-3899, 3900-4500 |
| 179 | `DREAM`, `SPACE` | `0x0A08` | 2 | `gung DanceMachine 1.05` | 3400-3899, 3900-4499, 4500-5199 |

The bytes after the kit list differ by variant:

- 43-byte block: `08 00`, twelve `00` bytes, then `01 00 02 00` (18 bytes).
- 179-byte block: `00 00`, then the same 18 bytes (20 bytes).
- 99-byte block: `00 00` only.

The 18-byte tail, and the zero kit count before it, are byte-identical to the
end of a Rave eJay `0x0A08` trailer after its creator name; see
[`MIX_FORMAT_RAVE.md`](MIX_FORMAT_RAVE.md) section 4. [certain for the bytes;
the fields are probably writer options. Interpretation inferred]

No song title or tempo field has been observed in any block. The creator
string, version and kit list look like a record of the environment that saved
the mix. [likely]

**Reading rule:** a reader must accept a file of at least 11,234 bytes and
ignore everything from offset 11,234 onward. The grid is complete before the
metadata block. [certain]

## 2. Arrangement grid

A **block** is 32 bytes, or 16 words. It holds **two consecutive bars** of
**eight tracks**:

```text
word:   0  1  2  3  4  5  6  7 | 8  9 10 11 12 13 14 15
        T1 T2 T3 T4 T5 T6 T7 T8| T1 T2 T3 T4 T5 T6 T7 T8
        '---- first bar ------ ' '---- second bar ----- '
```

- Word `0..7` is bar 1, tracks 1..8, left to right.
- Word `8..15` is bar 2, the same eight tracks.
- `0` is an empty cell. Any other value below `731` is **not a sample**
  (section 2.1); a reader must ignore it.
- A sample ID occupies one cell: one track for one bar. Longer placements are
  stored by repeating the ID across cells (section 6). There is no duration
  field in the grid.
- 351 blocks cover 702 bars. A file can therefore hold at most 702 bars, about
  20:03 at the timing in section 3.

Block `n` starts at byte `2 + 32*n`. Bar `b` (0 or 1), track `t` (0..7) is the
word at:

```text
2 + 32*n + 16*b + 2*t
```

Example, `WELCOME.MIX` block 0:

```text
0000 0000 0000 0000 0000 043d 0000 0000 | 0000 0000 0000 079f 0000 0000 0000 0000
```

Bar 1 has `0x043D` on track 6; bar 2 has `0x079F` on track 4. Both resolve to
"Circles in the Sky ****" and "Welcome in the house" respectively (section 4).

### 2.1 Cells below 731

Small non-zero values sit in otherwise unused cells. They are not sample IDs:
the base catalog starts at 731.

- `FREAK.MIX` has the values `2`, `3` and `8` in blocks 179-207.
- The same phenomenon appears in twelve of the sixteen mixes, with the values
  `1`, `2`, `3`, `4`, `8` and `9`; for example `MCXTREME.MIX` uses `1` and `4`,
  and `SPACE.MIX` uses `8` and `9`.
- The cells carry no path or duration and are not part of the music.

Any value below 731 must be dropped. Without that filter `FREAK.MIX` appears to
run to block 207 instead of block 35. [certain for the values; interpretation
of their origin is inferred]

## 3. Timing

A bar is **75,600 frames** at 44.1 kHz. A block (two bars) is **151,200
frames**.

| Unit | Frames | Time at 44.1 kHz |
|------|--------|------------------|
| Bar | 75,600 | 1.7142857 s |
| Block (2 bars) | 151,200 | 3.4285714 s |
| Full 351-block grid | 53,071,200 | 20:03.4 |

75,600 frames is four beats at **140 BPM**. The files do not store a tempo; 140
BPM is the value implied by the sample lengths and by the placement spacing.
[likely]

Evidence:

- Decoded sample lengths cluster at a 75,600-frame bar: 581 samples are exactly
  2 bars, 274 are 1 bar, 308 are 4 bars, 73 are 8 bars, and so on; four are
  half a bar (37,800 frames). The bar field in the old `PXD.TXT` has a similar
  distribution (592 / 312 / 309 / 73 for 2 / 1 / 4 / 8 bars).
- Across all 1,352 base catalog entries, **1,298** have
  `decoded_frames == bars * 75,600` exactly. Of the remaining 54, most are a
  few frames over a bar boundary (for example 75,640 instead of 75,600); a few
  are genuinely longer or shorter than the catalog field says. The frame count
  in the `tPxd` header is authoritative.
- Eight-bar samples are placed four blocks apart, which is eight bars:
  `0x03E0` "Sweeper *** L" (604,800 frames = 8 bars) at blocks 45, 49 and 53
  of `WELCOME.MIX`; `0x0637` "Morse 01 Complete Message" (604,800 frames = 8
  bars) at blocks 16, 20 and 24 of `FREAK.MIX`.
- The shortest catalog lengths are 37,800 frames (half a bar) and 75,600 frames
  (one bar). A one-bar cell is therefore the natural grid quantum.

Do not reuse Rave eJay's 117,600-frame record here. That is two 58,800-frame
bars at 180 BPM; Dance is 75,600 frames per bar at 140 BPM.

## 4. Sample catalog and ID resolution

The two discs use different catalog generations. Both describe the same 1,352
base samples; only the file names and the record shape changed.

| Disc folder | Index | Paths | Records |
|-------------|-------|-------|---------|
| `disks/Dance_eJay_old/DANCE/DMACHINE/` | `PXD.TXT` | `MAX.TXT` | 1,352 records of 4 lines, after 18 header values |
| `disks/Dance_eJay/DANCE/EJAY/` | `PXDDANCE` | `MAX` | 1,352 records of 6 lines |

The old `MIN.TXT` holds 897 quoted paths; the new `MIN` also holds 897. They
are a subset and are not needed for `.MIX` resolution.

All files use CRLF line endings. The new `MAX` has 2,845 unquoted paths, one per
line. Its first 1,352 entries are identical to the old `MAX.TXT`, in the same
order. The remaining entries belong to three add-on banks (section 4.3).

### 4.1 Old catalog: `PXD.TXT`

A `PXD.TXT` record has four quoted fields:

```text
"917984"       32-bit catalog key, decimal
"2"            length in bars
"Grp. 1"       sample name, part 1
"Vers1"        sample name, part 2 (often empty)
```

The 18 header values are nine `(start, count)` pairs. The counts sum to 1,352,
and each pair covers one contiguous block of records that shares a key high
word and one category word in `PXDDANCE`:

| Slot | Start | Count | Key high word | Category |
|------|-------|-------|---------------|----------|
| 0 | 0 | 126 | 14 | `loop` |
| 1 | 126 | 114 | 18 | `bass` |
| 2 | 240 | 115 | 24 | `layer` |
| 3 | 355 | 100 | 8 | `voice` |
| 4 | 455 | 81 | 5 | `effect` |
| 5 | 536 | 300 | 20 | `drum` |
| 6 | 836 | 229 | 16 | `sequence` |
| 7 | 1,065 | 127 | 17 | `xtra` |
| 8 | 1,192 | 160 | 15 | `rap` |

The slot starts are cumulative: `0, 126, 240, 355, 455, 536, 836, 1,065,
1,192`. The header is a per-group offset table and the group word selects the
category. [certain for the values, the grouping and the category counts; why
these nine numbers stand for these categories is unverified]

### 4.2 New catalog: `PXDDANCE`

A `PXDDANCE` record has six quoted fields:

```text
"bm\asjo.pxd"  relative path
""             unused, empty in every record
"loop"         category word
"2"            length in bars
"Grp. 1"       sample name, part 1
"Vers1"        sample name, part 2 (often empty)
```

All 1,352 records match the old `PXD.TXT` records exactly in path, bar count
and name. A reader can therefore use either catalog for base IDs. [certain]

### 4.3 ID -> record

```text
base_record = sample_id - 731
```

The base catalog has 1,352 records, so the base ID range is **731 (0x02DB)
through 2082 (0x0822)**. Across the 16 mixes, 318 distinct base IDs are used,
from 731 to 2066; every one resolves. [certain]

The new catalog adds three high-ID banks. A high ID selects a row of the new
`MAX` directly; it does not index `PXDDANCE`:

| ID range | Bank | `MAX` row | Rows | Nominal trailer range |
|----------|------|-----------|------|-----------------------|
| 3400-3822 | `dmkit1` | `1352 + (id - 3400)` | 423 | 3400-3899 |
| 3900-4419 | `dmkit2` | `1775 + (id - 3900)` | 520 | 3900-4499 or 3900-4500 |
| 4500-5049 | `dmkit3` | `2295 + (id - 4500)` | 550 | 4500-5199 |

The trailer advertises a wider range than `MAX` provides. IDs above the last
usable row are out of range even though the trailer names them. All high IDs in
the 16 mixes fall inside the rows above: 264 distinct IDs, from 3407 to 5013.
[certain for the mapping; the base/step choice is unexplained]

The `dmkit1`, `dmkit2` and `dmkit3` folders are not present on either disc, so
the high-ID samples cannot currently be decoded. Eight of the 16 mixes use
them (`DREAM`, `DRUMSYNT`, `RAPSVOIC`, `SOFTVOX`, `SPACE`, `START_RE`,
`THEFLOW`, `X_PERM`).

The optional metadata block (§1.1) names the kit ranges each mix references,
which confirms the bank-to-folder mapping:

| Mix | Metadata block | Kit range | Folder |
|-----|---------------|-----------|--------|
| `MCXTREME`, `ORGANICS`, `SOFTVOX`, `THEFLOW`, `WETDANCE`, `X_PERM` | 43-byte | none | — |
| `DRUMSYNT`, `RAPSVOIC`, `START_RE` | 99-byte | 3400–3899, 3900–4500 | dmkit1, dmkit2 |
| `DREAM`, `SPACE` | 179-byte | 3400–3899, 3900–4499, 4500–5199 | dmkit1, dmkit2, dmkit3 |

Kit names observed: `DanceMachine Sample-Kit Vol. 1` (3400–3899),
`DanceMachine Sample-Kit Vol. 2` (3900–4500), and `gung -SAMPLE BOX-` kits
for the third bank (`[Raps && Vocals]`, `[Drams && Synthies]`, `[Space Sounds]`).

### 4.3.1 Missing sample warning

The player reports every high-ID sample it cannot resolve. The warning now
includes the full expected path so the missing file is obvious:

```
player: skipped sample 0xDFF (C:\repo\mine\eJay\disks\Dance_eJay\DANCE\dmkit1\05\rob302.pxd): not found
```

Base samples (731–2082) are all present and decode normally; only the
`dmkit1`..`dmkit3` high-ID samples are missing. `--strict` escalates these
warnings into a `SampleError`.

### 4.4 Record -> file path

The old `PXD.TXT` key is **not** the sample ID, and `MAX.TXT` is **not** in the
same order as `PXD.TXT`. The key links the two lists:

```text
key          = (group << 16) | (path_index + 3)
path_index   = (key & 0xFFFF) - 3
path         = MAX.TXT[path_index]
```

- `group` is one of nine category ids. The nine values select `loop`, `bass`,
  `layer`, `voice`, `effect`, `drum`, `sequence`, `xtra` and `rap`
  (section 4.1). [certain]
- `path_index` is 0..1351 and is unique for all 1,352 records. [certain]
- Using `MAX.TXT[sample_id - 731]` is wrong: it gives a different file for most
  samples. The key is required. [certain]

Worked examples:

| ID | ID dec | PXD record | Key | Path index | Path | Bars | Name |
|----|--------|------------|-----|------------|------|------|------|
| `0x02DB` | 731 | 0 | 917984 | 477 | `bm\asjo.pxd` | 2 | Grp. 1 Vers1 |
| `0x02F6` | 758 | 27 | 918374 | 867 | `bw\bhjo.pxd` | 2 | Grp. 3 Vers1 |
| `0x035F` | 863 | 132 | 1180899 | 1248 | `aj\bwas.pxd` | 4 | High Whobble L |
| `0x043D` | 1085 | 354 | 1574175 | 1308 | `ak\byiy.pxd` | 8 | Circles in the Sky **** |
| `0x0637` | 1591 | 860 | 1049865 | 1286 | `aj\bxmq.pxd` | 8 | Morse 01 Complete Message |
| `0x079F` | 1951 | 1220 | 984388 | 1345 | `al\bztp.pxd` | 8 | Welcome in the house |
| `0x0812` | 2066 | 1335 | 983715 | 672 | `br\azwp.pxd` | 2 | Hey Ha! 02 |

Verification:

- For 1,250 of 1,352 records, the `PXD.TXT` name is an exact match for the
  two-line comment in the linked sample file; 1,344 match at a similarity
  above 0.8.
- The linked file's frame count equals `bars * 75,600` for 1,298 records
  (section 3).
- Every path index is distinct and inside `MAX.TXT`.

The sample header is the `tPxd` shape documented in
[`PXD_FORMAT.md`](PXD_FORMAT.md): a one-byte comment length at offset 4, the
comment, the `00 54` marker, then a 32-bit frame count. For Dance samples the
comment is usually two lines (name and part) rather than Rave's six-line
library record.

```text
frame_count_offset = 4 + comment_length + 2
```

## 5. The mixes

Counts ignore cells below 731. "Used blocks" counts blocks that hold at least
one base or high ID; "last used" is the highest such block index.

| File | Size | Metadata | Used blocks | Last used | Distinct IDs | Sample cells |
|------|------|----------|-------------|-----------|--------------|--------------|
| `DREAM.MIX` | 11,413 | 179 | 46 | 50 | 56 | 178 |
| `DRUMSYNT.MIX` | 11,333 | 99 | 47 | 46 | 55 | 176 |
| `FREAK.MIX` | 11,234 | 0 | 36 | 35 | 26 | 227 |
| `LOVE.MIX` | 11,234 | 0 | 31 | 34 | 29 | 126 |
| `MCXTREME.MIX` | 11,277 | 43 | 43 | 42 | 36 | 258 |
| `ORGANICS.MIX` | 11,277 | 43 | 38 | 37 | 20 | 214 |
| `RAPSVOIC.MIX` | 11,333 | 99 | 46 | 50 | 56 | 178 |
| `SOFTVOX.MIX` | 11,277 | 43 | 54 | 53 | 29 | 262 |
| `SPACE.MIX` | 11,413 | 179 | 71 | 94 | 101 | 281 |
| `START.MIX` | 11,234 | 0 | 42 | 41 | 48 | 189 |
| `START_RE.MIX` | 11,333 | 99 | 99 | 98 | 82 | 323 |
| `THEFLOW.MIX` | 11,277 | 43 | 40 | 41 | 38 | 213 |
| `WELCOME.MIX` | 11,234 | 0 | 88 | 94 | 139 | 389 |
| `WETDANCE.MIX` | 11,277 | 43 | 37 | 36 | 33 | 211 |
| `X_PERM.MIX` | 11,277 | 43 | 114 | 113 | 78 | 472 |
| `XPIPE.MIX` | 11,234 | 0 | 42 | 41 | 48 | 189 |

Notable relationships:

- `START.MIX` and `XPIPE.MIX` are byte-identical in the new folder; the old
  `START.MIX` is the same file.
- `DREAM.MIX` and `RAPSVOIC.MIX` have identical grids but different metadata
  blocks (179 bytes for `DREAM`, 99 for `RAPSVOIC`), so they are not
  byte-identical.
- The four original files are continuous or nearly so: `FREAK.MIX` for blocks
  0-35, `START.MIX` for 0-41, `LOVE.MIX` at 0, 2-12, 14-22, 24-32 and 34,
  `WELCOME.MIX` at 0, 4-86, 88-90 and 94.
- `FREAK.MIX` also holds the sub-731 values in blocks 179-207 (section 2.1).

The filename is the only song identifier. There is no title field in the grid
or the metadata block.

## 6. Placement semantics

The grid stores **start cells**, not durations. A sample ID repeated in
consecutive cells is one placement spanning those bars; samples are not cut at
the end of a non-repeating run. This is the behaviour of the Rave format and
the natural reading of the repeated runs here, but it has not been confirmed
against the Dance player. [likely]

Catalog bars give the intended length. The sample's actual frame count can
differ by a few frames, and a few entries are longer or shorter than the
catalog says (section 3). A player should therefore use the decoded frame count
for playback and the cell run for the placement end.

## 7. Reference parser

```python
import struct

ID_BASE = 731
BAR_FRAMES = 75600
GRID_BLOCKS = 351
GRID_END = 2 + GRID_BLOCKS * 32
BANKS = ((3400, 1352, 423), (3900, 1775, 520), (4500, 2295, 550))


def quoted_lines(path):
    text = open(path, encoding="latin-1").read().replace("\r\n", "\n")
    return [line[1:-1] for line in text.split("\n") if line.startswith('"')]


def read_old_catalog(dm_dir):
    lines = quoted_lines(dm_dir + "/PXD.TXT")
    records = [
        lines[18 + 4 * i:22 + 4 * i]
        for i in range((len(lines) - 18) // 4)
    ]
    paths = quoted_lines(dm_dir + "/MAX.TXT")
    return records, paths


def read_new_catalog(ejay_dir):
    lines = quoted_lines(ejay_dir + "/PXDDANCE")
    records = [lines[6 * i:6 * i + 6] for i in range(len(lines) // 6)]
    text = open(ejay_dir + "/MAX", encoding="latin-1").read()
    paths = [line for line in text.splitlines() if line]
    return records, paths


def read_mix(path):
    data = open(path, "rb").read()
    header = struct.unpack_from("<H", data, 0)[0]
    assert header == 0x0A06
    assert len(data) >= GRID_END
    blocks = [
        struct.unpack_from("<16H", data, 2 + 32 * i)
        for i in range(GRID_BLOCKS)
    ]
    return blocks


def high_path(sample_id, paths):
    for base, start, count in BANKS:
        if base <= sample_id < base + count:
            return paths[start + sample_id - base]
    return None


def sample_for(sample_id, records, paths):
    record = records[sample_id - ID_BASE]
    if len(record) == 6:                    # PXDDANCE: path is field 0
        return {
            "id": sample_id,
            "path": record[0],
            "bars": int(record[3]),
            "name": " ".join(x for x in record[4:] if x),
        }
    path_index = (int(record[0]) & 0xFFFF) - 3
    return {
        "id": sample_id,
        "path": paths[path_index],
        "bars": int(record[1]),
        "name": " ".join(x for x in record[2:] if x),
    }


def events(blocks, records, paths):
    for block_index, block in enumerate(blocks):
        for bar in (0, 1):
            for track in range(8):
                sample_id = block[8 * bar + track]
                if sample_id < ID_BASE:
                    continue
                if sample_id >= 3400:
                    path = high_path(sample_id, paths)
                    yield {
                        "block": block_index,
                        "bar": 2 * block_index + bar,
                        "track": track + 1,
                        "id": sample_id,
                        "path": path,
                    }
                    continue
                yield {
                    "block": block_index,
                    "bar": 2 * block_index + bar,
                    "track": track + 1,
                    **sample_for(sample_id, records, paths),
                }
```

`read_mix()` accepts any length at or above `GRID_END`; the metadata block is
deliberately ignored. `events()` drops every value below 731. Do not use
`MAX.TXT` directly by ID: resolve the old `PXD.TXT` record first, then use the
key (section 4.4). For the new catalog, use `PXDDANCE` for base IDs and the
bank formula for high IDs (section 4.3).

## 8. Player support

`player` registers this container as the `dance` plugin (magic `0x0A06`). It
accepts any file of at least 11,234 bytes and ignores the optional metadata
block (section 1.1). It reads both catalog generations:

* the old `DMACHINE/PXD.TXT` -> key -> `MAX.TXT` chain (section 4.2);
* the new `EJAY/PXDDANCE` six-line records, whose path is stored directly,
  plus the 2,845-row `MAX` for high IDs 3400-3822, 3900-4419 and 4500-5049
  (section 4.3).

`--pxd` points at the `DANCE` folder for either disc; the plugin looks for
`DMACHINE` or `EJAY` inside it. Without the option it searches next to the
mix, which covers the shipped `disks/Dance_eJay/MIX` and
`disks/Dance_eJay_old/MIX` layouts.

```bash
python -m player "disks/Dance_eJay/MIX/DREAM.MIX" --list
python -m player "disks/Dance_eJay_old/MIX/FREAK.MIX" --list
python -m player "disks/Dance_eJay/MIX/FREAK.MIX" \
    --pxd "disks/Dance_eJay/DANCE" --list
```

All 20 files on the two discs load. The eight new mixes that use high IDs
(`DREAM`, `DRUMSYNT`, `RAPSVOIC`, `SOFTVOX`, `SPACE`, `START_RE`, `THEFLOW`
and `X_PERM`) resolve those IDs through the `MAX` banks, but the referenced
`dmkit1`..`dmkit3` sample files are not present on either disc or in the ISOs.
Their high-ID samples are skipped with a warning that now includes the full
expected path while the base samples still play; `--strict` turns those
warnings into an error. See §4.3.1.

The four old-catalog mixes were tested with `--pxd` and produced no sample
warning. Their rendered lengths were:

| File | Frames | Time |
|------|--------|------|
| `FREAK.MIX` | 5,367,600 | 2:01.7 |
| `LOVE.MIX` | 5,292,000 | 2:00.0 |
| `START.MIX` | 6,804,000 | 2:34.3 |
| `WELCOME.MIX` | 14,364,000 | 5:25.7 |

The event rule is per track: collapse repeated ids into one run, loop a run
that is longer than its decoded sample when the sample is at least one bar,
otherwise play the whole sample. A new placement on the same track cuts the
previous sound at its start; the last sound on each track rings out. This is
an implementation of section 6, not a new file-format fact. [implementation]

## 9. Open questions

1. Why the nine category ids have the values 5, 8, 14-18, 20 and 24.
2. The origin of the sub-731 values in `FREAK.MIX` and the other eleven files.
3. Why base IDs start at 731 and why the catalog holds exactly 1,352 records.
4. Why the add-on banks start at 3400, 3900 and 4500 with the observed
   capacities, and where their `.pxd` files were shipped.
5. Whether the Dance player repeats a sample whose run is longer than its
   decoded length, or truncates it at the end of the run.
6. The 54 catalog entries whose bar field does not exactly match the decoded
   frames.
