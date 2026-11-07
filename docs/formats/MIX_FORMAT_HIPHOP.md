# Hiphop eJay `.MIX` File Format

Status: **grid layout, timing and sample-ID resolution understood; trailer field meanings mostly unknown.**

Derived from all 17 files in `disks/Hiphop_eJay/MIX/`, each exactly 12,692 bytes.
Cross-referenced with the `HIPHOP/EJAY/PXD` sample catalog, the `MAX`/`MIN` path
lists, and the `tPxd` headers of the base sample files.

All integers are **little-endian 16-bit words** unless another width is stated.

## 1. File layout

| Offset | Size | Content |
|--------|------|---------|
| 0 | 2 | Header word `0x0A08` (magic/version) |
| 2 | 351 x 32 = 11,232 | Arrangement grid: 351 blocks of 16 words |
| 11,234 | variable | Optional metadata block (section 1.1) |
| ~12,666 | variable | Trailer (section 1.2) |

`2 + 351 * 32 = 11,234`. All 17 files end at 12,692 bytes, leaving 458 bytes for
the metadata block plus trailer combined. [certain]

The header word is `0x0A08` in all 17 files. It matches the Dance eJay metadata
block tag (`0x0A08`) but is used here as the file-level magic, one higher than
Dance's header `0x0A06` and one higher than Rave's header `0x0A07`. The layout
must not be confused with Dance: Hiphop shares the grid shape but has its own
catalog and trailer. [certain]

### 1.1 Optional metadata block

The block starts at offset 11,234. Its layout matches the Dance eJay metadata
block (see [`MIX_FORMAT_DANCE.md`](MIX_FORMAT_DANCE.md) section 1.1):

| Offset from 11,234 | Size | Content |
|--------------------|------|---------|
| 0 | 2 | Tag `0x0A08` |
| 2 | 2 | Version: 1 |
| 4 | 2 | Creator length N |
| 6 | N | Creator string, ASCII |
| 6+N | 2 | Kit count K |
| 8+N | ... | K kit records |

All 17 files share the same metadata header:

| Offset | Value | Content |
|--------|-------|---------|
| 11,234 | `0x0A08` | Tag |
| 11,236 | `0x0001` | Version 1 |
| 11,238 | `0x0012` = 18 | Creator length |
| 11,240-11,257 | `"HipHop eJay 1.01\x00\x01"` | Creator string |

The creator string includes the `00 01` terminator inside its length, exactly
as the Dance 43-byte block does. [certain]

After the creator (offset 11,258 onward) the bytes are mostly zero. Two u16
values of `0x015E` (350) appear at offsets 11,258 and 11,962 in every file, with
zeros between them. Their meaning is unknown; they do not follow the Dance kit
record format (which would require non-zero kit records). [inferred]

No song title or tempo field has been observed in the metadata block. [likely]

**Reading rule:** a reader must accept a file of at least 11,234 bytes and ignore
everything from offset 11,234 onward. The grid is complete before the metadata
block. [certain]

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
- `0` is an empty cell. Any other value below `731` is **not a sample** (section 2.1); a reader must ignore it.
- A sample ID occupies one cell: one track for one bar. Longer placements are stored by repeating the ID across cells (section 6). There is no duration field in the grid.
- 351 blocks cover 702 bars. A file can therefore hold at most 702 bars, about 29:15 at the timing in section 3. [certain]

Block `n` starts at byte `2 + 32*n`. Bar `b` (0 or 1), track `t` (0..7) is the word at:

```text
2 + 32*n + 16*b + 2*t
```

Example, `START.MIX` block 0:

```text
0000 0000 0000 0000 0000 043d 0000 0000 | 0000 0000 0000 079f 0000 0000 0000 0000
```

Wait — that example is from Dance's `WELCOME.MIX`. Hiphop's `START.MIX` block 0 contains different values:

```text
0000 0000 0401 03fe 0000 0000 0671 0000 | 0000 0000 0000 03fe 0000 0000 0000 0672
```

