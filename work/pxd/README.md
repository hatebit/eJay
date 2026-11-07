# PXD32D5.DLL (build D4) — reverse-engineering notes

Static analysis of `pxd32d5_d4.dll`, the 2001 Windows audio engine of Dance eJay3. This directory is a
documentation workspace, not a software project: the deliverable is the notes, plus the small Python
scripts used to produce them.

**Subject:** `pxd32d5_d4.dll` — 348,160 bytes, PE32 / x86, image base `0x10000000`, link stamp
2001-07-26 09:43:32 UTC, 96 named exports (ordinals alphabetical), 154 imports from 7 DLLs. The
internal DLL name is `pxd32d5.dll`; "D4" is only this workspace's file-name tag.

**Not checked in:** the binary is proprietary and no longer lives in this
repository. Verify a local copy before trusting an address: 348,160
bytes, MD5 `945c4fa40e1ab859280d164c218776d0`, SHA-256
`32438cdebfe8c631468437870d407c9c245d5d32f3588f5dba82c23d9594fa08`.

## What the DLL is

`pxd32d5.dll` is the **audio engine of Dance eJay3** (uninstall key `…\Uninstall\Dance eJay3`,
sample collections `eJay SoundCollection`/`…2`, conversion titles `PXD2Wav`/`WAV2PXD`). It is a
**DirectSound-based sampler / sequencer**:

* the host pushes sample events into per-voice rings with `APlay` (30-event rings, stride `0x108`);
  a worker thread mixes them and keeps up to **28 DirectSound buffers** fed, all at **44.1 kHz,
  16-bit, stereo**;
* the device is created at runtime with **`CoCreateInstance`** on `CLSID_DirectSound` — there is no
  `dsound.dll` import at all; MME `waveOut` is used only for enumeration and `waveOutSetVolume`;
* sample loading with Microsoft **`SZDD`** decompression (`0x44445A53`) through three `LZ32` thunks,
  200 slots of `0x528` bytes, cached as temp files `pxd32p<a-z>.tmp` under a free-space budget of
  `(free_MB − 18)`;
* a `waveIn` recording path (40 queued `0x1800` buffers, no callback) plus the mixer API for volume
  and record-input selection;
* waveform thumbnails as GDI DIB sections, a text-command property protocol (`REffekt`, `RDrum`,
  `RpDrum` — names in `0x1004B620`–`0x1004B9C8`), format conversion (`W2P`), a debug logger
  (`Debimem` → `c:\memo.txt`), and the product's uninstall registry entry (`ARegUnIn`/`ARegDelete`);
* two unexported functions still validate a `LIST`/`INFO`/`ICMT` comment starting with `eJay` and
  ≥ `0x15` bytes — the project-format writers are stubs in this build.

Every export is `__stdcall`; almost all return the engine status word (`int16`) at `0x10096DE0`;
every non-trivial call is gated on the magic `0x2A90CB20` at `0x10096DFC`. Fifteen exports declare
arguments they never read — trust the `Args` column of `PXD32D5-D4.md`, never the name.

This build is a **rewrite, not a recompile** of the 1998 sibling engine:
96 exports against 64, new `D*`/`P*`/`ALoad`/`REffekt`/`W2P` families, output moved from MME
`waveOut` to DirectSound, `SZDD` support added — but the same German API vocabulary and the same
engine magic.

## Documentation

| File | Contents |
|---|---|
| [`PXD32D5-D4.md`](PXD32D5-D4.md) | master/reference: file facts, all 96 exports with RVA and ordinal, calling conventions and arity per export, method, relationship to the 1998 engine |
| [`PXD32D5-D4-engine.md`](PXD32D5-D4-engine.md) | what the engine does: init contract, voice/event model, DirectSound layer, transport and worker thread, sample slots and `SZDD`, recording, conversion, text-command protocol, browser, registry glue, confidence table |
| [`PXD32D5-D4-layout.md`](PXD32D5-D4-layout.md) | image headers, sections, data directories, import/relocation directories, DirectSound interface offsets, runtime globals, voice/event/sample structures, address→section map |
| [`PXD32D5-D4-strings-imports.md`](PXD32D5-D4-strings-imports.md) | identity and application strings, format strings, strings that exist only as immediates, import inventory per DLL, useful negatives |
| [`PXD32D5-D4-worklog.md`](PXD32D5-D4-worklog.md) | provenance, progress log, **corrections to earlier readings**, established facts, open questions with test plans, artefacts, reusable snippets |

