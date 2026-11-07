# RAVE20.INF Format

`disks/Techno_eJay/EJAY/PXD/RAVE20.INF` is an index file for `disks/Techno_eJay/EJAY/PXD/RAVE20`, a ~409 MB binary archive containing PXD (Rave eJay) audio samples.

## Verification

- `.inf` total lines: **48,194**
- Header lines before `[SAMPLES]`: **14** (lines 1–13; line 3 is `#TRUE#`, lines 4–13 blank `""`)
- `[SAMPLES]` marker: line 14 — marks the start of PXD records; everything before it is unknown header
- Remaining lines after `[SAMPLES]`: **48,180**
- Record size: **12 lines** each
- Entry count: **48,180 / 12 = 4,015 entries** (no remainder)
- Cross-validated: `RAVE20` binary contains exactly **4,015 `tPxD` magic records**, matching the `.inf` entry count
- Record start offsets in `.inf` match `tPxD` record positions in the binary
- Gaps between consecutive binary records equal the `.inf` size field per entry
- All 4,015 `.inf` entries have valid `tPxD` records at their specified offsets — zero mismatches

## Structure

```
Lines 1-13: unknown header (line 3 = "#TRUE#", lines 4-13 = blank "")
Line 14:    [SAMPLES]   <-- marks start of PXD records
Lines 15+:  entries, 12 lines each
```

### Entry layout (12 lines)

| Line | Field | Example | Meaning |
|------|-------|---------|---------|
| 1 | size | `14546` | sample size / total record length |
| 2 | unknown | `6` | constant `6` |
| 3 | name | `"T1FX544"` | sample name |
| 4 | start_offset | `0` | byte offset into RAVE20 |
| 5 | sample_size | `37930` | PXD data size |
| 6 | str1 | `"jam-"` | category prefix |
| 7 | str2 | `"mer8"` | category suffix |
| 8 | num1 | `1` | numeric flag |
| 9 | num2 | `7` | numeric flag |
| 10 | str3 | `""` | empty string |
| 11 | num3 | `0` | numeric flag |
| 12 | str4 | `""` | empty string |

### Example entry

```
14546
6
"T1FX544"
0
37930
"jam-"
"mer8"
1
7
""
0
""
```

## Binary cross-reference

Each `.inf` entry corresponds to a `tPxD` record in `RAVE20`:

```
tPxD5jam-\r\nmer8\r\nRave eJay\r\n2\r\nEffect\r\n75600\r\n01\r\n270799...
```

| `.inf` line | Binary field | Match |
|-------------|--------------|-------|
| 3 (name) | sample name (implied) | implied by comment line 1 |
| 4 (start_offset) | record start offset | exact |
| 5 (sample_size) | record length / gap to next record | exact |
| 6 (str1) | comment line 1 | exact |
| 7 (str2) | comment line 2 | exact |

- `tPxD` magic at record start
- Record start offsets and sizes match `.inf` fields 4 and 5

## PXD container vs PXD_FORMAT.md

All 4,015 RAVE20 PXD records share the same low-level `tPxD` container structure described in `PXD_FORMAT.md`, but use a different comment format:

| Aspect | PXD_FORMAT.md (EJAY\PXD bank) | RAVE20 bank |
|--------|------------------------------|-------------|
| Magic | `tPxD` | ✓ `tPxD` |
| len byte | u8 at offset 4 | ✓ present |
| Comment | NUL-terminated ASCII | ✓ NUL-terminated |
| Tag at 4+len | `0x00 0x54` | ✓ all 4,015 |
| Frame count at 4+len+2 | i32 LE | ✓ present |
| Trailing u16 at 4+len+6 | mostly 0, some non-zero | ✓ 769/4,015 non-zero |
| Data at 4+len+8 | ADPCM/codebook stream | ✓ present |
| Comment line count | **6 lines** | **8 lines** |
| Comment line 3 | `"Rave eJay"` | ✓ `"Rave eJay"` |
| Comment line 5 | category | ✓ category |
| Comment line 6 | `"58800"` | `"75600"` |

RAVE20 comment lines (8): `jam-`, `mer8`, `Rave eJay`, `2`, `Effect`, `75600`, `01`, `270799`
Lines 1–2 are category prefix/suffix (matching `.inf` fields 6–7); lines 4, 7, 8 have no equivalent in PXD_FORMAT.md.

## Header notes

Lines 1–13 before `[SAMPLES]` are unknown header content (line 3 is `#TRUE#`, lines 4–13 are blank `""`). `[SAMPLES]` on line 14 marks the start of PXD record entries. Entries begin on line 15.
