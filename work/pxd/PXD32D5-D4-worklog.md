# PXD32D5.DLL (build D4) — worklog and handover

What has been established, how, what was wrong earlier, and what to do next. Written so a future
session can resume without re-deriving anything. The conventions (evidence tags, correction policy,
file placement) follow the repository-wide [`AGENTS.md`](../../AGENTS.md).

**Document set**

| File | Contents |
|---|---|
| `PXD32D5-D4.md` | master: file facts, all 96 exports with RVA, ordinals, calling conventions + arity, method |
| `PXD32D5-D4-engine.md` | what the engine does — behavioural map with addresses and confidence tags |
| `PXD32D5-D4-layout.md` | headers, sections, directories, runtime globals, structures, address map |
| `PXD32D5-D4-strings-imports.md` | string inventory, import inventory, useful negatives |
| `PXD32D5-D4-worklog.md` | this file: provenance, corrections, open questions, artifacts, snippets |

**Subject:** `pxd32d5_d4\pxd32d5_d4.dll` — 348,160 bytes, PE32 x86, image base `0x10000000`, PE stamp
2001-07-26 09:43:32 UTC, 96 named exports, 154 imports from 7 DLLs. The internal name is
`pxd32d5.dll`; `D4` is only the file-name tag used in this workspace.

**Ground rules used throughout:** static analysis only — the file was never loaded, executed,
registered or modified. Capstone was installed into a scratch directory (`/tmp/caplib`) and used
through `PYTHONPATH`; nothing was added to a project environment. Paths are resolved from each
script's own directory, so the folder can be moved.

---

## 1. Progress log

| Step | What was done | Result |
|---|---|---|
| 1 | Parsed the PE headers, section table and data directories by hand (`_pxd_headers.py`) | 4 sections; only 4 of 16 data directories populated; no resource, no load config, no TLS |
| 2 | Parsed the export directory (EAT, name table, ordinal table) | 96 named exports, base 1, no forwarders — **and ordinals are alphabetical**, not address-ordered |
| 3 | Linear-sweep disassembly of every export with Capstone (`_pxd_conventions.py`) | `ret` form, frame offsets, register use per export, `_pxd_detail.txt` |
| 4 | Cross-checked `__stdcall` three ways (`_pxd_xref.py`) | all 96 `__stdcall`, 0 push-count mismatches, arity histogram 0×37, 1×38, 2×10, 3×5, 4/5/6×1, 7×2, 12×1 |
| 5 | Extended the table with per-export prose and spliced it into the master (`_pxd_rows.py --splice`) | the `<!--ARITY-ROWS-->` block in `PXD32D5-D4.md` |
| 6 | String inventory with VA mapping (`_pxd_strings.py`) | 805 runs ≥ 4 bytes; app strings in `.data`, CRT in `.rdata` |
| 7 | Parsed the import descriptors (`_pxd_imports.py`) | 154 imports / 7 DLLs (KERNEL32 110, WINMM 23, GDI32 7, USER32 5, ADVAPI32 4, LZ32 3, ole32 2) |
| 8 | Traced string cross-references by scanning `.text` for each VA | ownership of the identity, temp-file, log-label and format strings; **7 dead literals** found |
| 9 | Resolved IAT slots to call sites (`_pxd_iatref.py`) | `mixer*` proven in use; 151 of 154 slots referenced, 3 KERNEL32 imports unused |
| 10 | Read the start helper, the thread procedure, `ASetPitch`/`ASetFader`/`RWavePause*`, `DPlayFile*`, `DGetZeit` | seven critical sections, the named event, the non-blocking poll loop, the `0xA0` record array and its two folded bases |
| 11 | Parsed the base-relocation directory block by block | 75 blocks, 9,012 entries (8,967 HIGHLOW + 45 ABSOLUTE) |
| 12 | Wrote the three missing documents (`layout`, `strings-imports`, this file) and corrected the master/engine documents | the set listed in `PXD32D5-D4.md` now exists |
| 13 | Added the workspace meta files `AGENTS.md` and `README.md` (following the existing workspace convention), plus `_pxd_mdcheck.py`; fixed the unescaped pipe in `layout.md` §1 Characteristics | every `*.md` in the directory passes the consistency check (`table_issues []`, paired fences) |

---

## 2. Corrections to earlier readings

Each entry: what was believed, what is true, and the evidence. Nothing was silently overwritten — the
old statements in `PXD32D5-D4.md` / `PXD32D5-D4-engine.md` have been fixed **and** logged here.

