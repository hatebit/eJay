# AGENTS.md

Guidance for an AI coding agent continuing work in this directory. Read this before touching anything,
then read `README.md` and the repository-wide [`AGENTS.md`](../../AGENTS.md). The same evidence
discipline, file placement and style rules apply here.

## What this directory is

A **documentation workspace**, not a repository or an application. There is no git, no build, no tests,
no package manifest. The artefacts are:

* the subject binary, `pxd32d5_d4.dll` — **not checked in**; use a local
  copy (do not modify it);
* the hand-written markdown documents (the deliverable), including the
  `PXD32D5-D4-*.md` set, `ongoing.md` and `README.md`;
* small Python scripts plus the text artifacts they produce (`_pxd_detail.txt`,
  `_pxd_imports.txt`, `_pxd_strings.txt`, and the `_pxd_rows.md` byproduct) that supply the evidence
  those documents cite.

The goal of the work is understanding: recover what the DLL does and document it so the next session
can continue without re-deriving anything.

## Ground rules

1. **Static analysis only.** Never load, execute, patch or write to the analysed DLL (`PXD_DLL`). Do not register
   exports, do not shell out to `rundll32`, do not "test" a function.
2. **Keep dependencies out of any project environment.** Capstone goes in a scratch dir and is used
   through `PYTHONPATH`:
   ```bash
   python -m pip install --target /tmp/caplib capstone
   cd work/pxd
   PYTHONPATH=/tmp/caplib python _pxd_dump.py AStart
   ```
   Never `pip install` into the global environment for this work.
3. **Stay in this repository.** Do not read, write or browse anything outside the repository root.
4. **Shell is bash on Windows.** POSIX syntax only (`ls`, `mv`, `rm`, `/dev/null`), forward slashes in
   paths. Python is `python` (3.x). Read-only tools: with a binary this size, re-reading bytes from the
   file is always cheaper than guessing.

## Files and what belongs where

| File | Write to it when… |
|---|---|
| `PXD32D5-D4.md` | the export table, an export's arity/arguments, or the convention analysis changes. Also the index of the document set. |
| `PXD32D5-D4-engine.md` | you learn what the code *does* — behaviour, data flow, algorithms, policy |
| `PXD32D5-D4-layout.md` | you identify an address, global, structure, field, table or section fact |
| `PXD32D5-D4-strings-imports.md` | new strings, format strings, or import facts |
| `PXD32D5-D4-worklog.md` | progress, **corrections**, open questions, new artefacts, reusable snippets |
| `README.md` | the high-level story for a human reader changes |
| `_pxd_*.py` | you need a new mechanical pass; keep them small, documented and re-runnable |

Script rules: resolve every path from `os.path.dirname(os.path.abspath(__file__))` — never hardcode an
absolute path, so the folder stays movable. `_pxd_conventions.py` is the shared preamble the other
scripts `exec` and rewrites `_pxd_detail.txt`; `_pxd_rows.py` writes `_pxd_rows.md` as a byproduct —
diff it if useful, then delete it, because the canonical table is in `PXD32D5-D4.md` (its
`<!--ARITY-ROWS-->` block is regenerated with `--splice`).

Never restate the export table or the arity table in another file; link to `PXD32D5-D4.md` instead.

## Evidence discipline

Every behavioural claim carries a **[certain]** / **[likely]** / **[guess]** tag and an address. When
you add a claim:

* **[certain]** — the instruction or byte pattern is visible; quote the address.
* **[likely]** — several independent observations only fit this reading; say which.
* **[guess]** — plausible; say what would confirm it.

When a new observation contradicts an existing document, do not silently edit the old statement: fix
the statement **and** add an entry to `PXD32D5-D4-worklog.md` §2 ("Corrections to earlier readings")
with what was believed, what is true, and the evidence.

## Rules that have already caused wrong answers here

1. **Ordinals are alphabetical, not address-ordered.** The name table (`0x10049BD8`) is sorted
   ASCII-ascending and the ordinal table (`0x10049D58`) runs 0…95 in that same order, so EAT[0] is
   `ABilder` (ordinal 1, at `0x10017883`) while the first export in the image — lowest RVA, row 1 of
   the master table — is `W2P` (ordinal 96, at `0x100104C6`). Never copy the row index into an `Ord`
   column; compute it from the ordinal table (`ordinal_of` in `_pxd_rows.py`).
2. **An export's body ends at its `ret`.** The exports are not contiguous. Internal functions and their
   literals live in the gaps between export RVAs, so "address is between export A and export B" does
   **not** mean "address belongs to export A". Before attributing anything, read the bytes and check
   for an early `ret` / `0xCC` padding / a fresh `55 8B EC` prologue.
3. **Never name an import from its IAT slot number.** Disassemble, then resolve
   `call dword ptr [0x10043xxx]` through the import table (`_pxd_iatref.py <slot>`; the IAT is
   `0x10043000`–`0x10043284`, 161 slots over 7 DLLs). Assuming slot→name produced wrong attributions
   in the sibling workspace.
4. **A dead literal is only dead after a whole-file scan.** Seven literals (`c:\debug.txt` at
   `0x1004BA44`/`0x1004BA68`, the two `%s : %ld` formats, `c:\w.wav`, `Test-Meldung`) have **no
   reference anywhere in the file** — proven by a whole-file scan for each little-endian VA, not a
   `.text`-only scan (worklog §2.7).
5. **`0x10093F38` is not a second array.** It is the same `0xA0`-stride voice record array at
   `0x10093EB0`, with the `+0x88` displacement folded into the constant (MSVC strength reduction).
   See worklog §2.6 before writing anything about mapped-file fields.
