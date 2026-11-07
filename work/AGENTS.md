# AGENTS.md — working in this folder

This folder is a standalone project: a Python port of a few exports of Rave eJay binaries plus the reverse engineering
notes that justify it. Correctness is judged against the decompilation, the binary itself, and the real `.pxd` fixtures
when they are available — not against a written specification. The fixture files (`bo-test.pxd`, `hyper-test.pxd`) are
**not checked in**; the scripts look for them in `work/data/` and skip the fixture tests when they are absent. The analysed DLL is
**not checked in** either (see `work/pxd/README.md`); the recovered notes are split between `work/docs/` and `work/pxd/`.

**SAFETY:** Do **NOT** execute, load, or run any binaries (`*.dll`, `*.exe`) or any code from the binary. Never use
`ctypes`, `LoadLibrary`, `rundll32`, or any other method to invoke DLL functions. The binary is read-only reference
material only (for disassembly and inspection). All functionality must be implemented as pure Python code.

## Ground rules

1. **Static analysis only.** Never load, execute, patch or write binaries (`*.dll`, `*.exe`). Do not register
   exports, do not shell out to `rundll32`, do not "test" a function.
2. **Keep dependencies out of any project environment.** Capstone goes in a scratch dir and is used
   through `PYTHONPATH`:
   ```bash
   python -m pip install --target /tmp/caplib capstone
   cd work/pxd
   PYTHONPATH=/tmp/caplib python _pxd_dump.py APlay
   ```
   Never `pip install` into the global environment for this work.
3. **Stay in this repository.** Do not read, write or browse anything outside the repository root.
4. **Shell is bash on Windows.** POSIX syntax only (`ls`, `mv`, `rm`, `/dev/null`), forward slashes in
   paths. Python is `python` (3.x). Read-only tools: with a binary this size, re-reading bytes from the
   file is always cheaper than guessing.

## Files and what belongs where

| path                      | role                                                                                                                                                                                                   |
|---------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `pxd/`                    | the DLL and the full reverse-engineering document set — read-only reference                                                                                                                             |
| `pxd/README.md` | subject facts and provenance of the analysed DLL (binary **not checked in**) |
| `data/`                   | real `tPxd` fixtures — **not checked in**; tests skip when absent                                                                                                                                       |
| `dumps/`                  | derived per-mix text dumps (`WAMBAM.*.txt`) used by the Techno notes                                                                                                                                   |
| `src/pxd32d5.py`          | the port: engine, `RWavToTemp`, both decoders                                                                                                                                                          |
| `src/pxdsink.py`          | playback sinks: `FileSink`, stdlib `ctypes` `waveOut`, optional `sounddevice`                                                                                                                          |
| `src/pxd2wav.py`          | CLI (`argparse`), no engine logic of its own                                                                                                                                                           |
| `src/mixplay.py`          | Rave eJay `.mix` player: grid + sample index (`../docs/formats/MIX_FORMAT_RAVE.md`) → engine play requests                                                                                             |
| `src/sdmixplay.py`        | standalone `.mix` player: own `tPxd`/RIFF decoder and Python mixer → `sounddevice` directly, no engine                                                                                                 |
| `src/sdmixplayer2.py`     | Techno eJay `.mix` player: trailer event table + `RAVE20.INF` + `RAVE20` archive → the same engine-free decoder (`../docs/formats/MIX_FORMAT_TECHNO.md` §12)                                            |
| `src/mixsamples.py`       | lists the `RAVE20.INF` samples a Techno eJay mix references (also supplies `read_events`)                                                                                                               |
| `src/sdpxdplay.py`        | standalone `.pxd` player: the same engine-free `tPxd`/RIFF decoder → `sounddevice` directly, no engine                                                                                                 |
| `src/pxdplay.py`          | playback demo CLI — plays a `.pxd` through the ported engine on the speakers                                                                                                                           |
| `src/test_pxd32d5.py`     | the whole verification suite, a plain runnable script                                                                                                                                                  |
| `src/test_pxd2wav.py`     | WAV conversion regression tests                                                                                                                                                                        |
| `src/test_sdmixplay.py`   | tests for the standalone `.mix` player                                                                                                                                                                 |
| `src/test_sdpxdplay.py`   | tests for the standalone `.pxd` player                                                                                                                                                                 |
| `src/hyperplay.py`        | Hyper Generator preset player                                                                                                                                                                          |
| `src/pxdstream.py`, `src/pxdhelpers.py`, `src/scan_pxd_headers.py` | inspection helpers                                                                                                                                         |
| `tools/pxd_dis.py`        | PE reader + capstone disassembler (`dis`, `find`) — use whenever disassembly/reference is needed. It may be extended if needed, or new tools may be created under `tools/` to assist with the process. |
| `tools/disapp.py`         | disassembler for the host binary `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE`                                                                                                                                                |
| `pxd/PXD32D5-D4.md`       | the D5 export/convention reference — keep it current                                                                                                                                                   |
| `docs/PLAYBACK.md`        | playback port notes                                                                                                                                                                                    |
| `docs/HYPER_GENERATOR*.md`| Hyper Generator data, DSP extraction and string search                                                                                                                                                 |
| `docs/RWavToTemp.md`      | focused write-up of the ported path                                                                                                                                                                    |