1. **"Ord equals # because the export table has no holes."** Wrong. The ordinal table
   (`0x10049D58`) follows the *alphabetically sorted* name table (`0x10049BD8`), so ordinals are
   assigned by name, not by address: EAT[0] = `ABilder` (`0x10017883`, ordinal **1**) while the first
   export in the image is `W2P` (`0x100104C6`, ordinal **96**). Only `ASetFader` happens to land on
   the same number in both columns. The `Ord` column of `PXD32D5-D4.md` now comes from the ordinal
   table, and `_pxd_rows.py` computes it (`ordinal_of`) instead of reusing the row index. Evidence:
   EAT/name/ordinal tables read directly; `_pxd_rows.py` output.
2. **`ARecPlay` "pushes a full 12-dword `APlay` preview event" and `ARecInput` "forwards to
   `0x10014233`."** Both were 1998-engine behaviour, not this build's. Here `ARecPlay`
   (`0x100138B6`, 10 instructions) only calls `AWaveDauer(0x100823FC)` — it measures the temp record
   file — and `ARecInput` (`0x100138DA`) pushes its declared argument into the mixer routine
   `0x100188EA` and returns 0. Evidence: `_pxd_dump.py ARecPlay ARecInput`.
3. **"No mixer-API path in this build … there are no `mixer*` imports."** Wrong. WINMM contributes six
   `mixer*` imports (`mixerOpen`, `mixerClose`, `mixerGetLineInfoA`, `mixerGetLineControlsA`,
   `mixerGetControlDetailsA`, `mixerSetControlDetails`). `mixerOpen` runs in the start helper
   (`0x10017953`), three unexported helpers (`0x100188EA`, `0x10018B34`, `0x10018DA6`) do the line and
   control work for `ALautSet` (`0x10013020`), `ALautGet` (`0x10013185`) and `ARecInput`
   (`0x100138E1`), `AGetInput` calls the API directly, and `mixerClose` runs in `AEnd` (`0x1001721E`).
   The replacement negative in `engine.md` §12 is the true one: there is **no `waveInGetDevCaps`**.
   Evidence: `_pxd_imports.py` + `_pxd_iatref.py 0x10043258 0x1004325c 0x10043260 0x10043264
   0x10043268 0x10043234`.
4. **"`waveInOpen` is called with a NULL callback at `0x10013F9`/`0x1001400`."** Those addresses do
   not exist in this image (they are below the image base + `.text` start). The four real call sites
   are `0x10013400`, `0x10013449` (`ARecTest`) and `0x100135E9`, `0x10013613` (`ARecInit`); all four
   pass `dwCallback = 0`, `dwFlags = 0`, out `&0x10096DEC`. Evidence: `_pxd_iatref.py 0x1004323c`.
5. **The `DPlayFile` signature `DPlayFile(voice, offset, length)`.** Wrong order. Argument 1 is the
   path (`CreateFileA` at `0x1001C514`), argument 3 is the voice (pushed to `DPlayFileClose` at
   `0x1001C4E8` and to `DStart` at `0x1001C4FC`, compared with `0xA` at `0x1001C4D9`). The master
   table's `(char* path, dword a2, int voice)` was right; `engine.md` §4.2 was not.
6. **The mapped-file fields are `slot+0x38` / `slot+0x3C` / `slot+0x40`.** Wrong reading of the
   displacements. `DPlayFileClose` computes `voice*0xA0 + 0x10093F38`, and `0x10093F38 =
   0x10093EB0 + 0x88`, so those are record fields **`+0x88` / `+0x8C` / `+0x90` / `+0x98`** of the
   same `0xA0` array whose DirectSound fields are addressed from `0x10093EB0`. There is no second
   array: `0x88 + 0x10 < 0xA0`, so the four fields fit inside one record, and MSVC simply folded the
   `+0x88` into the displacement. Evidence: `ASetPitch`/`RWavePause1/2` use `0x10093EB0 + voice*0xA0`
   with `+0x44`/`+0x48`; `DPlayFileClose` uses `0x10093F38 + voice*0xA0`; `0x10093F38 - 0x10093EB0
   == 0x88 == 0xA0 - 0x18`.
7. **"`0x1004BA44`/`0x1004BA68` point a second logger at `c:\debug.txt`."** Unfounded. Those two
   literals, plus `%s : %ld (%ld)` (`0x1004BA54`) and `%s : %ld` (`0x1004BA78`, `0x1004BA84`), have
   **no reference anywhere in the file** — a whole-file scan for each dword finds nothing. The only
   debug logger is `Debimem` → `c:\memo.txt`. The same scan condemns `c:\w.wav` (`0x1004B430`) and
   `Test-Meldung` (`0x1004BA90`). Evidence: script in §6.