Bar 1 has `0x0401` on track 3, `0x03FE` on track 4, and `0x0671` on track 7.
Bar 2 has `0x03FE` on track 4 and `0x0672` on track 8. All of them resolve to
samples in the Hiphop catalog (section 4).

### 2.1 Cells below 731

Small non-zero values sit in otherwise unused cells. They are not sample IDs: the base catalog starts at 731.Values observed in the grid below 731 are `1` through `15`. For example,
`START.MIX` has 25 such cells, all between byte offsets 5,630 and 6,856:
`0x0008` values in that region and `0x000C` values nearby. Any value below 731 must be dropped. [certain for the values; interpretation inferred]

## 3. TimingA bar is **110,250 frames** at 44.1 kHz. A block (two bars) is **220,500
frames**.

| Unit | Frames | Time at 44.1 kHz |
|------|--------|------------------|
| Bar | 110,250 | 2.5 s |
| Block (2 bars) | 220,500 | 5.0 s |
| Full 351-block grid | 77,395,500 | 29:15.0 |

110,250 frames is four beats at **96 BPM**. The files do not store a tempo;
96 BPM follows from the catalog's bar field and the decoded `tPxd` lengths.
[likely]

Evidence:
- The Hiphop `PXD` catalog's bar field (line 4 of each record) holds `1` (648
  records), `2` (650), `3` (14), `4` (28) and `6` (one record).
- Every one of the first 200 catalog records decodes to exactly
  `bars * 110,250` frames; the observed lengths are 110,250 (2.5 s), 220,500
  (5.0 s) and 441,000 (10.0 s). None is a multiple of 75,600, so the Dance bar
  length does not apply to Hiphop. [certain]
- Record 0 ("dirty slurpy", bar field 2) decodes to 220,500 frames = 5.0 s,
  exactly two bars. The `tPxd` header frame count stays authoritative for
  playback; the catalog's bar field is the placement length. [certain]

An earlier revision of this note assumed 140 BPM and a 75,600-frame bar
because the grid has Dance's shape. The catalog bar field and the decoded
sample lengths rule that out. Dance still fits 140 BPM: 198 of its first 200
`PXDDANCE` records decode to `bars * 75,600`.

## 4. Sample catalog and ID resolution

The catalog is `disks/Hiphop_eJay/HIPHOP/EJAY/PXD`, a plain-text file with CRLF line endings. It holds **1,341 records of 6 quoted lines each**:

```
"aa\h1bs001.pxd"   relative path under disks/Hiphop_eJay/HIPHOP/
""                  unused, empty in every record
"bass"              category word
"2"                 length in bars
"dirty slurpy"      sample name, part 1
"the one"           sample name, part 2 (often empty)
```

This is the same record shape as Dance eJay's `PXDDANCE` (six quoted fields, path stored directly). Unlike Dance's old `PXD.TXT`/`MAX.TXT` split, there is no separate key-to-path indirection: the path is in the record itself. [certain]

### 4.1 ID -> record

```text
base_record = sample_id - 731
```

The base catalog has 1,341 records, so the base ID range is **731 (0x02DB)
through 2071 (0x0817)**. Across the 17 mixes, all observed sample IDs fall in
this range; no high-ID banks (3400+) are used. [certain]

All 1,341 catalog paths resolve to existing `.pxd` files under
`disks/Hiphop_eJay/HIPHOP/` (folders `AA` through `BR`). [certain]

### 4.2 Record -> file path

The path is field 0 of the PXD record, already relative to the `HIPHOP` folder.
No `MAX` indirection is needed for base IDs. The separate `MAX` file (1,381 paths)
and `MIN` file (743 paths) exist on the disc but are not referenced by the MIX
grid; their role is unknown. [inferred]

Worked examples:

| ID | ID dec | PXD record | Path | Bars | Name |
|----|--------|------------|------|------|------|
| `0x02DB` | 731 | 0 | `aa\h1bs001.pxd` | 2 | dirty slurpy / the one |
| `0x0307` | 775 | 44 | `br\h1bs045.pxd` | 2 | goldfinger / the bow 1 |
| `0x03FE` | 1022 | 291 | `bf\h1ex018.pxd` | 1 | hard / breath |
| `0x0401` | 1025 | 294 | `bh\h1ex021.pxd` | 1 | help / me |
| `0x0671` | 1649 | 918 | `bh\h1rp056.pxd` | 1 | hiphp / jam |
| `0x0817` | 2071 | 1340 | `aq\h1zzm04.pxd` | 4 | MCM / http://www.eJay.com |