6. **Do not copy 1998-engine behaviour onto this build.** It is a rewrite, not a recompile:
   `ARecPlay` here only measures the temp record file, `ARecInput` pushes its argument to the mixer
   routine, and there is no `waveInGetDevCaps` import. Verify every claim in *this* image.

## Known facts to not re-derive

* Image base `0x10000000`; `.text` is `0x10001000`–`0x10042162` (raw starts at file offset `0x1000`);
  sections are `.text`, `.rdata`, `.data`, `.reloc` (4 sections; no resource, no load config, no TLS).
  App strings and initialised globals live in the file-backed part of `.data` (`0x1004B000`–
  `0x1004F000`); the BSS beyond it (`0x1004F000`–`0x10098AEC`) never appears in a file dump.
* Engine magic `0x2A90CB20` at `0x10096DFC`, status word `int16` at `0x10096DE0` (returned
  sign-extended by nearly every export), request word `0x10096D88` (0 idle / 1 stop / 2 start).
* "Play to the end" sentinel `0x6921CFF0`.
* Worker thread at `0x10017AB4`, created by the start helper `0x100178D4` after seven
  `InitializeCriticalSection` calls and `mixerOpen`; polls `WaitForSingleObject(PXD_Event, 0)`
  (handle at `0x10093A84`, event name `PXD_Event` at `0x1004B424`) plus exit flag `0x100826C0`.
  Exports block in `0x100144C9` (`Sleep(8)` × 20/−30 ≈ 176 ms stop, ≈416 ms start).
* DirectSound is created with `CoCreateInstance` (CLSID `{47D4D946-62E8-11CF-93BC-444553540000}` at
  `0x100434B0`, IID `{279AFA83-4981-11CE-A521-0020AF0BE560}` at `0x100434C0`) — there is **no**
  `dsound.dll` import. MME `waveOut` only for enumeration and `waveOutSetVolume`.
* Voice array `0x10095108`, stride `0x84`, 32 voices (48 for product type `0x14`); 30-event rings,
  stride `0x108`; 28 playable DirectSound voices (slots `1..0x1C`) in the `0xA0` record array at
  `0x10093EB0`; the `0xA0` array's mapped-file fields are `+0x88`/`+0x8C`/`+0x90`/`+0x98`.
* Temp names `pxd32p<a-z>.tmp` under `GetTempPathA` with a `c:\` fallback; sample cache
  `(free_MB − 18) MB`; 200 sample slots of `0x528` with `SZDD` (`0x44445A53`) decompression through
  three `LZ32` thunks.
* Recording: `waveIn` 44.1 kHz/16-bit/stereo, 40 × `0x1800` buffers, no callback.
* `REffekt`/`RDrum` are string-command property setters over `lstrcmpiA`, names in
  `0x1004B620`–`0x1004B9C8`.
* Export ordinals are alphabetical (`ABilder` = 1 … `W2P` = 96), unrelated to address order.
* **15 exports declare arguments they never read** — the caller must still push the full list; use the
  `Args` column of `PXD32D5-D4.md`, never the name.

## Workflow for a new question

1. **Locate** — dump strings with `_pxd_strings.py`, or cross-reference a string VA with the snippet
   in `PXD32D5-D4-worklog.md` §6.
2. **Disassemble** — `PYTHONPATH=/tmp/caplib python _pxd_dump.py <Export>` or an address range.
   Read the whole body including early-exit paths.
3. **Cross-check** — does a second, independent signal agree (frame offsets vs `ret N`, call-site push
   counts vs callee's `ret N / 4`, string xref vs code path)? If not, the hypothesis is not ready.
4. **Record** — update the right document, add the address, keep the confidence tag, and add a worklog
   entry if anything previously written changes.
5. **Verify** — re-run a script that exercises the claim; check tables and code fences stayed valid:
   ```bash
   python - <<'EOF'
   import glob
   for f in sorted(glob.glob('PXD32D5-D4*.md')):
       lines = open(f, encoding='utf-8').read().split('\n')
       rows = [(i, l.count('|')) for i, l in enumerate(lines, 1) if l.startswith('|')]
       blocks, cur, prev = [], [], None
       for i, c in rows:
           if prev is not None and i != prev + 1: blocks.append(cur); cur = []
           cur.append((i, c)); prev = i
       if cur: blocks.append(cur)
       bad = [b[0][0] for b in blocks if len({c for _, c in b}) > 1]
       fences = sum(1 for l in lines if l.startswith('```'))
       print(f, 'table_issues', bad, 'fence_ok', fences % 2 == 0)
   EOF
   ```
   Tables must have a constant pipe count per block and fences must pair up.

## Style for the documents

* Markdown, tables over prose for anything with addresses.
* Addresses as `0x100076C8` (absolute VA, never bare RVA — the base is `0x10000000`).
* Hex for machine facts, decimal for human quantities, with the conversion in parentheses the first
  time (`0x249F0` (150,000)).
* No speculation in a table cell without a confidence tag right there.
* Do not delete historical statements from the worklog; the corrections log is the audit trail.

## Do not

* Run the DLL, register it, or feed it to `rundll32`/`regsvr32` — it is 32-bit and expects a 2001 host.
* Modify the analysed DLL or write derived binaries next to it.
* Add a `requirements.txt`, `pyproject.toml`, lockfile or CI config — this is not a project.
* Invent API signatures. Fifteen exports declare arguments they never read, so the caller must still
  push them; guessing from names will desynchronise the stack in any future harness.

## Definition of done for a task here

* The new fact has an address and a confidence tag in the correct document.
* Anything it contradicts is corrected **and** logged in `PXD32D5-D4-worklog.md` §2.
* The open-question list in `PXD32D5-D4-worklog.md` §4 is updated (closed, narrowed, or newly added).
* The markdown consistency check above passes.
* `README.md` is updated only if the high-level story changed.