Start with `PXD32D5-D4.md` for the API surface, then `PXD32D5-D4-engine.md` for behaviour. If a
statement matters, follow its address into `PXD32D5-D4-layout.md` and confirm it with `_pxd_dump.py`.

## The analysis scripts

| File | Purpose |
|---|---|
| `_pxd_conventions.py` | shared preamble (PE/export parsing helpers); walks the export table, disassembles every export, writes `_pxd_detail.txt` |
| `_pxd_dump.py` | annotated disassembly of named exports or address ranges, with import slots resolved to function names |
| `_pxd_xref.py` | cross-checks each callee's `ret N / 4` against push counts at internal call sites |
| `_pxd_rows.py` | regenerates the per-export markdown table from the analysis plus an annotation dictionary (`--splice` writes it into the master) |
| `_pxd_headers.py` | dumps the PE headers, section table and data directories |
| `_pxd_imports.py` | parses the import descriptors, writes `_pxd_imports.txt` |
| `_pxd_iatref.py` | maps an IAT slot address to its import name and every call site |
| `_pxd_strings.py` | string inventory with VA mapping, writes `_pxd_strings.txt` |
| `_pxd_calls.py` | call graph of one export: callees, push counts, string references |
| `_pxd_peek.py` | hex + ASCII dump of 32 bytes at an absolute VA |
| `_pxd_mdcheck.py` | markdown consistency check over all `*.md`: constant pipe count per table block (escaped pipes ignored), paired code fences |
| `_pxd_detail.txt` | per-function heads, frame offsets and `ret` forms for all 96 exports |

They need [Capstone](https://www.capstone-engine.org/), installed into a scratch directory so nothing
is added to a project environment. The DLL is not checked in: set
`PXD_DLL` to a local copy. All scripts otherwise resolve paths relative to
their own location, so the folder can be moved or copied.

```bash
python -m pip install --target /tmp/caplib capstone
cd work/pxd
PYTHONPATH=/tmp/caplib python _pxd_conventions.py
PYTHONPATH=/tmp/caplib python _pxd_dump.py AStart APlay DPlayFile
```

## Quick recipes

**Disassemble one export.** `PYTHONPATH=/tmp/caplib python _pxd_dump.py APlay` — imports are labelled,
so `call dword ptr [0x10043xxx]` shows up as the API name.

**Find what a string is used for.** Scan the *whole file* for the little-endian VA, then check whether
the hit lies *before* the next export's RVA. If it does not, it belongs to an internal function, not to
the preceding export — and a string is only "dead" after a whole-file scan, not just `.text`.

**Check an IAT slot.** `PYTHONPATH=/tmp/caplib python _pxd_iatref.py 0x10043214` prints the import name
and every call site — never assume a slot name from its position.

**Look up an ordinal.** Compute it from the ordinal table (`ordinal_of` in `_pxd_rows.py`); the rows in
the master table are alphabetical, so the row number is not the ordinal.

## Status

Established: identity, API surface, calling convention and arity (0 push-count mismatches over all 96
exports), voice/event model, DirectSound bring-up and interface offsets, transport and worker thread,
sample slots and `SZDD` decompression, recording path, temp-file cache, text-command protocol,
registry glue, string and import inventories, base-relocation map.

Open: which host `.exe` shipped this copy; the real vtable-slot mapping of the DirectSound calls;
the `ICMT` comment payload; the status-word bits; what `APlay`'s four pass-through parameter dwords
mean; three dead-code sites; whether the `.flt`/`.env1`/`.env2` extensions are sidecar files.
`PXD32D5-D4-worklog.md` §4 lists each with a way to close it.

## Ground rules

* Static analysis only — the DLL has never been loaded, executed or patched.
* 32-bit x86 image: it cannot be loaded into a 64-bit process without a thunking layer.
* Claims are tagged **[certain]** (visible in the code), **[likely]** (only reading that fits the
  evidence) or **[guess]** (plausible, unproven). Keep the tags when citing.
* Work conventions for agents live in [`AGENTS.md`](AGENTS.md).
