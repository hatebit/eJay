# PInit / RWavToTemp / PClose — reverse-engineering notes

Source: targeted disassembly of `PXD32D5-D4.DLL` (a Win32 sound / music-module
engine) with `tools/pxd_dis.py`. Python port: `src/pxd32d5.py`. Verification:
`python src/test_pxd32d5.py`.

The three requested functions are the "render a file" front end of the DLL:

| function | address | role |
|---|---|---|
| `PInit` | `0x10022318` | start the engine (device probe, mixer init, wave params) |
| `RWavToTemp` | `0x10020290` | turn an input file / stream slice, or one numbered sound, into a temp WAV the player can stream |
| `PClose` | `0x10022339` | `AStop(); AEnd();` — shut the engine down |

`RWavToTemp` is 1 of only 2 places the DLL talks to files on the "render"
side; the other (`RWaveLaden`, `0x1001A152`) is its only in-DLL caller and
passes `a3 = 0` (`RWaveLaden` → `RWavToTemp(name, byte_1008E64C, 0, h, off,
len, 0)`), i.e. the normal use is *"convert this file/stream slice into the
canonical temp wave"*.

---

## 1. PInit / PClose

```c
int __usercall PInit@<eax>(double a1@<st0>)   // a1 arrives on the FPU stack
{
  ADevice(0);
  AInit(a1, 0);
  RWaveParam(60, 32000);
  return 0;
}

int PClose() { AStop(); AEnd(); return 0; }
```

Both are wrappers; the interesting work is in the callees:

* **`ADevice(0)`** (`0x10012AEA`) — walks `waveOutGetNumDevs()` /
  `waveOutGetDevCapsA()` looking for 16-bit stereo 44.1 kHz
  (`dwFormats & 0x800`), then falls back through 16-bit 44.1 k stereo open,
  16-bit mono, 8-bit mono 44.1 k, 8-bit mono 22.05 k, storing the achieved
  class (0…3) in `word_1008BBE0` and the chosen `puDeviceID`. Class ≠ 0 later
  sets status bit `0x20`. Rendering to a file does not need the device, so the
  port keeps the bookkeeping and assumes class 0.
* **`AInit(a1, a2)`** (`0x1001149F`) — clears the voice state
  (`dword_10095108[132 * voices]`, `byte_100824E0`, `unk_1008E730`,
  `dword_10082B1C[0..298]`, `dword_1008B774[0..59]`), stores the gain `a1` in
  `dbl_10066968/70/78/80`, sets the mixing rate `dword_100826C4` to 32000
  (29400 when `word_10096D7C == 2`), installs the 25-entry pitch/period table
  `dword_100668F0…dword_10066950`, allocates the working buffers
  (`dword_10096D90`, `dword_1008BBE8`, `dword_1008BBEC`, `dword_1008BBF0[2520]`)
  via `sub_1001186B()`, which **sets `dword_10096DFC = 714132256`**, and then —
  because that magic is now set — calls `sub_100178D4(0)`, which creates the
  critical sections, opens the DirectSound mixer and starts the player thread.
  `sub_100178D4` also sets **`dword_10096CC8 = 1`**, the "rendering allowed"
  flag that guards every `R…` entry point.
* **`RWaveParam(60, 32000)`** —
  `dword_10082B1C[a1] = a2` plus, for `60 ≤ a1 < 129`,
  `dword_10095184[33*a1-1980] = trunc(f(a2/32767*1.33) * 65536)` where
  `f(x) = x` for `x ≤ 1` and `x³` above. (Note the header declares
  `dword_10082B1C[19]` but `AInit` zeroes 299 entries — a real overflow in the
  original; the port allocates 300.)