The notes are a deliverable, not scratch space: a change that alters behaviour without updating `docs/` is incomplete.

## Evidence discipline

Every behavioural claim carries a **[certain]** / **[likely]** / **[guess]** tag and an address. When
you add a claim:

* **[certain]** — the instruction or byte pattern is visible; quote the address.
* **[likely]** — several independent observations only fit this reading; say which.
* **[guess]** — plausible; say what would confirm it.

When a new observation contradicts an existing document, do not silently edit the old statement: fix
the statement **and** add an entry to `<filename>-worklog.md` §2 ("Corrections to earlier readings") with
what was believed, what is true, and the evidence.

## Commands

```sh
python src/test_pxd32d5.py                            # full suite
python src/pxd2wav.py song.pxd -o out/                # convert one file
python src/mixplay.py song.mix --list                 # dump a .mix arrangement
python src/sdmixplay.py song.mix --list               # same, without the engine
python src/sdmixplayer2.py "../disks/Techno_eJay/MIX/WAMBAM.MIX" --list  # Techno mix
python tools/pxd_dis.py 0x100149E0 40                 # disassemble at a VA
python tools/pxd_dis.py find a380e30810               # locate a byte pattern
```

Run them from `work/`; the scripts resolve `pxd/` and `data/` relative to their
own location, so they also work from elsewhere. `tools/` needs
`pip install capstone`; `src/` must stay standard-library only. The one
exception is an optional, lazily imported `sounddevice` in `pxdsink.py` (see
below); every default path and the whole test suite run without it.

## Conventions

* Markdown, tables over prose for anything with addresses.
* The DLL's globals are modelled on one `Engine` instance (`pxd32d5.engine`,
  used by the module-level `PInit` / `PClose` / `RWavToTemp`). New state goes on
  `Engine` or `Session`, never into new module-level variables.
* `Session` field comments carry the original layout (`# +12 a1[3] read
  offset`). Keep them accurate when you touch a field.
* Reuse the C-semantics helpers instead of ad-hoc arithmetic: `_idiv` (C
  truncating division), `_wrap16` (int16 wrap), `_s16` / `_put16` / `_u16` /
  `_u32` (masked little-endian access), `emit()` (the decoder's saturating
  step).
* Docstrings and comments cite the original symbol (`sub_10016361`,
  `dword_10096CC8`). An address may only come from a `//----- (ADDR)` label, an
  export-table entry, or a `sub_ADDR` name — never from a line number in the
  dump (that mistake produced two wrong addresses already).
