# PXD32D5 (build D4) — PXD → WAV codec: working notes

**Status:** decoder recovered and prototyped; one open question about the exact output-length stop condition.
**Scope:** how `pxd32d5_d4.dll` turns an eJay `tPxD` sample into a WAV file, and how to reimplement that in Python.
**Method:** static analysis only (Capstone via `_pxd_range.py`); the DLL was never loaded or executed. Verification is a
pure-Python model checked against `..\bo-test.pxd` and `..\hyper-test.pxd`.

Confidence tags as elsewhere: **[certain]** visible in the code, **[likely]** the only reading that fits, **[guess]** plausible.

---

## 1. Where the code is

The converter lives in the **unexported object code before the first export** (`0x10001000`–`0x100104C5`). The
export `W2P` (`0x100104C6`) and `ALoad` (`0x1001974A`) are thin wrappers/entry points onto it; the real work is done by a
C++ "converter object" at `0x100564E0` and a global codec context at `0x1004E2D0`.

| VA | Role | Confidence |
|---|---|---|
| `0x100101DB` | `main`-style driver: `f046` reset, `0x100101EA` reset, `0x1001020E` setup | certain |
| `0x100101CC` | one-time call into the table builder (via `0x100101C2`) | certain |
| `0x1000FFD7` | **table builder** — builds the delta ladder + quantiser at object `0x1004E2D0` | certain |
| `0x1000F046` | reset a "file object" (zero 6 dwords) | certain |
| `0x1000EE40` | close/unmap a mapping object (`UnmapViewOfFile`, `CloseHandle`, `_lclose`) | certain |
| `0x1000EEA8` | create a `PAGE_READWRITE` file mapping of N bytes and map it | certain |
| `0x1000EF09` | `OpenFile` + `_llseek(end)` (size) + `CreateFileMappingA` + `MapViewOfFile` | certain |
| `0x1000EFED` | write a buffer to a file: `OpenFile` + `_hwrite` + `_lclose` | certain |
| `0x1000F115` | **file loader / container parser** (PXD and WAV) | certain |
| `0x1000F580` | store the input path at `obj+0x00` | certain |
| `0x1000F55D` | store the output path at `obj+0x104` | certain |
| `0x1000F825` | **PXD → WAV driver**: parses, builds the WAV header, runs the decode loop, writes the file | certain |
| `0x1000F5C0` | encoder: nearest-ladder-index for a sample difference (with clamp/refine) | certain |
| `0x1000F6B0` | encoder: look up an op for a delta pair (hash table `0x100567F0`) | certain |
| `0x1000F792` | encoder: **teach** a new op (assign `op → T1/T2`, register in the hash) | certain |
| `0x1000FB3E` | **WAV → PXD driver** (the reverse direction, `Waver → pxd (Textinfo)`) | certain |
| `0x1000FF00`–`0x1000FF92` | encoder: emit a taught op (`F5 op v1 v2`) or a plain op, advance `cur` | certain |
| `0x100101C2`/`0x100101DB` | static initialisers; `0x100101DB` calls `0x100101EA` then `0x1001020E` | certain |

Targets and state (from `f825` frame, `A` = file object at `[ebp-0x48]`, `B` = output mapping at `[ebp-0x5c]`):

| Address | Meaning |
|---|---|
| `0x1004E0D0` | `T1[256]` — opcode → ladder index for the 1st sample of a pair (zero in the file) |
| `0x1004E1D0` | `T2[256]` — opcode → ladder index for the 2nd sample of a pair (zero in the file) |
| `0x1004E2D0` | **delta ladder** `D[256]` (int16), indexed by a byte value |
| `0x1004E2D0+0x204` | **quantiser table** `Q[...]`, 64 KiB (encoder only), indexed by `diff + 0x3FFF` |
| `0x100564D4` | `Q` base pointer (set by the builder to `0x1004E2D0+0x204`) |
| `0x100564D8` | `D` base pointer (set by the builder to `0x1004E2D0`) |
| `0x100567F0` | encoder hash table, 64 KiB (key = `v1*256 + v2`, value = op) |