* **`AEnd()`** — returns immediately unless
  `dword_10096DFC == 714132256`; otherwise `AStop()`, `sub_100179FD(0)`
  (signal + wait for the player thread, `dword_10096CC8 = 0`, delete the
  critical sections), `sub_10011CFB()`, `sub_1001E05D()`, frees
  `dword_1008B8B0`, then disposes of the temp files with
  `OpenFile(name, &buf, 0x200)` — `0x200` is `OF_DELETE`, so `AEnd` deletes
  `FileName`, `byte_1008E64C`, `byte_10082310` and `byte_1008BAE8` — and
  `mixerClose(hmxobj)`. The port removes its two temp paths likewise.
* **`AStop()`** — exported at `0x10014516`. Its body was not recovered by
  the decompiler (only `// 10014516: using guessed type int AStop(void)`
  survived), so it was disassembled from the binary: it zeroes ten playback
  counters, sets `dword_10096D88 = 1` (the player thread's full-reset command,
  `sub_10014589`), waits for the thread (`sub_100144C9`) and returns 1 — not the
  status word. The port reproduces the counter resets and the command register;
  `sub_100144C9` is a no-op because there is no player thread.

`PInit` must therefore be called before `RWavToTemp`, otherwise `AInit` never
runs and `RWavToTemp` returns 0 immediately (see the `dword_10096CC8` guard).

---

## 2. RWavToTemp

```c
int __stdcall RWavToTemp(LPCSTR lpString2,  // input file, or "" with a4
                         LPCSTR a2,         // output name when a3 <= 0
                         int    a3,         // >0: sound number, <=0: convert file
                         HANDLE a4,         // open handle to copy a slice from
                         LONG   a5,         // slice offset
                         LONG   lDistanceToMove, // slice length
                         int    a7);        // append de-click tail + padding
// returns 0 = ok, 1 = failure
```

### 2.1 Guards

```c
if (dword_10096CC8 == 0) return 0;                 // engine not started
if (lpString2 == NULL) return 0;
if (*lpString2 == 0 && a4 == NULL) return 0;       // nothing to read
```

### 2.2 Input acquisition (the `a4` cache)

When `a4` is given the DLL copies `lDistanceToMove` bytes from `a4` at `a5`
into the global temp file `byte_1008BAE8`, using a `CreateFileMapping` +
`MapViewOfFile` of the freshly sized file as the destination of one `ReadFile`.
The triple `(a4, a5, lDistanceToMove)` is cached in
`dword_10096D24/D28/D2C`; the copy is skipped when it repeats. A short read
sets `dword_10096D24 = 0` (cache invalidated) and returns 1. Otherwise
`lpString2` is used directly.

### 2.3 Duration — `AWaveDauer` / 2

`AWaveDauer(path)` (`0x100125A5`) reads 270 bytes of the header and returns a
length normalised to *44100 Hz / 16 bit / stereo* bytes:

* `"RI"` (RIFF): starts from `GetFileSize`, then, if the RIFF chunk size
  `v5 = i32@4` looks consistent (`v5/7+v5 > size > v5-v5/7`) uses it, and if the
  `data` size `v10 = i32@40` looks consistent (`3*v10 > size`, `v10 > 1000`,
  `v10/6 < size`, `v10 < size`) uses that instead. Then
  `wFormatTag != 1` → negate; `nChannels == 1` → ×2; `wBitsPerSample == 8` → ×2;
  `11025 Hz` → ×4; `22050 Hz` → ×2.
* `"tP"`: `4 * i32@((u8)i32@4 + 6)` — a sample count stored in the header.
* anything else: 0.

The `tP` branch is confirmed by the two real files in `data/` (fixtures, not
checked in):

| file | `h[4]` | frame count | `AWaveDauer` = 4·frames | data offset `4+h[4]+8` |
|---|---|---|---|---|
| `bo-test.pxd` | 38 | `i32@44` = 117600 | 470400 | 50 |
| `hyper-test.pxd` | 42 | `i32@48` = 14700 | 58800 | 54 |

So the container is
`"tPxD" + [len: `h[4]` bytes counted from offset 4] + 2 + i32(frames) + 2 + ADPCM data`,
and `4 * frames` really is the duration expressed in 44.1 kHz stereo 16-bit
bytes — which is what `AWaveDauer` promises for every format.