8. **The command table in `engine.md` §9 was incomplete.** Two names in the block were missing:
   `GetPlayBufferBreite` (`0x1004B690`, referenced at `0x1001E871` inside `REffekt`) and `Reverse`
   (`0x1004B868`, referenced at `0x1001F054` inside `RDrum`). Both are now listed. The claim that the
   names are "contiguous from `0x1004B620` to `0x1004B9C8`" survives — the gaps were in the table, not
   in the data.
9. **"`PXD_Event` is an event tag handed to the mixer."** It is the *name* passed to `CreateEventA` at
   `0x10017972` (manual-reset, initially non-signalled, handle stored at `0x10093A84`). The thread
   receives `&0x10093A84` as its parameter and polls it with `WaitForSingleObject(h, 0)`;
   `AExit`/the stop helper `SetEvent` it to make the loop leave.
10. **`ASelectMic` was called "a `waveIn`-enumeration stub".** Its entry does return 0 unconditionally
    (`xor eax,eax` + jump to the epilogue), but the unreachable body at `0x100192B0`…`0x1001959F` is a
    **mixer** microphone selector: `mixerGetControlDetailsA` at `0x10019421`/`0x10019459`,
    `mixerSetControlDetails` at `0x10019569`, matching the item names `Microphone` (`0x1001948D`) and
    `Micro` (`0x100194DD`). Dead code, but mixer code, not waveIn code.
11. **`engine.md` §7 rows for `ARecPlay`/`ARecInput` cited regions that belong to other exports**
    (`0x10013525` is `ARecDuplex`, `0x10013FBF` does not exist). Fixed to `0x100138B6` and
    `0x100138DA`.
12. **`engine.md` §4.1 attributed `+0x1A` and `+0x24` to "the array".** They are the fields of the
    `WAVEFORMATEX` that `DStart` keeps at `0x10093EC6` (= record base `+0x16`): `nSamplesPerSec` at
    `0x10093ECA` compared with `0xAC44` at `0x1001AF52`, `wBitsPerSample` at `0x10093ED4` compared
    with `0x10` at `0x1001AF47`, both cleared at `0x1001AEE8`/`0x1001AEF1`. Same addresses, better
    description.

---

## 3. Established facts (one-line index)

* Identity: **Dance eJay3** (2001), VC6 release build; uninstall key `…\Uninstall\Dance eJay3`,
  collections `eJay SoundCollection`/`…2`, conversion titles `PXD2Wav`/`WAV2PXD`.
* Output: **DirectSound through `CoCreateInstance`** (CLSID `0x100434B0`, IID `0x100434C0`); no
  `dsound.dll` import. MME `waveOut` only for enumeration and `waveOutSetVolume`; the `mixer` API for
  volume and record input; `waveIn` 44.1 kHz/16-bit/stereo for recording, 40 × `0x1800` buffers, no
  callback.
* Model: voice array `0x10095108`, stride `0x84`, 32 voices default (48 for product type `0x14`);
  30-event rings, stride `0x108`; `0x6921CFF0` = "play to end"; 28 playable DirectSound voices
  (slots `1..0x1C`) in the `0xA0` record array at `0x10093EB0`.
* Control: request word `0x10096D88` (0 idle / 1 stop / 2 start), bounded wait at `0x100144C9`
  (`Sleep(8)` × 20/−30 ≈ 176 ms stop, ≈416 ms start), worker thread at `0x10017AB4` polling
  `WaitForSingleObject(event, 0)` + exit flag `0x100826C0`, created by the start helper `0x100178D4`
  after seven `InitializeCriticalSection` calls and `mixerOpen`.