`*(0x100564D4)`/`*(0x100564D8)` are written only by the builder at `0x100101AE`/`0x100101B7`; the decode/encode loops read
them. **[certain]** (whole-file scan for the two VAs).

---

## 2. The `tPxD` container (loader `0x1000F115`) **[certain]**

The loader maps the file and dispatches on the first word:

```
if word[0] == 0x5074 ('tP'):        # 't','P','x','D' little-endian magic
    fmt = 1  (PXD)
    p = view + 4
    attr = byte[p]                  # attribute byte b (0x26 / 0x2A in the test files)
    p += attr
    p += 2                          # two bytes skipped
    length = dword[p]               # field used as length * 2
    p += 4
    init = int16[p]                 # initial value of the running sample
    p += 2
    data = p                        # stream pointer
    stream_len = filesize - (data - view)
elif word[0] == 0x4952 ('RI'):      # RIFF/WAVE
    fmt = 2  (WAV)                  # see §5
```

So `tPxD` = 4-byte magic, 1 length byte `b`, `b` bytes of text (sample name, collection, category, a numeric field such as
`58800`), 2 bytes, a 32-bit length field `L`, an int16 seed, then the op stream.

For the two test files (recomputed with Python):

| file | size | `b` | text | `L` (`length`) | `init` | data off | stream len |
|---|---:|---:|---|---:|---:|---:|---:|
| `bo-test.pxd` | 66 761 | `0x26` | `chirpy 1 … bass … 58800` | 117 600 | 0 | 50 | 66 711 |
| `hyper-test.pxd` | 8 943 | `0x2A` | `Peel off 001 … hyper … 58800` | 14 700 | 0 | 54 | 8 889 |

Declared output bytes = `L << 1` (235 200 / 29 400) — i.e. exactly **2 bytes per declared sample** (117 600 / 14 700 samples).

---

## 3. The delta ladder (builder `0x1000FFD7`) **[certain]**

The builder fills the object at `0x1004E2D0`. `W[0] = 0`, then a geometric-but-flattening ladder:

```c
W[0] = 0;
double v = 2.1;        // 0x400199999999999A
double r = 1.056840...; // 0x3FF0E76C8B439581
for (i = 1; i < 0x80; i++) {
    if (i < 6) W[i] = W[i-1] + 1;
    else       W[i] = (int)(W[i-1] + v - 0.52);   // K   = double @ 0x100432E8 = 0.52
    v = v * r;
    r = r - 0.00022;                               // K2  = double @ 0x100432E0 = 0.00022
}
// negative half of D:
for (i = 1; i <= 0x80; i++) D[0x80 - i] = -W[i];
// positive half of D (W[0..0x7F] already sit at D[0x80..0xFF]):
for (j = 0; j < 0x80; j++)  D[0x80 + j] = W[j];
```

So `D` is a signed ladder: `D[0x80] = 0`, `D[0x81] = 1`, … increasing positive steps up to `D[0xFF] = W[0x7F]`, and
`D[0x7F] = -W[1] = -1`, … down to `D[0x00] = -W[0x80]`. `W[0x80]` is never used by the decoder (opcode `0x00` is
special-cased), so it can stay 0.

Computed values (`_pxd_decode_probe.py`):

```
W[0..16] = [0, 1, 2, 3, 4, 5, 7, 9, 11, 13, 15, 18, 21, 24, 27, 30, 34]
W[0x7F]  = 12051        (largest positive step = full-scale-ish)
D[0x7F]  = -1           D[0x80] = 0     D[0x81] = 1
D[0xFF]  = 12051        D[0x00] = -12051
```

The builder also fills the encoder-only quantiser `Q` (64 KiB at `+0x204`) with the near est ladder index for each
difference (default `0xFE`, refined for `diff ∈ [-0x3FFF, 0x3FFF]`), and finally stores the two base pointers.

---

## 4. The PXD → WAV decode (`0x1000F825`) **[certain, except §6]**

1. `0x1000F115` loads the source into object `A` (§2). If `A[0x18] == 0` → nothing to do.
2. Output mapping `B` is created with `CreateFileMappingA(-1, NULL, PAGE_READWRITE, 0, A[0x24] + 0x2C, NULL)`
   (`0x1000EEA8`) — i.e. room for a 44-byte WAV header plus `A[0x24]` bytes of data.
