# PXD → WAV: a complete Python reimplementation

How `pxd32d5_d4.dll` (the audio engine of Dance eJay3) turns a `tPxD` sample into a `.wav` file, and a
drop-in Python port. Evidence addresses refer to `pxd32d5_d4.dll` (image base `0x10000000`); the analysis
trail and confidence tags are in [`ongoing.md`](ongoing.md) and the other `PXD32D5-D4-*.md` files.

The reimplementation is [`pxd2wav.py`](pxd2wav.py) (≈130 lines, standard library only). Run it with:

```
python pxd2wav.py input.pxd [output.wav]
```

---

## 1. The two formats

**Input — the `tPxD` sample container.** A `tPxD` file is a small text header followed by a compressed op
stream. The magic is the four bytes `t P x D`; the loader is the unexported function at `0x1000F115`
(the `tP` branch at `0x1000F1E9`–`0x1000F260`). **[certain]**

```
+0    4   "tPxD"
+4    1   b      – length of the text block that follows
+5    b   text   – sample name, collection, category, a numeric field, each \r\n-terminated
+5+b  2   (skipped)
+6+b  4   L      – length field; the WAV 'data' size is L*2 bytes
+10+b 2   seed   – int16 initial value of the running sample
+12+b ..  op stream (length = filesize - (12+b))
```

In the two sample files bundled with this workspace `b` is `0x26` / `0x2A` and `L` is 117 600 / 14 700.

**Output — a standard WAV.** 44.1 kHz, mono, 16-bit PCM, written by `0x1000F825`. The `data` chunk is
`2*L` bytes; the first sample is the `seed`, the rest is the decoded op stream. (The header byte map is in
§4.) **[certain]**

---

## 2. The codec

The audio is a **table-driven delta codec**: a 256-entry signed "ladder" of step sizes, and a pair of
256-byte dictionaries `T1`/`T2` that map each opcode to two ladder indices. It is exactly the inverse of the
WAV→PXD encoder at `0x1000FB3E`; the tables are built once at start-up by `0x1000FFD7`.

### 2.1 The delta ladder `D[256]`

Builder `0x1000FFD7`, object at `0x1004E2D0`. `W[0] = 0`; then a geometric-but-flattening sequence
(`W[i]` at `obj + 0x100 + 2i`), then the signed table mirrors it. **[certain]**

```python
W[0] = 0
v, r = 2.1, 1.056840...            # double 0x400199999999999A and 0x3FF0E76C8B439581
for i in range(1, 0x80):
    W[i] = W[i-1] + 1                          if i < 6
           else int(W[i-1] + v - 0.52)         # trunc; 0.52 = double @ 0x100432E8
    v = v * r
    r = r - 0.00022                            # double @ 0x100432E0

D[0x80 - i] = -W[i]   for i in 1..0x80         # negative half
D[0x80 + j] =  W[j]   for j in 0..0x7F         # positive half
```

`D` is a symmetric signed ladder around `0x80`:

| opcode | meaning | value |
|---|---|---|
| `0x80` | zero step | `D = 0` |
| `0x81`…`0xFF` | increasing positive steps | `1, 2, 3, 4, 5, 7, 9, …, 12051` |
| `0x7F`…`0x01` | increasing negative steps | `-1, -2, -3, …, -11643` |
| `0x00` | largest negative step (`-W[0x80]`) | unused — opcode `0x00` is the run opcode |

(`W[0x80]` is read from the file but never used, because opcode `0x00` is special-cased. It is 0 here.)

### 2.2 Two samples per opcode

Every opcode produces **two** samples. A running value `cur` (int16) is advanced by the ladder and the
resulting value, shifted left twice and truncated to 16 bits, is the PCM sample:

```python
cur = (cur + D[idx]) & 0xFFFF
pcm = (cur << 2) & 0xFFFF          # little-endian word in the file
```

`T1[op]` selects the ladder index for the first sample, `T2[op]` for the second. Both start at 0, so a
never-taught opcode uses `D[0]` (zero). **[certain]**

### 2.3 The three opcode kinds

Decode dispatch is at `0x1000F96C` (`0x00`), `0x1000F9DE` (`0xF5`) and `0x1000FA91` (everything else).
**[certain]**

| opcode | bytes consumed | samples out | behaviour |
|---|---:|---:|---|
| `0x00` | 1 | 5 | emit the **current** value five times (`off += 10`); a silence/run op |
| `0xF5` | 4 | 2 | `0xF5 sel v1 v2`: teach `T1[sel]=v1`, `T2[sel]=v2`, then emit the pair using the new entries |
| other | 1 | 2 | emit the pair using the remembered `T1[op]`/`T2[op]` |

Pseudocode (faithful to the DLL):