## 5. Trailer

The file ends with a variable trailer after the metadata block. The last 28 bytes
(12,664-12,691) of `START.MIX`:

```text
01 00 11 2B 00 00 00 00 08 00 00 00 00 00 00 00 00 00 00 00 01 00 02 00
```

As u16 LE words from offset 12,666:

| Offset | Value | Content |
|--------|-------|---------|
| 12,666 | `0x0001` | Constant across all 17 files |
| 12,668 | varies | `0x2B11` (11,025) for most files; `0x340A` (13,322) for `DUTCH`, `0x4D29` (19,753) for `RAGE`, `0x2EA8` (11,944) for `SHYGIRL`, `0x409A` (16,538) for `UPDOWN`, `0x5622` (22,050) for `VIBE` |
| 12,670 | `0x0000` | Constant |
| 12,672 | `0x0000` | Constant |
| 12,674 | `0x0008` | Constant across all 17 files |
| 12,676-12,687 | varies | Mostly zero; occasional non-zero words |
| 12,688 | varies | `0x0001` or `0x0002` |
| 12,690 | varies | `0x0001` or `0x0002` |

For `MYSELF.MIX` and `XDAYS.MIX`, the trailer ends at offset 12,674 (value `0x0008`); the remaining bytes to EOF are zero.

The value at offset 12,668 does not obviously correlate with grid usage, length, or sample count. Its meaning is unknown: it could be a mix identifier, a checksum, or a writer option. The `0x0008` at 12,674 matches the `0x0008` seen in Dance's metadata block tails (possibly a track count). [inferred]

The trailer format is **unverified** beyond the observed byte layout; no engine behaviour has been confirmed against it.

## 6. Placement semantics

The grid stores **start cells**, not durations. A sample ID repeated in consecutive cells is one placement spanning those bars; samples are not cut at the end of a non-repeating run. This matches the Dance format behaviour ([`MIX_FORMAT_DANCE.md`](MIX_FORMAT_DANCE.md) section 6) but has not been confirmed against the Hiphop player. [likely]

Catalog bars give the intended length: `bars * 110,250` frames at 44.1 kHz, which matches every decoded length in the first 200 records. A player should still use the decoded frame count for playback and the cell run for the placement end.

## 7. Comparison with existing formats

| Item | Hiphop eJay | Dance eJay | Rave eJay | Techno eJay |
|------|-------------|------------|-----------|-------------|
| Magic | `0x0A08` | `0x0A06` | `0x0A07` | `0x0889` |
| File size | 12,692 (all 17) | 11,234 + metadata | 11,276 | ~2,144 (variable) |
| Grid | 351 blocks x 32 bytes | 351 blocks x 32 bytes | 351 records x 32 bytes | compact pairs + event table |
| Grid start | offset 2 | offset 2 | offset 2 | after text block |
| Grid end | offset 11,234 | offset 11,234 | trailer tag offset | before trailer |
| Metadata block | yes (0x0A08 tag) | optional (0x0A08 tag) | trailer (0x0A08 tag) | linked-list catalog |
| Trailer | yes, variable | optional tail | small values | `"Techno eJay"` + catalog |
| Sample IDs | `id - 731` | `id - 731` | `id - 731` | `RAVE20.INF` id |
| Catalog | `EJAY/PXD` (6-line) | `PXD.TXT`/`PXDDANCE` | `EJAY/PXD` (6-line) | `RAVE20.INF` |
| Base ID range | 731-2071 (1,341) | 731-2082 (1,352) | 731-1879 (1,149) | varies |
| Path in record | yes | PXDDANCE: yes / PXD.TXT: no | yes | n/a (INF) |
| High-ID banks | none | 3400-5049 (dmkit1-3) | none | kit ranges 3400-7199 |
| Timing | 110,250 frames/bar | 75,600 frames/bar | 58,800 frames/bar | 75,600 frames/bar |
| BPM | 96 (implied) | 140 (implied) | 180 (implied) | 140 (header word 4) |
| Tracks | 8 | 8 | 8 (2 lanes) | 16 (+1 empty) |
| Output | mono (inferred) | mono | mono | stereo |