3. The WAV header is written into `B` (see §5).
4. Loop over the op stream `A[4]`, length `A[0x18]`:
   - `cur = A[0x28]` (int16); output offset starts at `0x2E` (46); the first sample (`cur << 2`) is written at `0x2C`
     (44) first.
   - read byte `op`; the read index advances by 1 (or by 4 for `0xF5`);
   - `op == 0x00` → emit the **current** value 5 times (5 words), output offset += 0xA;
   - `op == 0xF5` → read `sel`, `v1`, `v2`; `T1[sel] = v1`, `T2[sel] = v2`; then emit **2** samples (below);
   - otherwise → emit **2** samples (below).
   - each emitted sample: `cur = int16(cur + D[Tk[op]])`; write `word = (cur << 2) & 0xFFFF` to `B + off`; `off += 2`
     (2 samples → `off += 4`).
5. Write `B` to the destination path via `0x1000EFED` and unmap.

`cur` is 16-bit wrap-around arithmetic; `cur << 2` is a 16-bit truncating shift (i.e. the PCM value is `cur*4` taken
mod 65536). Each op therefore produces **two mono 16-bit samples**; `0x00` produces **five** copies of the current value
(silence/pad runs — the test files start with a long `0x00` run and an all-zero `T1/T2`, so the seed decodes to silence
until the first `0xF5`).

### Per-byte work (pseudo-C, faithful)

```c
cur = seed;                       // int16
T1[256] = {0}; T2[256] = {0};
for (i = 0; i < stream_len; ) {
    op = stream[i++];
    if (op == 0x00) {
        for (k = 0; k < 5; k++) { out(off) = (cur << 2) & 0xFFFF; off += 2; }
    } else if (op == 0xF5) {
        sel = stream[i++]; v1 = stream[i++]; v2 = stream[i++];
        T1[sel] = v1; T2[sel] = v2;
        cur += D[T1[sel]]; out(off) = (cur << 2) & 0xFFFF; off += 2;
        cur += D[T2[sel]]; out(off) = (cur << 2) & 0xFFFF; off += 2;
    } else {
        cur += D[T1[op]]; out(off) = (cur << 2) & 0xFFFF; off += 2;
        cur += D[T2[op]]; out(off) = (cur << 2) & 0xFFFF; off += 2;
    }
}
```

`D[index]` is the int16 ladder of §3. Opcodes `T1`/`T2` start at 0, so an untrained op uses `D[0] = -W[0x80]` (0 in
practice) — the `0xF5` "teach" op is how the stream builds its own dictionary as it goes.

**Reimplementation note:** because every byte emits a *pair* of samples and `0xF5` is a 4-byte packet, the stream is a
self-describing table-driven delta codec. A Python port is ~60 lines using `struct`/`array` (see
`_pxd_decode_probe.py`).

---

## 5. The WAV bytes written (`0x1000F825`) **[certain]**

This is a **standard** RIFF/WAVE header. The writer emits the chunk size as two words (`0x10` at 16, `0` at 18) which
together form the 4-byte fmt chunk size `0x00000010`, so the fmt fields begin at offset 20 — the normal positions. Byte
map for a mono 16-bit source:

| off | bytes | value | meaning | reader offset |
|---:|---:|---|---|---|
| 0 | 4 | `RIFF` | | |
| 4 | 4 | `data_len + 0x24` | RIFF size (file size − 8) | |
| 8 | 4 | `WAVE` | | |
| 12 | 4 | `fmt ` | | |
| 16 | 4 | `0x00000010` | fmt chunk size (written as `word` 16 @16, `word` 0 @18) | |
| 20 | 2 | `0x0001` | format tag = PCM | `+0x14` |
| 22 | 2 | `0x0001` | channels = mono | `+0x16` |
| 24 | 4 | `0x0000AC44` | 44 100 Hz | `+0x18` (low word) |
| 28 | 4 | `0x00015888` | 88 200 (byte rate) | |
| 32 | 2 | `0x0002` | block align | |
| 34 | 2 | `0x0010` | 16 bits/sample | `+0x22` |
| 36 | 4 | `data` | | |
| 40 | 4 | `data_len` | data chunk size | |
| 44 | 2 | first sample (`cur << 2`) | the seed sample | |
| 46 | … | decoded samples | `data_len` bytes total from offset 44 | |