```python
cur = seed
T1 = [0] * 256
T2 = [0] * 256
while i < len(stream):
    op = stream[i]; i += 1
    if op == 0x00:
        for _ in range(5):
            emit(cur)
    elif op == 0xF5:
        sel, v1, v2 = stream[i], stream[i+1], stream[i+2]; i += 3
        T1[sel] = v1; T2[sel] = v2
        cur = s16(cur + D[v1]); emit(cur)
        cur = s16(cur + D[v2]); emit(cur)
    else:
        cur = s16(cur + D[T1[op]]); emit(cur)
        cur = s16(cur + D[T2[op]]); emit(cur)
```

where `emit(cur)` appends `struct.pack("<H", (cur << 2) & 0xFFFF)`.

### 2.4 Worked start (`bo-test.pxd`)

The stream opens with a long `0x00` run with an all-zero `T1`/`T2`, so it decodes to silence until the first
`0xF5` teaches a non-zero step:

```
00 00 00 ...            -> 5 zero samples each
F5 02 7F 7E             -> T1[0x02] = -1, T2[0x02] = -2; emit cur-1, cur-2
02                      -> (plain op) emit cur-1, cur-2 again
F5 03 7E 7B             -> teach opcode 0x03 the steps -2, -5; emit them
...
```

That is why the `bass`/`hyper` samples recover as structured audio with a quiet lead-in.

---

## 3. Why the decode runs the whole stream but the file is shorter

The decode loop's only bound is the **input stream length** (`0x1000F94A`, comparing the read index to
`A[0x18] = filesize - data_off`), so the DLL decodes every opcode. The output is a **file mapping** sized
`L*2 + 44` (`0x1000EEA8`); Windows rounds file-mapping sizes up to the 64 KiB allocation granularity, so the
mapping can hold the full decode. The final `_hwrite` (`0x1000EFED`) writes exactly `L*2 + 44` bytes, so the
file is `header(44) + data(L*2)` and any decoded samples beyond the declared `data` size are discarded.
**[certain]** for the mechanics; the 64 KiB rounding is the standard Windows behaviour, not code in the DLL.

For the bundled samples the raw decode is 260 810 / 34 442 bytes but the declared `data` is 235 200 / 29 400,
so the port decodes the full stream and slices to the declared size.

---

## 4. The WAV byte map (mono, 16-bit, 44.1 kHz)

Written field-by-field at `0x1000F825` (`0x1000F895`–`0x1000F92A`). It is a **standard** RIFF/WAVE header —
the fmt chunk size is a 4-byte field (`0x00000010`, written as a word `0x10` at 16 and a word `0` at 18), so
the fmt fields start at 20. **[certain]**

| off | bytes | value | meaning |
|---:|---:|---|---|
| 0 | 4 | `RIFF` | |
| 4 | 4 | `L*2 + 36` | RIFF size (file size − 8) |
| 8 | 4 | `WAVE` | |
| 12 | 4 | `fmt ` | |
| 16 | 4 | `0x00000010` | fmt chunk size |
| 20 | 2 | `1` | format tag (PCM) |
| 22 | 2 | `1` | channels (mono) |
| 24 | 4 | `44100` | sample rate |
| 28 | 4 | `88200` | byte rate (`44100 × blockAlign`) |
| 32 | 2 | `2` | block align |
| 34 | 2 | `16` | bits per sample |
| 36 | 4 | `data` | |
| 40 | 4 | `L*2` | data chunk size |
| 44 | 2 | seed sample | `seed << 2` |
| 46 | … | decoded op samples | filled by §2 |

The engine's own reader (`0x1000F115` WAV branch) reads the same offsets; Python's `wave` module reads the
output directly as `1 ch, 16 bit, 44100 Hz`.

---

## 5. The reimplementation

`pxd2wav.py` (in this directory) is the whole thing. The three pieces:

```python
import struct

K, K2, V0 = 0.52, 0.00022, 2.1
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]   # ~1.056840

def build_delta_table():                       # 0x1000FFD7
    W = [0] * 0x81
    v, r = V0, R0
    for i in range(1, 0x80):
        W[i] = W[i-1] + 1 if i < 6 else int(W[i-1] + v - K)
        v = v * r
        r = r - K2
    D = [0] * 256
    for i in range(1, 0x81):
        D[0x80 - i] = -W[i]
    for j in range(0x80):
        D[0x80 + j] = W[j]
    return D

DELTA = build_delta_table()

def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x

def parse_tpxd(raw):                           # 0x1000F115 (tP branch)
    if raw[:4] != b"tPxD":
        raise ValueError("not a tPxD file")
    attr = raw[4]
    p = 4 + attr + 2
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p + 4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p + 6:]

def decode(raw):                               # 0x1000F825
    data_bytes, seed, stream = parse_tpxd(raw)
    out = bytearray(struct.pack("<H", (seed << 2) & 0xFFFF))
    cur, T1, T2, i = seed, [0]*256, [0]*256, 0
    def emit():
        out.append(((cur << 2) & 0xFFFF) & 0xFF)
        out.append((((cur << 2) & 0xFFFF) >> 8) & 0xFF)
    while i < len(stream):
        op = stream[i]; i += 1
        if op == 0x00:
            for _ in range(5):
                emit()
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel], T2[sel] = v1, v2
            cur = _s16(cur + DELTA[v1]); emit()
            cur = _s16(cur + DELTA[v2]); emit()
        else:
            cur = _s16(cur + DELTA[T1[op]]); emit()
            cur = _s16(cur + DELTA[T2[op]]); emit()
    return bytes(out[:data_bytes]), data_bytes
```