* `docs/` uses the same citations and marks anything not confirmed as
  **(unverified)**.
* Addresses as `0x100076C8` (absolute VA, never bare RVA — the base is `0x10000000`).
* Hex for machine facts, decimal for human quantities, with the conversion in parentheses the first
  time (`0x249F0` (150,000)).
* No speculation in a table cell without a confidence tag right there.
* Do not delete historical statements from the worklog; the corrections log is the audit trail.
* Do **not** fix small issues in code comments (typos, grammar, style) for
  their own sake. Only update comments if they no longer correspond to the
  code.

## Invariants — do not "clean these up"

1. `PInit` must run before `RWavToTemp`; the guard is `dword_10096CC8`
   (`Engine.started`), set by `AInit` → `sub_100178D4`. Otherwise
   `RWavToTemp` returns 0 immediately, exactly like the DLL.
2. C arithmetic: division truncates toward zero (`_idiv`, not `//`), int16
   values wrap (`_wrap16`), stores to 16-bit fields mask (`_put16`).
3. The decoder's overflow clamp picks its limit from the sign of the *wrapped*
   sum, so a positive overflow becomes `0x8000`. Reproduced deliberately.
4. `tP` opcodes `0xF4…0xFE` copy `opcode - 0xF3` = 1…11 deltas. Hex-Rays'
   `opcode + 13` (257…267) is a `char` → `int` artefact of the decompiler.
5. `tPxd` header: `h[4]` counts the comment field **including itself**; data
   starts at `4 + h[4] + 8`; the frame count is `i32` at `h[4] + 6`;
   `AWaveDauer` returns `4 * frames` and `v14 = AWaveDauer / 2` is the mono
   16-bit byte count. Off-by-one here is the classic failure (it happened
   twice): always re-check against `data/bo-test.pxd` (h[4]=38 → data at 50)
   when that fixture is present.
6. The decoder writes the **left channel only** (4-byte stride); the converter
   then keeps every fourth byte.
7. DPCM integrator (`Session.vol_word`, `session[4]`) and the code book
   (`Session.book`, 8100 bytes, entries 16 bytes apart, entry 0 =
   `0,0,0,0,0,-1`) persist across blocks and calls. Do not reset them per
   block.
8. Output file: preallocated to `v14 + 75632 + header + 64` (or
   `4*75600 + 64`), 44-byte mono 44.1 kHz header when `output_kind == 4`,
   truncated to `header + v14`; when `v14 == 0` the file keeps its
   preallocated size and gets no header (faithful to the DLL).
9. `a7`: 128-sample ramp (the very last sample becomes 0) then zero padding to
   whole 9450-byte blocks, at most 16.
10. Gain is `(pan * volume) >> 8`; the file path uses `pan = 512`, i.e. 2×.
11. Overwrite/`--force` behaviour belongs to the CLI, not to the port.
12. Only raise `UnsupportedCodec` for a genuinely unknown stream type; the DLL
    tolerates a lot and the port mirrors it (e.g. compressed RIFF input yields
    a broken file, not an exception).

## Porting the next function

1. **Locate it.** Use the export table in `pxd/PXD32D5-D4.md` to get the
   address, then disassemble it with `tools/pxd_dis.py` (see §Method). No
   decompiler dump is checked in; `AStop` at `0x10014516` is an example of a
   body that has to be read directly from the binary.
2. **Verify in asm** anything the decompiler tends to garble: `char`
   truncation, address-vs-pointer (`0x1008E380`), signed vs logical shifts,
   struct strides, inlined `memset`/`memcpy`, and loop bounds.
3. **Implement** on `Engine`/`Session`, preserving the original symbol names in
   comments and the C semantics above.
4. **Test** with a synthetic stream whose expected output you can compute by
   hand, plus a real fixture where one exists. Reuse `make_wav`, `read_wav`,
   `new_engine` from `src/test_pxd32d5.py`; tests are plain functions taking
   `tmp` (a temp dir), auto-discovered by `main()`.