`RWavToTemp` uses `v14 = AWaveDauer(...) / 2`, which for a plain PCM file is
exactly the number of **16-bit mono bytes at 44100 Hz** the temp file will
hold. Because a compressed RIFF (e.g. an MP3-tagged WAV) is negated, `v14`
becomes negative and the original produces a broken/empty file — reproduced
here (see Limitations).

`dword_10096D9C` keeps the real file size; the first 220 bytes (`0xDC`) of the
input are read into a buffer that becomes `session.header` (`a1[28]`).

### 2.4 Stream classification — `sub_10019DEE`

Fields it writes in the session struct (`a1[10]` = type/flags, `a1[3]` = read
offset, `a1[5]`/word = data offset, `a1[9]` = end):

| magic | meaning |
|---|---|
| `tP` | `type = 1`, read offset `= 4 + len(byte@4) + 2 + 4 + 2` |
| `RI`, size > 0 | `type = 0 \| flags`, scan for the `data` tag |
| otherwise | `type = 2` ("unknown") |

RIFF branch: `fmt` chunk size `w = u16@16`, clamped to 16 when `< 16` or
`> 64`; data offset `w + 28`; scans `w + 20 … w + 100` two bytes at a time for
`"data"` (`24932`, `24948` = `'d','a'`,`'t','a'`); then flags
`0x20` stereo (`u16@22 == 2`), `0x10` 8 bit (`u16@34 == 8`), and the rate:
`0x08` = 11025, `0x04` = 22050, `0x02` = 44100/other. If the `data` size looks
consistent the stream is cut there. Finally `a1[3] = a1[5] = data offset`.

Note the collision: "unknown" is encoded as `2`, which is also the "44100"
flag, so a caller cannot tell them apart — the port keeps a separate
`has_riff` flag.

### 2.5 Output file

* `a3 <= 0`: output name is `a2` verbatim.
* `a3 > 0`: `wsprintf("%spxd32p%c.tmp", PathName, a3 + 99)`, i.e.
  `<PathName>pxd32p` + character `a3+99` (`a3 = 1` → `'d'`). The sound tables
  indexed `65*(a3-1)` are also read: `dword_1008E828` (volume →
  `session.volume = 2*v`, Q16 with 0x10000 = unity), `dword_1008E830`
  (pitch → resampling rate), `dword_1008E82C` (reverse/loop flag).
  `v14` is also clamped to `2*75600` (151200).

The file is **preallocated** with `SetFilePointer` + `SetEndOfFile`:

| path | size |
|---|---|
| `a3 <= 0` | `v14 + 75632 + header(44) + 64` |
| `a3 > 0` | `4*75600 + 64` |

then reopened read/write and mapped. `session.out_ptr` points at
`base + header`, `session.region` is the usable region. Everything is
zero-filled, so any area the renderer does not reach is silence.

### 2.6 Branch `a3 <= 0` — convert the stream

```
do {
    memset(dst + write_offset, 0, 75696);          // 0x127B0
    produced = 0;
    (type==1 ? sub_100147C2 : sub_100148D1)(session);   // decode one block
    frames = produced / 4;                         // stereo 16-bit frames
    for (i = 0; i < frames; ++i) {                 // keep the LEFT channel
        *(u16*)(dst + 2*i) = *(u16*)(dst + 4*i);
    }
    write_offset += 2 * frames;
} while (frames != 0 && write_offset < v14 && read_offset < stream_end);
```

So the decoder always produces 44.1 kHz **stereo 16-bit**, and the converter
throws the right channel away *in place* (safe: the write index `2i` never
overruns the unread source index `4i`). Result: a mono 16-bit/44100 stream.

One block is bounded by `session[12]` (`75632` bytes ⇒ 18908 frames; the
`memset` covers 75696 so the decoder may overrun by a few samples), and
`session[14]` advances by `2 * frames` per iteration.

### 2.7 Branch `a3 > 0` — render one sound