* Storage: temp names `pxd32p<a-z>.tmp` under `GetTempPathA` with a `c:\` fallback; sample cache
  `(free_MB − 18) MB`; 200 sample slots of `0x528` with `SZDD` (`0x44445A53`) decompression through
  three `LZ32` thunks.
* Project/comment format: the exports that wrote it are stubs, but two unexported functions still
  validate a `LIST`/`INFO`/`ICMT` comment starting with `eJay` and ≥ `0x15` bytes
  (`0x10005D62`, `0x1000814C`).
* Protocol: `REffekt`/`RDrum` are string-command property setters over `lstrcmpiA`, names in
  `0x1004B620`–`0x1004B9C8`.
* Status: `int16` at `0x10096DE0`, returned sign-extended by nearly every export; engine magic
  `0x2A90CB20` at `0x10096DFC`.
* Export ordinals are **alphabetical** (`ABilder` = 1 … `W2P` = 96), unrelated to address order.

---

## 4. Open questions, with how to close each

| # | Question | How to answer |
|---|---|---|
| 1 | **Which host `.exe` shipped this copy?** The image never names it (no `VERSIONINFO`, no resource section). | Look for `pxd32d5.dll` on Dance eJay3 install media, or any binary importing `AStart`/`APlay`/`PInit`. The `P*` wrappers suggest a simple host harness. |
| 2 | **What do the vtable offsets in `DStart`/`ASetFader`/`RWavePause*` really map to?** The labels and argument counts fit one `dsound.h` ordering, but `Play`/`SetFormat`/`Stop` sit one slot lower and the create call is at `+0x0C` where `Compact` (0 args) is expected. | Put a real DX7/DX8 SDK `dsound.h` next to `PXD32D5-D4-layout.md` §5, or trace the calls with a 32-bit VM + sound device. Do not use the method names until this is settled. |
| 3 | **What is the `ICMT` comment payload?** `eJay` + ≥ 21 bytes, then `(len − 0x14) / 2` words. | Save two projects that differ in one property in the host app and diff the `LIST`/`INFO`/`ICMT` chunk. Purely a host-app experiment; static analysis has taken it as far as it goes. |
| 4 | **Meaning of the status-word bits at `0x10096DE0`.** | Enumerate every write (`or al, 2` is already visible at `0x1001AE3C`, i.e. bit 1 = DirectSound init failure) and correlate with `AStart`/`AStop`/record states. Roughly 30 sites, all short. |
| 5 | **What does `APlay`'s four parameter dwords (`event +0xF0`, `+0xF4`, `+0xF8`, `+0x104`) mean?** They are copied through untouched. | Find the host's `APlay` call site (question 1) or a `.pxd` sample that exercises them; alternatively read the mixer step `0x1001D74E` far enough to see which fields it consumes. |
| 6 | **Is the helper at `0x10018715` dead?** It has the mixer shape (guards on `0x100826BC`, `MIXERLINE 0xA8`, component type 7) but nothing references it — no `E8`/`E9`, no absolute dword, no RVA dword anywhere in the file. | Look for a computed call (`call reg` / jump table) in the functions that use the sibling helpers; or accept it as dead code left by an earlier build. |
| 7 | **Is the window procedure at `0x1001847C` reachable?** `ret 0x10`, `WM_DESTROY` → `PostQuitMessage`, else `DefWindowProcA`; unreferenced, and USER32 has no `RegisterClassA`/`CreateWindowExA`. | Same technique as 6. If the host registers the class, it cannot get this address without a reference — so the reading is "dead". |
| 8 | **Which fields of the `0x84` voice record beyond `+0x4A`, `+0x64`, `+0x6A` are used?** | Read the mixer step `0x1001D74E` and the start body `0x10017632` with `_pxd_dump.py 0x1001d74e-0x1001de49`. |
| 9 | **What are `.flt`, `.env1`, `.env2`?** Referenced at `0x10008A52`, `0x10008E25`, `0x10008F50`, inside the pre-export converter object. | Read the function around each reference; the three extensions look like sidecar files next to a `.pxd`. |
| 10 | **What is `ANummer`'s `0x01879487`?** Returned as a literal, outside the image — same constant as in the 1998 engine. | Compare with sibling DLLs (`pxd32d5` builds other than D4, `PXD32HA`, `PXD32RB`); if the value is identical across builds it is a product/build id, not a date or a pointer. |
| 11 | **What does the 90-byte-ish header before PCM samples contain?** `BWaveDauer` only peeks `0x10E` bytes and never walks RIFF chunks properly. | Dump the first bytes of a file the app wrote; `c:\w.wav` is a dead literal here, so use the temp names from `AGetString`. |
| 12 | **What is the ninth/extra voice slot for?** Slots run `1..0x1C` but `APlay` accepts voice `0..0x30`. | Check which voice index `ARecPlay`'s callers and `DPlayFile` use in practice (needs the host), or read the mixer step's voice loop. |

---

## 5. Artifacts on disk (next to the DLL)

| File | Purpose |
|---|---|
| `_pxd_headers.py` | PE headers, section table, data directories — no Capstone, source of `layout.md` §1–§3 |
| `_pxd_conventions.py` | loads the PE, walks export + import tables, sweeps every export, writes `_pxd_detail.txt`; the shared preamble the other scripts `exec` |
| `_pxd_rows.py` | regenerates the `<!--ARITY-ROWS-->` block (evidence from the sweep, prose from its `notes` dict, ordinals from the ordinal table); `--splice` writes it into the master |
| `_pxd_dump.py` | `python _pxd_dump.py APlay 0x100178d4-0x100179dd` — annotated disassembly, calls resolved to export names and IAT slots to import names |
| `_pxd_calls.py` | call map + data references for orienting inside a long export |
| `_pxd_xref.py` | compares each callee's `ret N / 4` with push counts at in-image call sites |
| `_pxd_iatref.py` | `python _pxd_iatref.py 0x10043268` — every `call/jmp [slot]` site, labelled with its export |
| `_pxd_strings.py` | ASCII/Latin-1 runs ≥ n with absolute VAs; writes `_pxd_strings.txt` (805 entries) |
| `_pxd_imports.py` | resolved `IAT_VA dll!name`; writes `_pxd_imports.txt` (154 entries) |
| `_pxd_peek.py` | `python _pxd_peek.py 0x1004B304` — 32 bytes at an absolute VA, hex + ASCII |
| `_pxd_mdcheck.py` | markdown consistency check over all `*.md` (constant pipe count per table block, escaped pipes ignored, paired code fences) |
| `_pxd_detail.txt` | per-export heads, frame offsets and `ret` forms for all 96 exports |
| `_pxd_rows.md` | byproduct of `_pxd_rows.py`; the canonical table lives in `PXD32D5-D4.md`, so treat this as a diff aid |

All of them resolve their paths from `os.path.dirname(os.path.abspath(__file__))`, so the folder can
be moved or copied without edits. Capstone is needed by everything that disassembles; on this machine
it is in a scratch directory:

```bash
python -m pip install --target /tmp/caplib capstone    # once
cd pxd32d5_d4
PYTHONPATH=/tmp/caplib python _pxd_dump.py AStart
```

If `/tmp/caplib` is gone (reboot), reinstall there — never into a project environment.

---

## 6. Reusable snippets

**String cross-reference (used for every row of `strings-imports.md` §3–§5):**

```python
import struct
d = open('pxd32d5_d4.dll', 'rb').read()
text = d[0x1000:0x1000 + 0x41162]          # .text: raw 0x1000 == RVA 0x1000
for va in (0x1004BAA4, 0x1004B160):
    pat = struct.pack('<I', va)
    hits = [hex(0x10001000 + i) for i in range(len(text) - 4) if text.startswith(pat, i)]
    print(hex(va), hits or 'NO CODE REFERENCE')