The WAV writer is a literal transcription of §4:

```python
def wav_header(data_len):
    return (b"RIFF" + struct.pack("<I", data_len + 0x24) + b"WAVE" +
            b"fmt " + struct.pack("<I", 0x10) +
            struct.pack("<H", 1) + struct.pack("<H", 1) +      # PCM, mono
            struct.pack("<I", 44100) + struct.pack("<I", 88200) +
            struct.pack("<H", 2) + struct.pack("<H", 16) +
            b"data" + struct.pack("<I", data_len))

def pxd_to_wav(raw):
    pcm, data_len = decode(raw)
    return wav_header(data_len) + pcm
```

---

## 6. Verification

```
$ python pxd2wav.py ../bo-test.pxd ../bo-test.wav
../bo-test.pxd -> ../bo-test.wav  (235200 bytes PCM, 2.667 s mono 16-bit 44.1 kHz)
$ python pxd2wav.py ../hyper-test.pxd ../hyper-test.wav
../hyper-test.pxd -> ../hyper-test.wav  (29400 bytes PCM, 0.333 s mono 16-bit 44.1 kHz)

$ python -c "import wave; w=wave.open('../bo-test.wav'); print(w.getnchannels(), w.getsampwidth()*8,
             w.getframerate(), w.getnframes())"
1 16 44100 117600
```

Output files are exactly `44 + L*2` bytes (235 244 / 29 444), matching the mapping size the DLL writes.

**Status.** The codec above is self-consistent: `_pxd_roundtrip.py` encodes a sine with the §7.5 encoder and the
§5 decoder reproduces it to within the ladder's quantisation (mean error 2/8192). The two `-test.pxd` files in
the repo root, however, do **not** decode to audio with it — their `cur` is a random walk. They use opcode `0xFF`
heavily and leave 10–38 % of opcodes never taught, neither of which this DLL's encoder can produce, so they look
like a different/older variant (their text says `Rave eJay`, 1996-97) or synthetic fixtures. See
[`ongoing.md`](ongoing.md) §9. Verifying against a known-good WAV (or the 32-bit DLL, which is out of scope
here) is the remaining step.

---

## 7. Gotchas

* **`cur` is 16-bit.** Every ladder update wraps (`& 0xFFFF`); read it back as a signed int16 before use.
* **`cur << 2` is a truncating 16-bit shift**, not a saturating one — mask to `0xFFFF` when packing.
* **Both `T1` and `T2` start at 0**, so an untrained opcode emits the zero step (`D[0] = 0` here). Training is
  entirely stream-driven via the `0xF5` packets; there is no separate table to load.
* **The `0x00` opcode emits five samples**, not one — a run of silence/long constant runs. It never advances
  `cur`.
* **`data_bytes` can be smaller than the raw decode.** Decode the whole stream, then slice; don't stop early
  (the declared boundary can fall inside an opcode's sample pair).
* **Only `tPxD` is handled here.** The loader also accepts RIFF/WAVE input (`0x4952` branch) for the reverse
  direction; compressed `SZDD` (`0x44445A53`) samples are expanded by `ALoad` via `LZ32` before this codec
  (`PXD32D5-D4-engine.md` §6), which is a separate concern.

---

## 8. Address index (evidence trail)

| Address | What |
|---|---|
| `0x1000F115` | container parser (tP branch `0x1000F1E9`; RIFF branch `0x1000F265`) |
| `0x1000FFD7` | delta-ladder + quantiser builder (object `0x1004E2D0`) |
| `0x1004E0D0` / `0x1004E1D0` | `T1` / `T2` dictionaries |
| `0x1004E2D0` / `0x1004E2D0+0x204` | `D` ladder / encoder quantiser |
| `0x100564D8` / `0x100564D4` | pointers to `D` / quantiser |
| `0x1000F825` | PXD → WAV driver (header `0x1000F895`–`0x1000F92A`, loop `0x1000F94A`) |
| `0x1000F96C` / `0x1000F9DE` / `0x1000FA91` | opcode `0x00` / `0xF5` / plain dispatch |
| `0x1000EEA8` / `0x1000EFED` | create output mapping / write file |
| `0x1000F5C0` / `0x1000F6B0` / `0x1000F792` | encoder index / op lookup / teach |
| `0x1000FB3E` | WAV → PXD driver (the inverse; confirms every field) |