Single pass (no loop):

1. `sub_100147C2` / `sub_100148D1` decodes into `dword_10096D90`
   (`4*75600` bytes).
2. Resample with a 14-bit fraction linear interpolator into `dword_1008BBEC`:
   `frac = 0; for each output sample: cur = src[pos], nxt = src[pos+4];
   out = ((0x3FFF-frac)*cur + frac*nxt) >> 14; frac += step;
   pos += 4*(frac>>14)` where `step = dword_100668EC[13 - pitch]`
   (`0x4000` = unity). `dword_1008E82C` selects the backward variant
   (starts at the last frame, walks backwards, interpolates with the previous
   sample). Output count is `frames << 14 / step`, clamped to 75600.
3. `sub_10021272` derives the effect coefficients from
   `dword_10090758, 75C, 760, 764, 768, 770, 774, 778` — reproduced verbatim
   in `Engine._update_effect_params`.
4. If `dword_10082FE0 > 0 && dword_10083540 != 0` the tail is extended by
   `dword_10082FE0 + dword_10090764` samples (clamped to 75600) and zeroed.
5. `sub_1000E3E0(out, out+2*n, 0, dword_1008BBEC)` runs the echo/chorus/
   reverb chain and writes the final mono data.

The `dword_100668EC` table is the same 25-entry pitch/rate table as
`dword_100668F0…10066950`, but shifted one entry earlier in memory (index 13 ⇒
`0x4000` ⇒ unity, index 1 ⇒ `0x8000` ⇒ double rate, index 25 ⇒ `0x2000` ⇒
half rate). Entry 0 is not visible in the decompilation; the port extrapolates
34528 from the neighbouring ratio.

### 2.8 Tail (`a7 != 0`)

Applied to both branches after rendering:

```
for (j = 0; j < 128; ++j) {           // de-click ramp on the last 128 samples
    p = end - 2*(j+1);
    *(i16*)p = (j * *(i16*)p) >> 7;   // last sample -> 0
}
blocks = v14 / (2*4725) + 1;          // pad to 9450-byte blocks, max 16
if (blocks > 16) blocks = 16;
zero [v14, blocks*9450);
v14 = blocks * 9450;
```

9450 bytes (`2 * dword_1004B2D0`, `dword_1004B2D0 = 4725`) is 4725 samples,
roughly 0.107 s at 44100, so this rounds the temp file up to a whole mixer
block and fades the seam.

### 2.9 Header + truncate

```
if (v14 > 0) {
    hFile = CreateFile(out, OPEN_ALWAYS);
    if (header_size) {                        // dword_10096CD8 == 4
        word_100823F8 = 2; hObject = hFile; dword_1008E644 = v14;
        sub_10013198();                       // 44-byte RIFF header
        word_100823F8 = 0; hObject = NULL;
    }
    SetFilePointer(hFile, header_size + v14);
    SetEndOfFile(hFile);                      // drop the preallocated slack
}
return 0;
```

`sub_10013198` builds the header at the *current* file pointer:

```
"RIFF" size "WAVE" "fmt " 16 | tag=1 | channels | rate | avg | align | bits
"data" data_size
```

with `channels = 1` (because `word_100823F8 = 2`), `rate = 44100`,
`align = 2`, `bits = 16`, `avg = 88200`. So the temp file is a plain **mono
16-bit 44.1 kHz** WAV, and `data_size == v14`. When `dword_10096CD8 != 4`
(`header_size == 0`) the temp file is raw mono PCM with no header.

If `v14` ended up 0 the header is not written and the file keeps its
preallocated size — a quirk of the original that the port preserves.

---

## 3. The decoders (what is and is not reproducible)

