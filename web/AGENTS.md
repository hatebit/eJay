# AGENTS.md — working in `web/`

This folder holds a static page, `index.html`, that converts a dropped `.pxd`
file to a downloadable `.wav` entirely in the browser (no backend, no build
step, no dependencies). Its decoder is a **hand port of a subset of the Python
code in `../work/src/`**.

## Golden rule: update the JS only when asked

The Python port in `../work/` is the source of truth and it keeps
evolving. **Do not change the JavaScript decoder just because the Python
changed, or because you noticed a difference.** Only sync the JS when the
person explicitly asks (e.g. "update the JS from the Python", "port the new
change to the web page").

* If you spot drift while doing something else, **mention it** in your reply
  and leave the code alone.
* Unrelated requests (styling, layout, UI, copy) must not touch the decoder
  `<script>`.
* Never edit anything under `../work/` from here. It is a separate
  project with its own `AGENTS.md`; read from it, do not write to it.
* Do not run the analysed engine DLL or any code from it (same safety
  rule as the Python project; the binary is not checked in).

## Layout

| path | role |
|---|---|
| `index.html` | the whole app: markup, CSS, decoder script, UI script |
| `background.webp` | page background (CSS `cover`, centered, fixed) |
| `background-original.jfif` | original background source image |

`index.html` has two `<script>` blocks, in this order:

1. **Decoder core** — defines `const PXD = {...}` exposing
   `pxdToWav(Uint8Array) -> { wav: Uint8Array, frames, seconds }`. It is pure
   (no DOM, no `fetch`, no globals other than `PXD`) so it can be extracted and
   tested headlessly. Keep it that way.
2. **UI** — drag and drop, file input, result rows, download links. It only
   calls `PXD.pxdToWav`.

Keep everything in the single `index.html` (the page must work by opening the
file directly, `file://`, with no server).

## What is ported, and from where

The JS reproduces the path `pxd2wav.py` takes for a `.pxd` input:
`PInit` → `RWavToTemp(src, dst, 0, None, 0, 0, tail=0)` → `PClose`, with
`output_kind = 4` (44-byte RIFF header) and gain 1.0.

| JS (`index.html`) | Python (`work/src/pxd32d5.py`) |
|---|---|
| constants (`DECODE_BLOCK`, `SCRATCH_CLEAR`, `DECODER_SLACK`, `DECODE_TAIL`, `BOOK_SIZE`, …) | module constants of the same names |
| `GAIN = (512 * 0x10000) >> 8` | `Session.gain` = `(pan * volume) >> 8` with `pan = 512`, `volume = 0x10000` (file path) |
| `wrap16` | `_wrap16` |
| `makeDeltaTable` / `DELTA_TABLE` | `_delta_table` / `DELTA_TABLE` (`sub_10011EFF`) |
| `emit` | `emit` |
| `decodeTp` | `Engine._decode_tp` (`sub_10016361`) |
| header checks and frame count at the top of `pxdToWav` | `awave_dauer`, "tP" branch (`AWaveDauer`) |
| `p += buf[p]; p += 2; …` (start of audio) | `Engine._parse_header`, "tP" branch (`sub_10019DEE`) |
| conversion `for (;;)` loop in `pxdToWav` | `Engine._convert_stream` + `_compact_left_channel` |
| output preallocation and final slice | `Engine.RWavToTemp` (`file_size`, `final`) |
| `writeRiffHeader` | `Engine._write_riff_header` (`sub_10013198`) |

**Deliberately not ported** (do not add these unless asked): RIFF/WAVE PCM input
(`_decode_pcm`, the RIFF branch of `_parse_header` / `awave_dauer`), the
`a3 > 0` sound-render path (`_render_sound`, `_pitch_step`,
`_update_effect_params`, `_effects_chain`), the `a7` de-click tail
(`_append_tail`), `--raw` output, the temp-file/stream-cache handling, and the
`APlay`/`PPlay`/`AStop`/`AEnd` playback queue. A non-`tP` input is reported as
an error in the UI instead.

## How to update the JS from the Python (when asked)

1. **Find what changed.** Look at the relevant Python function(s) in the table
   above (`git diff`/`git log` on `work/src/pxd32d5.py` helps). Decide
   whether the change affects the ported path at all. If it only touches code
   that is not ported (see the list above), say so and change nothing.
2. **Port it faithfully, not idiomatically.** Preserve the original's
   behaviour, including its quirks (see the invariants below). Keep the
   comments that cite the original symbol (`sub_10016361`, `dword_…`).
3. **Keep the function mapping 1:1** so the next sync stays easy: same
   structure, same order of operations, names that mirror the Python ones
   (camelCase of the same name).
4. **Update this file** if the table, the "not ported" list or an invariant
   changed.
5. **Verify** (next section) and report the real numbers.

### C semantics to keep (do not "clean up")

The Python port documents these in `work/AGENTS.md`; the JS must behave
identically.

* **int16 wrap-around.** Python's `_wrap16` is `(v << 16) >> 16` here. The
  DPCM accumulator is a 16-bit value; it wraps, it does not clamp. `Int16Array`
  stores and `DataView.setUint16(..., v & 0xFFFF)` already wrap.
* **Truncating division.** Python's `_idiv` truncates toward zero. In JS use
  `Math.trunc(a / b)` — never `Math.floor`, never `//`-style flooring. Python's
  `>>` is an arithmetic (flooring) shift, which matches JS `>>` only while the
  operand fits in int32; use `Math.floor(x / 2 ** n)` when it might not.
* **Overflow clamp in `emit`.** The clamp is chosen from the sign of the
  *wrapped* sum, so a positive overflow becomes `0x8000`. Reproduced on purpose.
* **Opcode count.** Opcodes `0xF4…0xFE` copy `opcode - 0xF3` deltas
  (1…11). The decompiler's `opcode + 13` is a `char` artefact.
* **Header layout.** Audio starts at `4 + h[4] + 8` (clamped to the 220-byte
  header the DLL keeps); the frame count is the `int32` at `h[4] + 6`; mono
  16-bit byte count is `2 * frames`. Off-by-one errors here are the classic
  failure — re-check against the fixtures.
* **State persists across blocks.** The DPCM accumulator (`st.acc`) and the
  code book (`bookDv`, 8100 bytes, entry 0 = `0,0,0,0,0,-1`) must not be reset
  per block.
* **Left channel only.** The decoder writes a 4-byte stride; the loop then
  compacts every other int16 (in place, ascending — safe because the read
  index is always ≥ the write index).
* **Buffer sizes.** The output buffer is preallocated to
  `dataBytes + 75632 + 44 + 64 + 1024`, zeroed `0x127B0` bytes before each
  block, and sliced to `44 + dataBytes` at the end.
* **Float arithmetic.** `makeDeltaTable` relies on IEEE doubles; JS numbers are
  doubles too, so keep the same operation order (`v1 *= v20; v20 -= 0.00022`).
* **Errors, not silent corruption.** Out-of-range typed-array/`DataView`
  accesses or a truncated stream must surface as an error shown in the UI, not
  produce a plausible-looking wrong file. (The Python raises in the same
  situations.)

## Verification

There is no JS test runner in this folder and none should be added just for
this. Verify headlessly with Node by extracting the first `<script>` block:

```js
// run from anywhere:  node check.js   (do not leave check.js behind)
const fs = require("fs");
const html = fs.readFileSync("web/index.html", "utf8");
const core = html.match(/<script>([\s\S]*?)<\/script>/)[1];   // first block = decoder
const PXD = new Function(core + "; return PXD;")();

const r = PXD.pxdToWav(new Uint8Array(fs.readFileSync("hyper-test.pxd")));
const s = new Int16Array(r.wav.buffer, 44, r.frames);
// compare r.frames, r.wav.length, min, max, sum, sum of squares
```

Expected results — the same regression locks as the Python suite
(`work/src/test_pxd2wav.py`, `test_pxd32d5.py::test_tp_real_files`):

| file | frames | WAV bytes | min / max | sum | sum of squares |
|---|---|---|---|---|---|
| `hyper-test.pxd` | 14 700 | 29 444 | −12604 / 12588 | −2 385 408 | 307 018 638 208 |
| `bo-test.pxd` | 117 600 | 235 244 | −14008 / 14064 | (take from the Python suite) | (take from the Python suite) |

For the strongest check, generate the reference with the Python converter
(`python work/src/pxd2wav.py <file> -o <tmpdir> -f`) and compare the
bytes of the JS output to it; they should be **identical**. If you do this, say
so; if you could not, say that instead of implying it.

Rules:

* Never edit a golden value to make a check pass. If a value moves, explain why
  the new value is *more* correct, or fix the cause.
* Do not claim bit-exactness with the original DLL — there is no reference
  output from the real DLL. Say "matches the Python port".
* Do not leave scratch files (`check.js`, generated `.wav`, `node_modules`)
  behind.
* The repo-root `bo-test.wav` is **not** a reference for this port (it comes
  from some other converter; its samples differ). Use the Python port's output.
* If you cannot open the page in a browser, say that the UI was not exercised;
  only the decoder core is testable headlessly.

## Style

* 2-space indent in `index.html`, `"use strict"` in both scripts, no
  frameworks, no bundler, no external requests (fonts, CDNs, analytics). The
  page must keep working offline.
* The decoder script must stay DOM-free; UI code must stay out of it.
* Background image: keep it as CSS `cover` (stretch to fill, keep aspect
  ratio) with the relative filename; if the image file is renamed, update the
  `url(...)` in the stylesheet.
* Output is always a mono, 16-bit, 44.1 kHz PCM WAV with a 44-byte header.
