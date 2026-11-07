# .PXD file format (tPxd)

This document describes the proprietary `tP`/`tPxd` container format used by PXD32D5-D4.DLL, as reverse-engineered from the decompilation, binary disassembly, and the
`bo-test.pxd` / `hyper-test.pxd` fixtures (not checked in).

## Overview

`.pxd` files in this project are `tPxd` containers. They are decoded by `RWavToTemp` when `sub_10019DEE` classifies the stream as type `1` (magic `tP` / `0x5074`), routed to `sub_10016361` (`_decode_tp`) which uses a DPCM/codebook decoder with a shared delta table and a runtime codebook.

## Container structure

All offsets are byte offsets from start of file. Endianness is little-endian unless stated otherwise.

```
Offset  Size  Type  Description
0x00    4     char  Magic: 't','P','x','D' (0x74 0x50 0x78 0x44)
0x04    1     u8    len  (h[4])
                    The comment field starting at offset 0x04 is len bytes long,
                    and this byte itself is counted in len.
0x05    len-1 bytes NUL-terminated ASCII comment: len-2 text bytes followed
                    by 0x00.  For the Rave eJay sample bank this is a fixed
                    6-line CRLF "library record" - see
                    "Comment-line semantics" below.
4+len   2     u8[2] 0x00 0x54 in all 1 278 tPxD files on the install image
                    (verified by full-bank scan); skipped by both header
                    readers (see below), so its meaning is unverified.  A
                    tag that never varies (and is never read) cannot
                    distinguish a container version, so no version field
                    exists in this format.
4+len+2 4     i32   Frame count (mono samples at 44.1 kHz)
4+len+6 2     u8/u16 trailing header bytes, skipped by both readers.
                    0x0000 in 1 247 of 1 278 files; small non-zero values
                    (-2, +1, +243, -193, ...) in 31 files, differing even
                    between stereo L/R siblings.  Unused (see below).
4+len+8 ...   bytes ADPCM/codebook stream data
```

### Header parsing details (from `sub_10019DEE`)

- If `u16 @ 0 == 0x5074` (`'t','P'`): `sess.stream_type = 1`. Read offset becomes `4 + h[4] + 2 + 4 + 2` (which equals `4 + len + 8`), matching the data start. **[certain]** `0x10019E3B` (`cmp eax, 0x5074`) is the only byte comparison in the `tP` branch — the walk `p += len` (`0x10019E5E`), `p += 2` (`0x10019E6C`), `p += 4` (`0x10019E75`), `p += 2` (`0x10019E7E`) runs with no further comparisons, so no header byte except the magic is validated.
- The two bytes at `4 + len` are `0x00 0x54` in **all 1 278** `tPxD` files on the install image (previously "all three real files checked"). `sub_10019DEE` skips them (`p += 2`, `0x10019E6C`) and `AWaveDauer` starts at `len + 6`, so neither reader interprets them; they may be a format/version marker — but since the pair is constant across both products' files (the 1998 and 2000 product banks) and never read, it cannot function as a version. There is no container version field. **[certain]** (bytes); **[guess]** (original meaning).
- The two bytes at `4 + len + 6` were previously described as padding/alignment "`0x0000` in every known file". That is outdated: 31 of 1 278 files carry small non-zero values there (e.g. −2, +1, +2, +243, −193, −39; `R1FX026L` = −2 vs its sibling `R1FX026R` = +1). All 31 of those files still decode end-to-end under the standard layout (stream consumed exactly to the last byte, declared frame count reached), so the container layout is unchanged — these are trailing/unused header bytes. Not the last decoded sample, not a readable 16-bit sum of the file. **[certain]** (variation, both readers skip them); **[guess]** (encoder artifact).
- `pxd32d5.parse_pxd_comment(header)` validates and decodes this field for callers: it checks the magic, length, NUL terminator and ASCII content, and returns a `PxdComment` (`length`, `text`, `lines`). The line layout is application metadata and is not validated.
- `AWaveDauer` for `tP` files: `off = (u32 @ 4 & 0xFF) + 6` (i.e. `(h[4] & 0xFF) + 6`), read `i32 @ off` as frame count `f`, return `4 * f`. This is `2 * v14` where `v14 = AWaveDauer/2` is the number of mono 16-bit bytes at 44.1 kHz the temp wave will hold.

### Comment-line semantics: the comment carries the sample's library record

The comment text is CRLF-separated; every bank file except `EJAY\INTRO.PXD` has exactly **6 lines**, and they are the sample's record from the install's sample index `disks/Rave_eJay/RAVE/EJAY\PXD` (see [`MIX_FORMAT_RAVE.md`](MIX_FORMAT_RAVE.md) §3) — joined by filename, character-equality counts over the 1 148 joined bank files:

| Line | Content | EJAY\PXD index field | Exact agreement |
|------|---------|----------------------|-----------------|
| 1 | sample display name, part 1 (`"stone and"`, `"conga 2000"`) | field 5, name part 1 | 1 130 / 1 148 |
| 2 | sample display name, part 2 (`"iron"`, `"L"`, `"+ off"`, `""`) | field 6, name part 2 | 1 128 / 1 148 |
| 3 | producer/product tag: `"Rave eJay"` in every file | — | 1 277 / 1 277 |
| 4 | *empty* | field 2, which is *always empty* in the index | 1 148 / 1 148 |
| 5 | category / browser group: `bass` `drum` `effect` `loop` `sequence` `sphere` `special` `voice` | field 3, category (counts match the filename prefixes `BS` `DA`–`DF` `FX` `LA`–`LC` `SQ` `SR` `SF` `VX`) | 1 148 / 1 148 |
| 6 | the constant `"58800"` — **one bar in frames** (58 800 = 4 beats at 180 BPM = 1.333 s), the bank's grid quantum of [`MIX_FORMAT_RAVE.md`](MIX_FORMAT_RAVE.md) §2.1, identical in every file | — (index field 4 holds the sample's *own* length in bars; the comment holds the bar *size*) | 1 277 / 1 277 |

This settles the long-standing open question of why every file — whatever its length — says `58800` (e.g. hyper sounds of 14 700 frames): it is not the sample's own length, it is the grid constant copied into every comment. Cross-checked: `comment frame count == index bars × 58 800` exactly in 1 144 / 1 148 joined files (the 4 off-by-a-few exceptions are documented in
[`../../work/docs/HYPER_GENERATOR.md`](../../work/docs/HYPER_GENERATOR.md) §2). With line 4 mirroring the index's always-empty field 2, the comment is simply the index record minus the filename, plus the producer tag and the grid constant.

`hyper-test.pxd` shows the non-bank shape: its line 5 is `hyper`, not one of the 8 categories — the hyper bank (`r1hg0001.pxd`–`r1hg0128.pxd`, 128 files absent from the index) keeps the same 6-line frame, with line 2 a **unique sequential id `001`–`128`** instead of a name split (see
[`../../work/docs/HYPER_GENERATOR.md`](../../work/docs/HYPER_GENERATOR.md)).

Known exceptions (full bank scan; 1 279 `.pxd` files on the image, 1 278 of which are `tPxD`):

| Exception | Evidence |
|-----------|----------|
| `EJAY\INTRO.PXD` — comment is a **single line**, `"Rave eJay Intro"`; the only file with a 1-line comment | full-bank scan |
| 23 bank files where lines 1/2 differ from index fields 5/6: split drift (`('heart shock 1','')` vs `('heart shock','1')`), rename (`('drop','')` vs `('drop','1')`), one spelling fix (comment `"string sphere 1"`, index `"sting sphere 1"`) | the join |
| `R1DA084.PXD` is listed in the index but is **not a `tPxD` stream** (magic `54 B0 E5 00`); the only non-tPxD `.pxd` on the image | full-bank scan |
| The example `&chirpy 1\r\n\r\n58800` above is a 3-line variant (name / empty / 58800, no producer/category lines) from a file outside the bank; kept as the historical illustration of the raw layout | this section's predecessor |

The metadata lines (1, 2, 5) are descriptive only: the decode path never reads them (`sub_10019DEE` validates only length, terminator and ASCII), so Libre files that omit or reorder them decode identically.

### Fixtures (verified; files not checked in)

| File | Size (bytes) | h[4] (len) | Data start | Frame count | AWaveDauer | Output WAV size |
|------|---------------|-------------|------------|-------------|------------|-----------------|
| `bo-test.pxd` | 66761 | 38 | 50 (4+38+8) | 117600 | 470400 | 235244 (44 + 2*117600) |
| `hyper-test.pxd` | 8943 | 42 | 54 (4+42+8) | 14700 | 58800 | 29444 (44 + 2*14700) |

## Decoder: tP DPCM/codebook (`sub_10016361`)

The decoder operates on a 8100-byte codebook (`dword_1008B750`, allocated by `sub_1001186B`) with entries 16 bytes apart. Entry 0 is the silent entry written by `sub_10011EFF`: `(0,0,0,0,0,-1)` stored as `int16` deltas terminated by `0xFFFF`. The stream defines other entries on-the-fly (and may overwrite entries due to the 16-byte slot layout allowing up to 11 deltas).

### Shared delta table (`DELTA_TABLE`, 256 entries)