`sub_100147C2` / `sub_100148D1` are thin wrappers: they copy the 132-byte
session head, and — for `a1[37]` (subtype) in `3 … 127` or `≥ 128` — decode
*twice* with `a1[18].hi = 1/2` and a pan-weighted volume
(`(2*a1[37])` resp. `(2*(256-a1[37])) \* volume >> 8`) to build a stereo pair;
otherwise they call the single-pass core directly. `RWavToTemp` always sets
`a1[37] = 0`, so only the single-pass core `sub_100149E0` (16-bit) /
`sub_10014BDB` (other) runs. Those functions only pre-split the destination
region (an overlap of 64 bytes at the end of the mapped region is saved and
restored, because the decoder may run past the end), publish the window in
globals (`dword_1008B71C` = read pointer, `dword_1008B758` = read end,
`dword_1008B740` = write pointer, `dword_1008B754` = write end,
`dword_10093A78` = `(pan * volume) >> 8`) and call the real decoder.

That decoder is `sub_10016361` (16-bit out) / `sub_100165A9` (other). For the
`tP` streams that `RWavToTemp` handles (`a1[10] == 1`) the 16-bit variant is
used, and it turned out to be **fully recoverable**: both of its tables are
built by code, not shipped in `.data`.

### 3.1 The shared delta table (`dword_1008E350`, `sub_10011EFF`)

A 256-entry `int16` ladder of DPCM step sizes, index 128 = 0, symmetric:

```
v1 = 2.2; v20 = 1.0565; t[128] = 0;
for (j = 1; j < 128; ++j) {
    t[j+128] = (j >= 6 ? (int)(v1 - 0.52) : 1) + t[j+127];
    v1 *= v20; v20 -= 0.00022;
}
for (k = 1; k < 129; ++k) t[128-k] = -t[k+128];
for (m = 0; m < 256; ++m)  t[m] *= 2;
```

It peaks at ±25266, so nothing wraps. `t[256]` is never written, which is why
`t[0] == 0`. The port exposes it as `pxd32d5.DELTA_TABLE`.

### 3.2 The code book (`dword_1008B750`)

`sub_100149E0` publishes `session[0]` as the book pointer; in practice that is
the 8100-byte (`malloc(0x1FA4)`) player struct, whose **entry 0 is a 6-word
silent waveform** written by `sub_10011EFF` (`0,0,0,0,0,0xFFFF`). Entries are
16 bytes apart (`book + 16 * index`), hold `int16` **deltas** terminated by
`0xFFFF`, and the stream itself defines the other 255 entries on the fly.

### 3.3 Byte code (`sub_10016361`, verified against the binary)

| byte | meaning |
|---|---|
| `0x00…0xF3` | play entry `byte`: walk its deltas, `acc += delta`, emit |
| `0xFF` | one step: `acc += DELTA_TABLE[next_byte]`, emit |
| `0xF4…0xFE` | define entry `next_byte` with `opcode-0xF3` (1…11) deltas taken from `DELTA_TABLE[byte]`, write `0xFFFF`, then play it |

Emission (hand-written asm in the DLL):

```
prod   = acc * gain;                    // gain = (pan * volume) >> 8
if (overflow) sample = prod > 0 ? 0x7FFF : 0x8000;
else          sample = (prod >> 16) & 0xFFFF;
*dst += sample;                         // 16-bit add, saturate on overflow
```

The destination is the **left** channel only (`esi += 4` per sample); the right
channel keeps the zeroes from the `memset`, which is exactly why the
`a3 <= 0` loop then keeps every fourth byte. The 16-bit integrator lives in
`session[4]` (word) and survives across blocks, because `sub_100149E0` writes
it back after each call.

Two quirks are reproduced rather than fixed: the overflow clamp picks its
limit from the sign of the *wrapped* sum (a positive overflow becomes
`0x8000`), and the `0xF4…0xFE` count is `(char)(opcode + 13)`, i.e. 1…11.
Hex-Rays printed it as a 257…267-word copy, which is what the 16-bit `char`
value looks like before truncation.

The other variant (`sub_100165A9`, 8-bit destinations) is never reached from
`RWavToTemp`, so it is not ported.