5. **Document**: a row in `pxd/PXD32D5-D4.md`'s export table, `PLAYBACK.md`
   §2/§4 for playback changes; `PXD32D5-D4-worklog.md` §4 if it closes one.
   Update `README.md`'s status table. Touch `docs/RWavToTemp.md` if it is on
   the `PInit`/`RWavToTemp`/`PClose` path.
6. **Run the full suite** and report the real numbers.

## Verification bar

* `python src/test_pxd32d5.py` must pass. Fixture tests skip silently when
  `data/` is absent — say so instead of implying they ran. The fixtures are
  not checked in, so on a fresh clone those checks are skipped.
* The golden values in `test_tp_real_files` (frame counts, min/max, sum,
  sum-of-squares) are regression locks from a decoder that reproduces the
  declared frame count and consumes the stream to its last byte. If a golden
  value moves, explain why the new value is *more* correct; never edit it to
  get green.
* Never weaken an assertion, skip a test, swallow an error or add a
  suppression to make a check pass. Fix the cause.
* There is no reference output from the real DLL yet, so do not claim
  bit-exactness. Say "matches the decompiled arithmetic and the fixture
  structure".

## Style

* 4-space indent, ~79 columns, no formatter config; match the surrounding code.
* `src/` stays standard-library only; new dependencies need a strong reason and
  belong under `tools/`. `pxdsink.SoundDeviceSink` and `sdmixplay.py` are the
  approved exceptions: `sounddevice` is imported lazily, so importing `src/`
  and running the tests never requires it.
* Public names are API: `PInit`, `PClose`, `RWavToTemp`, `Engine`, `Session`,
  `engine`, `awave_dauer`, `DELTA_TABLE`, `UnsupportedCodec`.
* CLI: `argparse` only, quiet on success with `-q`, non-zero exit when any
  input fails. Do not add engine knowledge to the CLI.
* Do not leave generated files (`.wav`, `.pcm`, `__pycache__`) behind, and do
  not touch `pxd/` or `dumps/`.

## Open threads

* The playback set: `AStart`/`PStart`, the player thread, the drain
  (`sub_10015B6C`), the mix tick and pause/stop are ported against an
  `OutputSink` (`src/pxdsink.py`); `RWaveLaden` loads but does not start
  playback and the `sub_1001CA3B(4)` hand-off is unported. See
  `docs/PLAYBACK.md`.
* `sub_1000E3E0` — echo/chorus/reverb chain. Its inputs (the coefficients from
  `sub_10021272`) are known and ported; the algorithm is not.
* `W2P` / `AExport` — the `wav → pxd` encoder; `sub_10021D8A`'s tables are
  already documented, and the log strings (`WAV2PXD Konvertierung …`) identify
  the path.
* `LZ32.dll` is imported (`LZOpenFileA`/`LZRead`): some inputs may be
  LZ-compressed.
* Unresolved mode selectors: `dword_10096CD8` values other than 4,
  `word_10096D7C == 2` (mixing rate 29400), `dword_1008E358 ∈ {2,3,4}`.
* Possible ground truth: the DLL imports only winmm/ole32/gdi32/user32, so
  loading it via `ctypes` and calling `AWaveDauer` / `RWavToTemp` might work —
  untested, and it would need a mixer device and its `PXD_Event` thread.

## Definition of done for a task here

* The new fact has an address and a confidence tag in the correct document.
* Anything it contradicts is corrected **and** logged in `pxd/PXD32D5-D4-worklog.md` §2.
* The open-question list in `pxd/PXD32D5-D4-worklog.md` §4 is updated (closed, narrowed, or newly added).
* The markdown consistency check in `pxd/AGENTS.md` passes.
* `README.md` is updated only if the high-level story changed.
