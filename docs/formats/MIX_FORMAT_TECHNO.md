# Techno eJay `.mix` Format Derivation (from WAMBAM.MIX + static analysis)

Source: `work/dumps/WAMBAM.samples.txt`, `work/dumps/WAMBAM.tracks.txt`, `work/dumps/WAMBAM.index.txt` (produced by parse scripts that are not checked in), `disks/Techno_eJay/MIX/WAMBAM.MIX` (2,144 bytes), cross-referenced with `disks/Techno_eJay/EJAY/PXD/RAVE20.INF`, and
static analysis of `disks/Techno_eJay/EJAY/EJAY/TECHNO.EXE`.

## 1. File Layout

| Region | Offset | Size | Content |
|--------|--------|------|---------|
| Header | 0x00 | 16 bytes | 8 × u16 LE words |
| Text block | 0x10 | variable | name\0, subtitle\0, marker+len, description\0 |
| Prefix | after desc NUL | 3 bytes | `01 00 00` |
| Grid | after prefix | variable | u16 LE pairs (see section 4) |
| Track count | before trailer | 2 bytes | u16 LE = 16 |
| Trailer | before EOF-4 | variable | `"Techno eJay 1.0"` / `"Techno eJay 2 "` + sample catalog |
| Footer | EOF-4 | 4 bytes | `a9 7a 8a 01` |

## 2. Header (16 bytes = 8 u16 LE)

```
word:  0    1    2      3    4      5      6    7
       0889 0000 NNNN  0000 008c  MMMM  0000  LLLL
```

| Word | WAMBAM value | Meaning | Confidence |
|------|-------------|---------|------------|
| 0 | 0x0889 | File magic | certain |
| 1 | 0x0000 | Constant | certain |
| 2 | 0x006f = 111 | Varies per file (111–391) | inferred |
| 3 | 0x0000 | Constant | certain |
| 4 | 0x008c = 140 | BPM — matches reported 140 BPM | likely |
| 5 | 0x0089 = 137 | Varies per file (134–158) | inferred |
| 6 | 0x0000 | Constant | certain |
| 7 | 0x001c = 28 | Varies per file (24, 28, 30) | inferred |

Example (`WAMBAM.MIX`): `89 08 00 00 6f 00 00 00 8c 00 89 00 00 00 1c 00`

## 3. Text Block (starts at 0x10)

Three null-terminated fields followed by a 3-byte prefix:

```
offset 0x10:  "Daniel\0"                    (mix name)
offset 0x17:  "#SKKENNUNG#:0000000\0"      (subtitle, constant)
offset 0x2b:  01                            (marker byte)
offset 0x2c:  19 00                         (u16 LE description length = 25)
offset 0x2e:  "sis is what se dj  does\0"  (description)
offset 0x46:  01 00 00                      (3-byte prefix before grid)
```

## 4. Event Grid (starts at 0x49)

Grid region: 0x49–0x90 = 72 bytes = 36 u16 LE values = **18 pairs of (offset, track)**.

Raw pairs (offset u16 LE, track u16 LE):

| Pair | Offset | Track |
|------|--------|-------|
| 0 | 26800 (0x68b0) | 0 |
| 1 | 25485 (0x638d) | 0 |
| 2 | 26800 | 1 |
| 3 | 25587 (0x63f3) | 2 |
| 4 | 25586 (0x63f2) | 0 |
| 5–10 | 26800 | 0 (×6) |
| 11 | 26800 | 1 |
| 12 | 26800 | 2 |
| 13 | 26800 | 1 |
| 14 | 26800 | 2 |
| 15 | 26800 | 0 |
| 16–17 | 0 | 0 (padding) |

Then u16 LE = 16 (track count) at 0x91–0x92, then trailer at 0x93.

### Grid interpretation — UNRESOLVED

**Offset field** — values cluster at 26800 with a few at 25485–25587. At 44.1 kHz: 26800 frames ≈ 0.61 s. Does not align to clean beat (18,900 frames) or bar (75,600 frames) boundaries at 140 BPM. **[uncertain]**