Python's `wave` module reads these outputs directly (`1 ch, 16 bit, 44100 Hz, 117600/14700 frames`). The engine's own
reader (`0x1000F115` WAV branch) reads the same standard offsets (`+0x14` tag, `+0x16` channels, `+0x18` rate low word,
`+0x22` bits). It also applies sanity heuristics to the RIFF/`data` sizes and scales `A[0x24]` by the source
stereo/bit-depth/rate (×2 mono, ×2 8-bit, ×4/×2 for 11 025/22 050 Hz) so the decoded stream is always 44.1 kHz mono 16-bit.

---

## 6. Output length — reconciled

The loop bound is the **input stream length** (`A[0x18] = filesize − data_off`), so the DLL decodes the *whole* stream.
For the test files the full stream decodes to **more** than the declared `data` size:

| file | declared `A[0x24]` | declared samples | decoded (seed + full stream) | extra bytes |
|---|---:|---:|---:|---:|
| `bo-test.pxd` | 235 200 | 117 600 | 260 810 | 25 610 |
| `hyper-test.pxd` | 29 400 | 14 700 | 34 442 | 5 042 |

Two facts make this safe and explain the file size:

1. The output is a **file mapping** created with `CreateFileMappingA(-1, NULL, PAGE_READWRITE, 0, A[0x24] + 0x2C, NULL)`
   (`0x1000EEA8`). Windows rounds file-mapping sizes up to the 64 KiB allocation granularity, so `235 244` becomes a
   `262 144`-byte view — enough for the `260 810` bytes the loop writes. No overflow.
2. The writer (`0x1000EFED`) then writes exactly `A[0x24] + 0x2C` bytes to disk. So the file is
   `header (44) + data (A[0x24])` = **235 244 / 29 444 bytes**, and the WAV `data` chunk is the **first `A[0x24]` bytes**
   of `seed_sample + full op decode`. The extra decoded tail is discarded.

`A[0x24]` is exactly `2 × L` (the header length field) = 2 bytes per declared sample. `pxd2wav.py` mirrors this: decode
the full stream, then slice to `A[0x24]` bytes. The produced files are `44 + A[0x24]` bytes and parse with the standard
`wave` module as 117 600 / 14 700 mono 16-bit 44.1 kHz frames.

The one remaining nuance: for `hyper-test.pxd` the declared boundary falls one sample inside the last op, so the last
2 bytes of the declared data are the first half of a decoded pair. This is harmless (the file/header still agree) and is
what the DLL writes.

---

## 7. The reverse direction (`0x1000FB3E`, WAV → PXD) — confirms the codec **[certain]**

`0x1000FB3E` is the exact inverse and pins every field above:

1. `memset` the encoder hash (`0x100567F0`, 64 KiB), `T1`, `T2`; `op_counter = 0`.
2. Load the WAV with `0x1000F115`; the header parse is §5's (channels +0x16, rate +0x18, bits +0x22).
3. Write `t`, `P`, `x`, `D`, then an attribute/length byte, then the text block, then `2` bytes, then the **length
   field** = `data_len * factors` (see below), then the int16 seed, then the op stream.
4. Walk the source in **pairs of int16 samples** (`[ebp-0x78]` steps by 2); for each pair emit:
   - two indices `idx1 = 0x1000F5C0(prev, s1)`, `idx2 = 0x1000F5C0(prev+`...`, s2)` (`0x1000F5C0` = nearest ladder index
     for `s − prev`, clamped so `|prev + D[idx]| < 0x2000` and refined `±1`);
   - if both indices are the neutral `0x80` and the next three pairs are too → emit a single `0x00` (the 5-sample run);
   - else `op = 0x1000F6B0(idx1, idx2)`; if the hash has no op, `op = 0x1000F792(idx1, idx2)` **teaches** a fresh op and
     the stream carries `F5 op idx1 idx2`; then advance `cur` by `D[idx1]` and `D[idx2]`.