Built by `sub_10011EFF`:
```text
v1 = 2.2; v20 = 1.0565; t[128] = 0;
for j in 1..127: t[128+j] = (j>=6 ? (int)(v1-0.52) : 1) + t[128+j-1]; v1 *= v20; v20 -= 0.00022
for k in 1..128: t[128-k] = -t[128+k]
for m in 0..255: t[m] = t[m] * 2 (stored as int16)
```
Properties (verified): `len==256`, `t[128]==0`, `t[127]==-2`, `t[129]==2`, range roughly ±25266, `t[0]==0` (index 256 never written), symmetric `t[1:128] == [-x for x in reversed(t[129:256])]`. Exported as `pxd32d5.DELTA_TABLE`.

### Bytecode

| Byte | Meaning |
|------|---------|
| `0x00..0xF3` | Play codebook entry `byte` (entries addressed as `book + 16*index`). |
| `0xFF` | One step: read next byte `b`, do `acc = acc + DELTA_TABLE[b]` with 16-bit wrap; emit sample. |
| `0xF4..0xFE` | Define entry: `pos += 1; idx = src[pos]` (entry index), `count = opcode - 0xF3` (1..11). Then read `count` bytes and write `DELTA_TABLE[src[pos]]` into entry `idx` at offsets `e + 2*k` for `k=0..count-1` (16 bytes apart per entry). Write terminator `0xFFFF` at `e + 2*count`. Then play that entry. (Note: Hex-Rays showed `opcode+13` due to char→int sign extension; actual count is 1-11.) |

### Emission

For each delta step applied (either from playing a codebook entry or from `0xFF`):
1. `acc += delta` where `acc` is the 16-bit DPCM integrator held in `Session.vol_word` (persists across blocks/calls). Wrapping is 16-bit (`_wrap16`).
2. `gain = (sess.pan * sess.volume) >> 8` (published by `sub_100149E0` before decoding; in file conversion path `pan=512`, `volume=0x10000` so `gain = 131072`).
3. `prod = acc * gain`. If signed multiply overflows (detected like IMUL overflow), `sample = 0x7FFF` if `prod>0` else `0x8000`. Otherwise `sample = (prod >> 16) & 0xFFFF`.
4. Add `sample` (signed) to destination 16-bit value at current position with saturation: if sum in [-0x8000, 0x7FFF] store it, else store `0x8000` if sum negative (sign bit set) else `0x7FFF`. The overflow clamp uses the sign of the *wrapped* sum (quirk of original).
5. Advance destination by 4 bytes (stereo frame stride). **Only the left channel is written**; the right channel remains zero in the decoded stereo buffer.

### Decoder behavior notes

- The integrator (`vol_word`) carries over between decode blocks and between calls (not reset per block).
- Bounds are only re-checked when a codebook entry finishes; entries are not cut in half, so a block may overrun by a few samples (the wrapper saves/restores the last ~64 bytes to handle this).
- An entry slot is 16 bytes; a definition with count 11 writes 11 deltas + terminator = 24 bytes into that 16-byte slot, overwriting the start of the next entry.
- When `Session.chan_mode` has low word set in some cases the decoder emits one extra sample before clearing it (not used in normal `RWavToTemp` conversion).

### Output format (from decoder)

- Decoded to 44.1 kHz stereo 16-bit PCM in memory (each sample written as 16-bit at 4-byte stride). 
- In the `a3 <= 0` conversion path, after each decode block: for each frame produced, copy left sample from offset `4*i` to `2*i` (drop right channel), advance write position by `2*frames`. 
- Final mono 16-bit output is little-endian.

## RIFF/WAVE output (when converting)

When `RWavToTemp` is called with `a3 <= 0` (convert file) and `engine.output_kind == 4` (default in tests), it writes a 44-byte RIFF header via `sub_10013198`:
- `"RIFF"` + size (data_len + 36) + `"WAVE"`
- `"fmt "` + chunk size 16 + PCM tag 1 + channels 1 (mono) + rate 44100 + byte rate 88200 + block align 2 + bits 16
- `"data"` + data_len

The data written is mono 16-bit little-endian at 44100 Hz (after left-channel extraction from decoded stereo and any upsampling/resampling as applied by the decoder path for non-44.1k inputs). File is truncated to `header_size + v14` after rendering.

## Other notes

- `AWaveDauer` returns negative values for non-PCM RIFF (compressed formats) — the original produces broken output in that case rather than erroring.
- The container's frame count is the number of mono samples in the final output at 44.1 kHz.
- `tPxd` streams may reference codebook entries not explicitly defined in the visible stream? Observed fixtures define entries inline; behavior for undefined entries follows from entry 0 being silent and terminators.