**Track field** — values are only 0, 1, 2. But `WAMBAM.samples.txt` shows events on tracks 1–16. The grid track values do **not** map directly to mix tracks. Either the track field is encoded differently, or tracks 3–16 are stored in a different structure not yet located. **[uncertain]**

## 5. Sample Name → RAVE20.INF Correlation (CONFIRMED)

`WAMBAM.samples.txt` lists sample placements as `(bar, track, "category\nname")` triples.
Every sample name matches a `RAVE20.INF` **str1\str2** pair exactly (10/10 match):

| WAMBAM sample | RAVE20.INF id | Bank name | Bars | Size |
|--------------|---------------|-----------|------|------|
| `zap\nup 4` | 14797 | T1LA030 | 1 | 176812 |
| de\nflate | 14629 | T1FX610 | 7 | 67598 |
| dj\n1L | 16972 | T1VX543L | 6 | 70931 |
| dj\n1R | 16973 | T1VX543R | 6 | 69995 |
| mush\n9 | 13042 | T1BS043 | 3 | 38185 |
| big-drop\nsugar 4L | 15539 | T1SQ087L | 5 | 159380 |
| big-drop\nsugar 4R | 15540 | T1SQ087R | 5 | 162259 |
| orion\n2 | 14603 | T1FX590 | 7 | 158266 |
| thunder\nL | 14554 | T1FX550L | 7 | 75858 |
| thunder\nR | 14555 | T1FX550R | 7 | 75844 |

The `.mix` references the samples by their numeric id — the **first field** of the `RAVE20.INF`
record — not by the `category\nname` string; the mix holds no sample-name text. The names in
`WAMBAM.samples.txt` are that record's fields 6 (str1) and 7 (str2), which is why the mapping is
exact. The `.inf` entry also gives the bank name, byte offset and size in `RAVE20`, and the bar
length in field 9 (num2), which matches the `Bars` column above. [certain]

**1 bar = 75,600 frames at 44.1 kHz, 140 BPM** — matches the `75600` bar length seen in
`RAVE20.INF` binary comments. `[likely]`

## 6. Trailer: Sample Catalog

Begins at `"Techno eJay 2 "` (10 files) or `"Techno eJay 1.0"` (2 files).

After the magic + `00 01` (2 bytes), a 10-byte header block follows:
- u16 count = 9
- u32 val1 = 2000 (0x07d0)
- u32 val2 = 3399 (0x0d47)

Then catalog entries in a **linked-list format**. Each entry:

```
u16 name_length     (includes NUL terminator + 0x01 marker byte)
name_bytes          (name_length bytes, ending with 0x00 0x01)
u32 fieldA
u32 fieldB
u16 next_name_length (0 = end of list)
```

Kit entries (6 kits):

| Entry | Name | fieldA | fieldB |
|-------|------|--------|--------|
| 0 | DanceMachine | 3400 (0x0d48) | 3899 (0x0f3b) |
| 1 | DanceMachine Samplekit Vol. 1 Raps & Voices | 3900 | 4499 |
| 2 | DanceMachine Samplekit Vol. 2 Drums & Synthies | 4500 | 5099 |
| 3 | DanceMachine Samplekit Vol. 3 Space Sounds | 5100 | 5699 |
| 4 | Dance eJay Samplekit Vol. 4 House | 5800 | 6499 |
| 5 | Dance eJay Samplekit Vol. 5 Trance | 6500 | 7199 |
| 6 | Dance eJay Samplekit Vol. 6 Latin Dance | 0 | 0 |

fieldA and fieldB increment by ~599–700 per kit — likely frame offsets into the sample bank.
Entry 6 (fieldA=0, fieldB=0) appears to be a terminator.

Individual sample entries follow (different/slightly extended format):

| Sample | fieldA | fieldB (0x67d2 ≈ 26578 frames) |
|--------|--------|-------------------------------|
| eurokick5 | 0 | 26578 |
| elec.sn 2 | 0 | 26578 |
| 808cl.hat2 | 0 | 26578 |
| 808op.hat | 0 | 26578 |
| crash2 | 0 | 26578 |
| clap8 | 0 | 26578 |
| darabuka2 | 0 | 45488 (0xb1e0) |
| egg2 | 0 | 26578 |
| hit5 | 0 | 26554 (0x67da) |