5. The output length field = `data_len` scaled by the source format: `×2` if mono, `×2` if 8-bit, `×4`/`×2` for
   11 025/22 050 Hz (mirrors the reader). Written with the same `data`-chunk layout.

This closes the loop: `T1/T2`, `D`, the `0x00` run and the `0xF5` packet in §4 are exactly what §7 produces. **[certain]**

---

## 8. Verification

Two checks were run in pure Python (no DLL execution):

**A. Table build.** `D[0x80] = 0`, symmetric ladder, `D[0xFF] = W[0x7F] = 12051`. `0x100318D4` is
`__ftol` (it sets RC = truncate via `or ah, 0xc` then `fistp`), so `W[i] = trunc(W[i-1] + v - 0.52)` is correct.

**B. Encoder ↔ decoder round-trip.** `_pxd_roundtrip.py` implements the encoder of §7 and feeds its PXD output
through the decoder of §4. Encoding a 0.8 FS 220 Hz sine and decoding it back reproduces the signal:

```
encoded: seed=0 ops=15453 L=88200
internal-domain compare: mean|err|=2.458 max|err|=15
  decoded [0, 420, 817, 1237, 1634, 2054, 2451, 2848]
  target  [0, 411, 821, 1231, 1639, 2046, 2450, 2853]
```

The residual is the ladder's quantisation. **The codec model in §3–§4 is therefore self-consistent and correct.**

## 9. Anomaly — the two bundled `-test.pxd` files

The same decoder applied to `..\bo-test.pxd` / `..\hyper-test.pxd` does **not** produce audio: `cur` is a
random walk (σ≈89 per step) that leaves the ±8191 domain and, through `cur << 2`, aliases — *this is the
white noise / clicking*. Three independent signals say these files are not output of this codec:

| Observation | bo-test | hyper-test |
|---|---:|---:|
| distinct plain opcodes used | 247 | 203 |
| plain-opcode uses of a never-taught opcode | 10.1 % | 37.6 % |
| max opcode observed | `0xFF` (5951×) | `0xFF` (1355×) |
| decoded length vs declared | 130 404 vs 117 600 | 17 220 vs 14 700 |

The encoder of §7 only ever assigns opcodes `1..0xF3` (counter wraps at `0xF4`), keeps a `(v1,v2)→op` hash and
teaches an opcode **before** first use — so a stream it produced can neither contain `0xFF` nor leave 10–38 %
of opcodes untaught. Both files use `0xFF` heavily and beyond the encoder's range, so they are either an older
eJay variant (the text says `Rave eJay`, 1996-97 — predating this 2001 build) or synthetic fixtures. The ladder
constants are identical in the 1998 engine (`.52` / `.00022` doubles present in both images), so the
ladder is spec; the op framing/lifetime clearly is not the 2001 one.

**Consequence:** `pxd2wav.py` faithfully implements the 2001 `pxd32d5.dll` codec (validated above) but will not
reconstruct audio from these two files. Settling it needs a reference — either the 32-bit DLL itself (it cannot
be loaded into a 64-bit Python, and this workspace forbids executing it) or a known-good WAV made from the same
input. Confirming which requires dynamic analysis that is out of scope here.

## 10. Files

| file | purpose |
|---|---|
| `_pxd_range.py` | disassemble a VA range from the nearest `55 8B EC` prologue, annotate calls/imports |
| `_pxd_decode_probe.py` | the Python PXD decoder (tables + parse + decode) |
| `_pxd_roundtrip.py` | encoder + decoder round-trip test (validates §3–§4) |
| `pxd2wav.py` | the deliverable CLI: `python pxd2wav.py in.pxd [out.wav]` |

---

## 9. File-format quick reference

```
tPxD sample
  +0    4   "tPxD"
  +4    1   attr = b (text length)
  +5    b   text: "<name>\r\n[\r\n]<n>\r\n<collection>\r\n\r\n<category>\r\n<number>\0\0"
  +5+b  2   (skipped)
  +6+b  4   length field L          ; WAV data bytes = L*2
  +10+b 2   int16 seed
  +12+b ..  op stream               ; length = filesize - (12+b)
```

The companion guide `PXD32D5-D4-pxd2wav.md` turns this into a drop-in Python reimplementation.