The RIFF/PCM path (`_decode_pcm`) converts 8/16 bit, mono/stereo,
11.025/22.05/44.1 kHz input to 44.1 kHz stereo 16-bit with sample-and-hold
upsampling, so the same left-channel extraction applies.

`sub_1000E3E0` (the echo/chorus/reverb chain, ~700 lines) is still not ported:
it consumes `sub_10021272`'s coefficients plus delay buffers and codebooks.
Only the coefficient computation is ported. `Engine._effects_chain` copies the
resampled data through and is the single place to plug in a future port.

---

## 4. Session struct (`dword_1008E380`)

`sub_1001186B` allocates it with `malloc(0x1FA4)` (8100 bytes) and zeroes it;
`RWavToTemp` only touches the first 132 bytes (the size `sub_100147C2`
`qmemcpy`s):

| off | index | meaning |
|---|---|---|
| 0 | `a1[0]` | waveform/codebook pointer (used by the ADPCM decoder) |
| 4 | `a1[1]` | per-channel state pointer (stereo split) |
| 8 | `a1[4]` (word) | volume word handed to the decoder |
| 12 | `a1[3]` | read offset in the source |
| 20 | `a1[5]` (word) | data offset (set by `sub_10019DEE`) |
| 36 | `a1[9]` | stream end (file size, cut to the data chunk) |
| 40 | `a1[10]` | stream type/flags |
| 44 | `a1[11]` | bytes remaining |
| 48 | `a1[12]` | decode block size (starts at 75632) |
| 52 | `a1[13]` | bytes produced by the last decode |
| 56 | `a1[14]` | write offset into the destination |
| 68 | `a1[17]` | pan (`512` file path, `256` sound path) |
| 72 | `a1[18]` hi word | channel mode 1/2 during the stereo split |
| 74 | `a1[37]` (word) | subtype (`0` in `RWavToTemp`, `2` = scratch +2) |
| 84 | `a1[21]` | cleared |
| 112 | `a1[28]` | first 220 bytes of the input |
| 116 | `a1[29]` | destination data pointer |
| 120 | `a1[30]` | source mapping base |
| 124 | `a1[31]` | volume, 16.16 (`0x10000` unity) |
| 128 | `a1[32]` | destination region size |

## 5. Globals used

| symbol | use |
|---|---|
| `dword_10096CC8` | engine started — `RWavToTemp` returns 0 when clear |
| `dword_10096DFC` | `714132256` = buffers/thread alive (`AEnd` guard) |
| `dword_10096CD8` | output kind; `4` ⇒ write a 44-byte RIFF header |
| `dword_10096D9C` | size of the input file |
| `dword_10096D24/28/2C` | cached `(handle, offset, length)` of the stream copy |
| `byte_1008BAE8` | temp file for stream slices |
| `byte_1008E64C` | the "canonical" temp wave (`RWaveLaden` output) |
| `PathName` | directory prefix for `pxd32p%c.tmp` |
| `dword_1004B2EC` | 75600, engine buffer in frames |
| `dword_1004B2D0` | 4725, half a mixer block |
| `dword_1008E828/82C/830` | per-sound volume / loop-reverse / pitch (`65*(n-1)`) |
| `dword_100668EC` | pitch → rate table (`0x4000` unity) |
| `dword_10090758…78` | effect parameters for `sub_10021272` |
| `word_100823F8` | header flavour; `2` ⇒ mono, `3` ⇒ extra chunk |
| `dword_1008E644` | data length handed to `sub_10013198` |
| `hObject` | file handle `sub_10013198` writes to |

---

## 6. Using the port

```python
import pxd32d5

pxd32d5.PInit(1.0)              # a1 is the engine gain (x87 argument in the DLL)
pxd32d5.engine.output_kind = 4  # emit a 44-byte RIFF header
pxd32d5.RWavToTemp("in.wav", "out.wav", 0, None, 0, 0, 0)
pxd32d5.PClose()
```

or per-instance:

```python
eg = pxd32d5.Engine()
eg.ADevice(); eg.AInit(1.0, 0); eg.RWaveParam(60, 32000)
eg.output_kind = 4
eg.RWavToTemp("in.wav", "out.wav", 0, None, 0, 0, 0)
```

`Engine.decode_hook` lets another decoder be plugged in
(`hook(session, out_buffer, base, max_frames) -> bytes_written`, stereo 16-bit
frames) and `Engine._effects_chain` is the extension point for `sub_1000E3E0`.

### CLI

`pxd2wav.py` wraps the same sequence (`PInit` -> `RWavToTemp(a3 = 0)` -> `PClose`)
for batch conversion:

```
python pxd2wav.py song.pxd                 # song.wav next to the input
python pxd2wav.py *.pxd *.wav -o out/ -t   # batch, de-click tail + padding
python pxd2wav.py song.pxd --raw -o out/   # headerless mono 16-bit PCM (.pcm)
```

Options: `-o/--outdir`, `-t/--tail` (the `a7` argument), `--raw`
(`dword_10096CD8 != 4`, no RIFF header), `-f/--force` (never overwrites by
default), `-g/--gain` (`PInit`'s `a1`), `-q/--quiet`. Exit status is 0 only when
every input converted; each file reports frames, duration and size.

## 7. Verified behaviour

`test_pxd32d5.py` covers, against expected values derived from the
decompiled arithmetic:

* stereo 44.1 k/16 → 8820-byte data chunk of left-channel samples, header
  `1 ch / 44100 / 16 bit / 88200 B/s / align 2`;
* mono 22.05 k → ×2 sample-hold, 2205 frames → 8820 bytes;
* mono 8-bit 11.025 k → ×4 rate and ×2 bit conversion, `(b-128) << 8`;
* `a7 = 1` → 128-sample ramp (last sample 0) and padding to 9450 bytes;
* the `a4` handle path (byte-identical temp copy, same output);
* guards (engine not started, `NULL`/empty name, missing file → 1);
* `AEnd`/`PClose` teardown and the `RWaveParam(60, 32000)` curve value;
* the `tP` header parse and `AWaveDauer` against the shape of the real
  `data/bo-test.pxd` / `data/hyper-test.pxd` (470400 / 58800; fixtures not
  checked in);
* a hand-built `tP` stream (`0xF5 0x01 0x80 0x81 / 0x01 / 0xFF 0x82`) that
  produces exactly `[0, 4, 4, 8, 16]` for gain 131072;
* the CLI: conversion, `--raw`, overwrite refusal / `--force`, missing input,
  and a full `bo-test.pxd` run producing 235244 bytes;
* full decode of `bo-test.pxd` → **117600 frames** and `hyper-test.pxd` →
  **14700 frames**, i.e. exactly the frame count each header declares, with
  the input consumed to its last byte and no clipping (`±14008` / `±12604`).
  A wrong opcode length anywhere in the stream would desync and break both
  of those numbers.

## 8. Limitations / open items

* `sub_100165A9` (the 8-bit destination variant of the decoder) is not
  ported; `RWavToTemp` never selects it.
* The decoder is allowed to overrun a block by up to a few samples in the DLL
  (it only checks the bounds when a code-book entry finishes, relying on the
  64-byte overlap hack). The port keeps that behaviour but caps the overrun at
  64 frames of buffer slack.
* `sub_1000E3E0` (echo/chorus/reverb) is a pass-through; `_update_effect_params`
  (its coefficient stage) *is* ported.
* `ADevice` does not probe real waveOut devices. `AStop` is ported from the
  disassembly, but its wait on the player thread (`sub_100144C9`) is a no-op
  because the port has no thread.
* Compressed RIFF inputs (`wFormatTag != 1`) make `AWaveDauer` negative in the
  original; the port keeps that (the render loop then never fills `v14` and no
  header is written), which reproduces the original's broken output rather
  than fixing it.
* The 64-byte tail-preservation trick of `sub_100149E0` is unnecessary with the
  Python buffers and is documented rather than emulated.