```

**Dead-literal check** — run the same loop over the *whole* file, not just `.text`, before calling a
string dead: `d.startswith(pat, i) for i in range(len(d) - 4)`. That is what condemns
`c:\debug.txt`, `c:\w.wav` and `Test-Meldung` (§2.7).

**Export ordinals:**

```python
# after the _pxd_conventions.py preamble has run
ordinal_of = {name: ordbase + i for i, name in named.items()}
print(ordinal_of['W2P'], ordinal_of['ABilder'])   # 96 1
```

**Relocation histogram** (produced `layout.md` §4.3): walk `dd[5]`, for each block count
`entry >> 12`; types 3 (`HIGHLOW`) and 0 (`ABSOLUTE`) are the only ones present, and
`8967*2 + 45*2 + 75*8 == 0x48C0`.

**Markdown consistency check** (run after any edit):

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

Tables must have a constant pipe count per block, and fences must pair up.

---

## 7. Recommended next steps, in order of value

1. **Identify the host `.exe`** (question 1) — it unlocks the `APlay` argument semantics (question 5)
   and every "what does the host do with this" question at once.
2. **Settle the vtable mapping** (question 2) — a DX SDK `dsound.h` is enough; until then the layout
   document's §5 stays a guess and nothing should be written on top of those method names.
3. **Status-word bit map** (question 4) — purely static, ~30 sites, would make the API usable from a
   harness.
4. **Read the mixer step `0x1001D74E` and the voice record** (questions 5, 8, 12) — that is the core
   of the engine and the largest remaining gap in `PXD32D5-D4-engine.md`.
5. **Decide about the three dead-code sites** (questions 6, 7) — cheap, and it would let the
   negatives table in `strings-imports.md` §8 say "dead" with certainty rather than "no reference
   found".
6. Only then consider a 32-bit test harness (`PInit` → `AStart` → `APlay` → `PStop` → `PClose`) on a
   VM. Note that 15 exports declare arguments they never read, so the caller must still push the full
   list; use the `Args` column of `PXD32D5-D4.md`, never the name.