Hiphop's grid is structurally identical to Dance's: same magic word family (`0x0A08` vs `0x0A06`), same 351-block grid, same two-bar blocks, same 8-track layout, same 731 ID offset. The differences are: Hiphop's header is `0x0A08` instead of `0x0A06`; Hiphop always has a metadata block (all 17 files, version 1, creator "HipHop eJay 1.01"); Hiphop has a trailer that Dance lacks; Hiphop uses a single `PXD` catalog (like Dance's `PXDDANCE`) without the old `PXD.TXT`/`MAX.TXT` split or high-ID banks; and Hiphop's bar is 110,250 frames (96 BPM) where Dance's is 75,600 (140 BPM). [certain for structure; inferred for output and trailer]

## 8. Reference parser (Python)

```python
import struct

ID_BASE = 731
GRID_BLOCKS = 351
GRID_END = 2 + GRID_BLOCKS * 32
META_OFFSET = GRID_END
HEADER_MAGIC = 0x0A08


def read_mix(path):
    data = open(path, "rb").read()
    header = struct.unpack_from("<H", data, 0)[0]
    if header != HEADER_MAGIC:
        raise ValueError(f"bad Hiphop mix header: 0x{header:04X}")
    if len(data) < GRID_END:
        raise ValueError(f"Hiphop mix too short: {len(data)} bytes")
    blocks = [
        struct.unpack_from("<16H", data, 2 + 32 * i)
        for i in range(GRID_BLOCKS)
    ]
    return blocks


def read_catalog(pxd_path):
    text = open(pxd_path, encoding="latin-1").read()
    lines = [line.strip()[1:-1] for line in text.splitlines()
             if line.strip().startswith('"')]
    records = [lines[6 * i:6 * i + 6] for i in range(len(lines) // 6)]
    return records


def sample_for(sample_id, records):
    record = records[sample_id - ID_BASE]
    return {
        "id": sample_id,
        "path": record[0].strip('"'),
        "bars": int(record[3]),
        "name": " ".join(x for x in record[4:] if x),
    }


def events(blocks, records):
    for block_index, block in enumerate(blocks):
        for bar in (0, 1):
            for track in range(8):
                sample_id = block[8 * bar + track]
                if sample_id < ID_BASE:
                    continue
                yield {
                    "block": block_index,
                    "bar": 2 * block_index + bar,
                    "track": track + 1,
                    **sample_for(sample_id, records),
                }
```

`read_mix()` accepts any length at or above `GRID_END`; the metadata block and trailer are deliberately ignored. `events()` drops every value below 731. The catalog is CRLF-terminated, so `read_catalog()` strips each line before removing the surrounding quotes; `split("\n")` alone leaves a `\r` on every field and breaks `int()`.

## 9. Open questions

1. What do the two `0x015E` (350) values at offsets 11,258 and 11,962 in the metadata region represent?
2. What is the meaning of the trailer fields, especially the varying u16 at offset 12,668 (11,025 / 13,322 / 19,753 / 11,944 / 16,538 / 22,050 across files)?
3. What are the `MAX` (1,381 paths) and `MIN` (743 paths) files used for, given that PXD records carry their paths directly?
4. Are the sub-731 values in the grid (1, 4, 8, 12) the same phenomenon as Dance's sub-731 cells?
5. Does the Hiphop player repeat a sample whose run is longer than its decoded length, or truncate it at the end of the run?
6. Is output mono or stereo? All samples are decoded to mono; no panning data is stored in the grid.
7. Is 96 BPM confirmed by the engine? The catalog bar field and the decoded
   lengths fit 110,250 frames exactly, but no engine constant has been
   located, and the trailer fields are still unverified.