fieldB ≈ 0x67d2 (26,578 frames) matches the offset range seen in the grid (26800, 25485–25587).
These are likely sample frame offsets into the sample bank. `[inferred]`

After the last sample entry comes `>?~>` (bytes `3e 3f 7e 3e`), a 4-byte value, and the
per-track event table that holds the arrangement (section 12). The `RAVE20.INF` ids seen there
(e.g. 14797, 14629, 14794) are the sample references of its entries. `[certain]`

## 7. Footer

Last 4 bytes: `a9 7a 8a 01` = u32 LE `0x018a7aa9`. Constant across all 12 files. `[certain]`

## 8. Confirmed from Derived Dumps (`work/dumps/WAMBAM.*`)

| Fact | Source | Confidence |
|------|--------|------------|
| 16 tracks | tracks.txt lists tracks 1–16 | certain |
| Track L/R assignment | tracks.txt: 1–3, 6–12 stereo; 4, 13, 15 L-only; 5, 14, 16 R-only | certain |
| Per-bar placement | samples.txt: bar numbers 1–4, 61–64 | certain |
| Sample names are `category\nname` | samples.txt; matches RAVE20.INF str1\str2 10/10 | certain |
| Stereo = L/R track pairs | tracks 13/14, 4/5, 15/16 carry L/R variants | certain |
| 1 bar = 75,600 frames at 44.1 kHz, 140 BPM | matches RAVE20.INF comment `75600` | likely |
| samples.txt covers first 4 + last 4 bars | index.txt | certain |

## 9. Differences from Rave eJay ([`MIX_FORMAT_RAVE.md`](MIX_FORMAT_RAVE.md))

| Item | Rave eJay 1.01 | Techno eJay |
|------|---------------|-------------|
| Magic | `0x0A07` | `0x0889` |
| Grid | 351 × 32-byte records from offset 2 | compact (offset, track) pairs after text block |
| Trailer | `0x0A08` tag at fixed offset | `"Techno eJay X"` string + linked-list catalog |
| BPM field | not in header | header word 4 = 140 |
| Tracks | up to 8 (A/B lanes) | up to 16 |
| Sample refs | id − 731 rule | category\nname → RAVE20.INF str1\str2 |
| Sample index | `EJAY\PXD` | `RAVE20.INF` |
| Footer | small values + `0x0001`,`0x0002` | `a9 7a 8a 01` |

## 10. Static Analysis of `TECHNO.EXE`

`disks/Techno_eJay/EJAY/EJAY/TECHNO.EXE` (1,290,240 bytes) is the VB6 application.
The 5,136-byte `disks/Techno_eJay/TECHNO.EXE` is only a 16-bit NE launcher. File I/O
goes through MSVBVM50 runtime dispatch (`[0x5253xx]` indirect calls).

- `.mix` extension check at VA `0x0043CC76` and `0x004AFB17` (pushes `".mix"` string VA `0x0041F1A4`). `[certain]`
- Grid-reading loop at VA `0x004AF8CE`: counter 1–50 (`0x32`), VB6 `Open`/`Get` binary reads. `[certain]`
- Trailer/catalog iteration at VA `0x004AFDD0`: `Item`-by-index (`[0x525414]`) + `StrComp` (`[0x525404]`). `[likely]`
- No DLL beside the application in `disks/Techno_eJay/EJAY/EJAY/` contains `.mix` or `eJay` strings — all mix logic is in `TECHNO.EXE`. `[certain]`

## 11. Unresolved Questions

1. **Grid record semantics**: What do offset values (26800, 25485–25587) represent? Frame positions? Bar-relative positions? Sample bank offsets? They're in the same range as catalog fieldB values (~26578). The arrangement itself is in the trailer's event table (section 12), so this grid is something else.
2. **Grid track mapping**: Grid track values (0–2) don't match samples.txt tracks (1–16). The event table stores tracks 1–17 directly; 17 is present in every file and always empty.
3. **Grid size**: 18 pairs for WAMBAM seems small for events across 64+ bars on 16 tracks. The 171 placements of WAMBAM live in the event table, not here.
4. **Prefix bytes** `01 00 00` between description NUL and grid start — meaning unknown.
5. **Header words 2, 5, 7**: Vary per file; meaning unknown.
6. **Event entry flag and extra bytes**: Every entry's first byte is 0 in the files seen. The 10 extra bytes of the long entry variant vary per placement and are not interpreted; the manual's per-sample volume and cut controls are plausible owners. `[guess]`

## 12. Per-Track Event Table (Resolved)

The trailer's `"Techno eJay"` block ends with a fixed 4-byte marker `>?~>`, then a 4-byte value,
then the arrangement as one block per track. This is the structure
[`../../work/src/mixsamples.py`](../../work/src/mixsamples.py) reads and
[`../../work/src/sdmixplayer2.py`](../../work/src/sdmixplayer2.py) plays.

| Region | Size | Content |
|--------|------|---------|
| Marker | 4 | `3e 3f 7e 3e` (`>?~>`) |
| Prefix | 4 | Unknown; `38 05 00 00` (0x0538) in WAMBAM |
| Track block | 5 + entries | `u8 track`, `u32 count`, then `count` entries |

Blocks appear in track order 1–17. Track 16 is empty in every file seen; track 17 is present
with count 0 and then the footer follows. No track-18 block exists.

Each entry ends with a `u16` sample id — the `RAVE20.INF` first field. Its size depends on the
sign of the `i16` time field that precedes the id:

| Form | Size | Layout |
|------|------|--------|
| Short | 7 | `u8 flag`, `i16 time`, `i16 second`, `u16 id` |
| Long | 17 | same 7 bytes, then 10 parameter bytes |

* `time` is a fixed-point bar position with **7 fraction bits**. Short entries store it negated
  (`time = -(128 * k + 1)`), long entries store it directly (`time = 128 * k`); bar 1 is the start
  of the mix, so `bar = units / 128 + 1` where `units = abs(time) - (1 if time < 0 else 0)`.
  `[likely]` — it reproduces every row of
  [`../../work/dumps/WAMBAM.samples.txt`](../../work/dumps/WAMBAM.samples.txt)
  (bar, track and sample id,
  15/15) and every entry in all 13 mixes parses to exactly the footer.
* `second` is `-1` in the short form and `0` in the long form.
* `flag` is `0` in every entry seen. `[certain]` for the 13 files in `disks/Techno_eJay/MIX`.
* The long form's 10 bytes carry a per-placement parameter set (e.g. `00 00 00 00 80 00 00 00 00 00`,
  `b8 00 00 00 00 00 00 00 00 00`); meaning unknown. `[uncertain]`
* A bar is 75 600 frames at 44.1 kHz, four beats at 140 BPM; header word 4 is 140 in all 13
  files. `[likely]`

Track channels follow
[`../../work/dumps/WAMBAM.tracks.txt`](../../work/dumps/WAMBAM.tracks.txt): tracks
4, 13 and 15 are left-only, 5, 14 and 16 right-only, the others stereo/centre.
Engine side of those channels: §13.
All 13 mixes parse with
[`../../work/src/mixsamples.py`](../../work/src/mixsamples.py) and
[`../../work/src/sdmixplayer2.py`](../../work/src/sdmixplayer2.py) `--list`.

## 13. Audio Engine Conclusion

The engine a Techno mix is rendered by is `disks/Techno_eJay/EJAY/EJAY/PXD32R4.DLL`
(`pxd32r4.dll`, named by `TECHNO.EXE`). Its gain path is linear with unity at full
scale and no `0.5` factor anywhere; pan is a channel selector rather than a curve;
and the `.MIX` stores no pan at all, the stereo image coming from paired
`...L`/`...R` samples on separate tracks. The correct model is therefore
**unity-centre**, not constant power, and
`player/formats/techno/techno_event_builder.py` plays a centred track at full
scale in both channels.

Addresses, confidence tags and the remaining questions:
[`../../work/docs/PXD32R4.md`](../../work/docs/PXD32R4.md).
