# PXD32D5.DLL (build D4) — strings and imports

Companion to `PXD32D5-D4.md` (exports), `PXD32D5-D4-engine.md` (behaviour) and
`PXD32D5-D4-layout.md` (addresses). This file is the string inventory and the import inventory, plus
the negatives that matter: what sits in the file but is never used, and what is conspicuously absent.

Static analysis only; nothing was loaded or executed. The generated evidence is `_pxd_strings.txt`
(805 entries, minimum run length 4) and `_pxd_imports.txt` (154 entries, resolved `IAT_VA dll!name`).
Addresses are absolute VAs.

---

## 1. Method

* **Strings** — `_pxd_strings.py` walks `.rdata` and `.data`, takes every run of printable ASCII of at
  least *n* bytes and prints `VA  'text'`. Defaults: whole image, `n = 4`:
  ```bash
  python _pxd_strings.py            # whole image -> _pxd_strings.txt
  python _pxd_strings.py 6 0x1004B000 0x1004F000   # app strings only, longer runs
  ```
* **Cross-references** — a string is referenced as an absolute VA, so scan `.text` for the
  little-endian dword. A hit means the string is used; no hit anywhere in the file means the literal is
  dead (§8). This is how `c:\debug.txt`, `c:\w.wav` and `Test-Meldung` were condemned.
* **Imports** — `_pxd_imports.py` walks the descriptors and prints `IAT_VA  dll!name`;
  `_pxd_iatref.py 0x10043268` prints every `call/jmp dword ptr [slot]` site in `.text`, labelled with
  the export that contains it (or `internal after <export>` when the site lies in a gap).

Neither pass needs Capstone; only `_pxd_iatref.py` (which reuses the disassembly sweep) does.

---

## 2. Where the strings live

| Range | Contents |
|---|---|
| `0x10043357`–`0x10044B1C` | `.rdata`, CRT/STL literals: `string too long`, `R6002`…`R6028`, `Microsoft Visual C++ Runtime Library`, locale/day/month tables, country and code-page names, `user32.dll` + `MessageBoxA` (see §8), `sqrt`/`sin`/`frexp` and friends |
| `0x10048C58`–`0x10049A2E` | import descriptors, hint/name tables, ILTs |
| `0x10049E18`–`0x1004A17D` | `pxd32d5.dll` and the **96 export names** (sorted; the export directory's name table) |
| `0x1004B0E8`–`0x1004BB40` | `.data`, **application strings** (§3–§5) |
| `0x1004BB50`–`0x1004C648` | RTTI names (`.?AVexception@@`, `.?AV?$basic_ostream@…`) |
| `0x1004D0D4`–`0x1004D56C` | CRT code-page tables (`040a`/`1252` pairs) |
| in code | four tags that never appear as strings at all — `LIST`, `INFO`, `ICMT`, `eJay` (§6) |

Note the split: **every application string is in `.data`, every library string is in `.rdata`**, and the
export/import names sit in `.rdata` where the loader needs them. The `.data` copy is file-backed only
up to `0x1004F000` (see `PXD32D5-D4-layout.md` §2), and all of §3–§5 lies below that.

---

## 3. Identity

| Address | Text | Code reference |
|---|---|---|
| `0x1004BAA4`, `0x1004BB00` | `Software\Microsoft\Windows\CurrentVersion\Uninstall\Dance eJay3` | `0x10022486` (`ARegUnIn`), `0x100224FF` (`ARegDelete`) |
| `0x1004B218` | `eJay SoundCollection` | `0x10010407` |
| `0x1004B270` | `eJay SoundCollection2` | `0x10010466` |
| `0x1004B160` | `PXD2Wav Konvertierung: pxd -> wav` | `0x10010265` |
| `0x1004B1A4` | `WAV2PXD Konvertierung: wav -> pxd (Textinfo)` | `0x1001032E` |
| `0x1004B424` | `PXD_Event` | `0x10017968` (`CreateEventA` name) |
| `0x1004B118`… | `.?AV…` RTTI names | referenced from `.rdata` structures, never from code |

Four independent signals for **Dance eJay3** (2001): the uninstall key, the two collection names, the
two conversion titles. Unlike the 1998 engine, there is **no vendor/copyright string at all** —
a whole-file search for `Throll`, `Musicsoft`, `Hypergenerator`, `opyright`, `Stuttgart`, `Rave`
returns nothing (§8). The DLL's only self-description is the internal name `pxd32d5.dll` in the export
directory.

---

## 4. Application strings

### 4.1 Bundled files and paths

| Address | Text | Reference |
|---|---|---|
| `0x1004B1FC` | `c:\lang.wav` | `0x100103E9` |
| `0x1004B208`, `0x1004B230` | `c:\pxdlang.pxd` | `0x100103F8` |
| `0x1004B240`, `0x1004B250` | `c:\lang2.wav` | `0x1001042F` |
| `0x1004B260`, `0x1004B288` | `c:\pxdlang3.pxd` | `0x10010457` |
| `0x1004B298` | `c:\lang3.wav` | `0x1001048E` |
| `0x1004B0E8`, `0x1004B0F4`, `0x1004B100` | `.flt`, `.env1`, `.env2` | `0x10008A52`, `0x10008E25`, `0x10008F50` (converter object, before the first export) |
| `0x1004B430` | `c:\w.wav` | **dead** — no reference anywhere in the file |

The `lang*.wav` / `pxdlang*.pxd` group and the two conversion titles are all referenced from the same
unexported block at `0x10010265`–`0x100104A0`, i.e. they belong to a helper that runs *before* `W2P`
(`0x100104C6`), not to `W2P` itself. **[certain]** for the references, **[likely]** that this is the
sound-collection import/export routine.

### 4.2 Temp files

| Address | Text | Reference |
|---|---|---|
| `0x1004B320`, `0x1004B328` | `%c:\` | `0x10010734` (`AGetFree`/`AGetFull` drive probe) |
| `0x1004B334`…`0x1004B374` | `%spxd32pa.tmp`, `%spxd32pb.tmp`, `%spxd32pc.tmp`, `%spxd32p0.tmp`, `%spxd32pz.tmp` | `0x10011140`–`0x100111A0` (temp-name setup) |
| `0x1004B384`…`0x1004B3C4` | `c:\pxd32pa.tmp` … `c:\pxd32pz.tmp` | `0x1001124F`–`0x1001129B` (the `c:\` fallback form) |
| `0x1004B3D4`, `0x1004B9CC` | `%spxd32p%c.tmp` | `0x100137E0` (`AGetString`), `0x10020722` (`RWavToTemp`) |
| `0x1004BA30` | `%spxd32p%c.tmp` | `0x1002188E` (second user, near `Debimem`) |
| `0x1004B3F8`, `0x1004B404`, `0x1004B410` | `pxd01.tmp`, `pxd02.tmp`, `pxd03.tmp` | `0x100142C8`, `0x100142E8`, `0x10014308` (helper before `AExport`) |

The family is `pxd32p<a-z>.tmp` with a drive-letter suffix — the `+0x63` in
`wsprintfA("%spxd32p%c.tmp", …, drive + 0x63)` turns a 1-based index into `'a'`…`'z'`
(`0x1002071C`). There are no 1998-style `pxd32…` temp names here: they are gone.

### 4.3 Record and runtime messages (German)

| Address | Text | Reference |
|---|---|---|
| `0x1004B3E4` | `Fehl beim Rec-Start` | `0x1001384C` (`ARecStart`) |
| `0x1004B9DC` | `Fehler 20` | `0x1002087C` (`RWavToTemp`) |
| `0x1004BA90` | `Test-Meldung` | **dead** |
| `0x1004B9EC` | `c:\memo.txt` | `0x1002180A` (`Debimem`) |
| `0x1004B9F8` | `%s ML:%ld TP:%ld AP:%ld TPa:%ld APa:%ld TV:%ld AV:%ld` | `0x1002183A` (`Debimem`) |

`Fehl` is the same truncation the 1998 build used (`Fehler` → `Fehl`); `Fehler 20` is the conversion
error. Both are **[certain]** attached to their exports by the reference address.

### 4.4 DirectSound / mixer log labels

All are pushed into the internal logger `0x1001064D` right after a failed call, so each label names
the step it reports:

| Address | Label | Reference | Step |
|---|---|---|---|
| `0x1004B464` | `CoCreate` | `0x1001ADDA` | `CoCreateInstance` |
| `0x1004B470` | `Init` | `0x1001AE45` | device `+0x28` |
| `0x1004B478`, `0x1004B4A0`, `0x1004B4B8` | `DS-C-Level` ×3 | `0x1001AE95`, `0x1001AF99`, `0x1001B029` | device `+0x18` |
| `0x1004B484`, `0x1004B4C4` | `Create Buffer0`, `Create Buffer2` | `0x1001AED7`, `0x1001B0BD` | device `+0x0C` |
| `0x1004B494` | `GetFormat0` | `0x1001AF34` | buffer `+0x14` |
| `0x1004B4AC` | `SetFormat0` | `0x1001AFD5` | buffer `+0x38` |
| `0x1004B4D4`, `0x1004B4DC` | `Stop2` ×2 | `0x1001B18B`, `0x1001B1E6` | stop step in `DStart` |
| `0x1004B4E4`, `0x1004B4EC` | `Release`, `Release Sound` | `0x1001B241`, `0x1001B431` | teardown / `DCloseAll` |
| `0x1004B4FC`, `0x1004B50C` | `LOCK` ×2 | `0x1001B698`, `0x1001B976` | the lock helpers |
| `0x1004B504`, `0x1004B514` | `UNLOCK` ×2 | `0x1001B801`, `0x1001BAC3` | the lock helpers |
| `0x1004B51C`, `0x1004B560`, `0x1004B588` | `Pitch` ×3 | `0x1001BBA5`, `0x1001BF1F`, `0x1001C9DE` | `ASetPitch` and two more setters |
| `0x1004B41C` + 15 more | `Fader1` ×16 | `0x100175EE` | volume/fader failures, one string per call site |
| `0x1004B440`, `0x1004B448` | `Play0`, `Play1` | `0x10018570`, `0x10018619` | `RWavePause1` / `RWavePause2` |
| `0x1004B450`, `0x1004B45C` | `Microphone`, `Micro` | `0x1001948D`, `0x100194DD` | `ASelectMic`'s **disabled** body |
| `0x1004B524` | `Set C Pos` ×1 | `0x1001BBF8` | position setter |
| `0x1004B5A0`, `0x1004B5C4`, `0x1004B994` + 3 more | `Set D Pos` ×6 | `0x1001D038`, `0x1001D1CE`, `0x1001FFE7` | position setters |
| `0x1004B598` + 11 more | `GetPos` ×12 | `0x1001CFDB` | position getters |
| `0x1004B558`, `0x1004B570`, `0x1004B580` | `Play` ×3 | `0x1001BE49`, `0x1001C8EE`, `0x1001C97D` | buffer play |
| `0x1004B568` | `DTime` | `0x1001BFFF` | time step |

The duplicated labels are separate string objects, one per call site — the linker did not merge them
(`Fader1` ×16, `GetPos` ×12, `Set D Pos` ×6, `Pitch`/`Play`/`DS-C-Level`/`LOCK`/`UNLOCK`/`Stop2`
×2–3), so counting copies in `_pxd_strings.txt` gives the call-site count for free.

### 4.5 The command protocol

`REffekt` / `RDrum` compare the caller's string against the block `0x1004B620`–`0x1004B9C8` with
`lstrcmpiA`. The full grouped list with addresses is in `PXD32D5-D4-engine.md` §9 — do not duplicate it
here. Two names in that range are easy to miss and are referenced at `0x1001E871`
(`GetPlayBufferBreite`, `0x1004B690`) and `0x1001F054` (`Reverse`, `0x1004B868`); both were missing
from the first draft of that table.

### 4.6 Registry

| Address | Text | Reference |
|---|---|---|
| `0x1004BAA4` | `…\Uninstall\Dance eJay3` | `0x10022486` |
| `0x1004BAE4` | `DisplayName` | `0x100224B4` |
| `0x1004BAF0` | `UninstallString` | `0x100224D8` |
| `0x1004BB00` | `…\Uninstall\Dance eJay3` (second copy) | `0x100224FF` |

---

## 5. Format strings

| Address | Format | Used by |
|---|---|---|
| `0x1004B320`, `0x1004B328` | `%c:\` | `AGetFree` / `AGetFull` drive-root probe |
| `0x1004B334`–`0x1004B374` | `%spxd32pa.tmp` … | temp-name setup (fixed names) |
| `0x1004B3D4`, `0x1004B9CC`, `0x1004BA30` | `%spxd32p%c.tmp` | `AGetString` `0x100137E0`, `RWavToTemp` `0x10020722`, second user `0x1002188E` |
| `0x1004B184` | `PXD2Wav Konvertierung: %s -> %s` | `0x10010282` |
| `0x1004B1D4` | `WAV2PXD Konvertierung: %s -> %s (%s)` | `0x10010352` |
| `0x1004B9F8` | `%s ML:%ld TP:%ld AP:%ld TPa:%ld APa:%ld TV:%ld AV:%ld` | `Debimem` `0x1002183A` |
| `0x1004BA54`, `0x1004BA78`, `0x1004BA84` | `%s : %ld (%ld)`, `%s : %ld` ×2 | **dead** |

There is **no `%03d`/`%02d` layout string** anywhere, so the 1998 `ICMT`-comment writer's 32-number
format did not survive in this build as a `wsprintf` format. What did survive is the raw tag check in
§6.

---

## 6. Strings that exist only as immediates

Four tags are compared as **dword immediates in the code**, so a string dump never sees them
(`0x5453494C` = `LIST`, `0x4F464E49` = `INFO`, `0x544D4349` = `ICMT`, `0x79614A65` = `eJay`):

| Site | Sequence |
|---|---|
| `0x10005D62`–`0x10005D8A` | `cmp [ebp-0x30], 'LIST'` / `[ebp-0x28], 'INFO'` / `[ebp-0x24], 'ICMT'` / `[ebp-0x1c], 'eJay'` / `[ebp-0x20], 0x15` |
| `0x1000814C`–`0x10008174` | the same five comparisons on a different frame |

Both sit in unexported functions (`0x100059A5`-region and `0x10007D40`-region, both before the first
export), both read a 0x18-byte block with `0x10009830`, and both accept the comment only when the
first four bytes are `eJay` **and** the length is at least `0x15` (21). Otherwise they build a table of
`0x3E8` (1000) words instead. **[certain]** for the comparisons; **[likely]** that this is the
saved-project comment (`LIST`/`INFO`/`ICMT`) of the RIFF format the engine still reads, with an
`eJay…` prefix and a 20-byte header followed by 2-byte entries — the word count is computed as
`(length - 0x14) / 2` at `0x10005E62`.

Related dead code: a **window procedure** at `0x1001847C` (`ret 0x10`, `WM_DESTROY` →
`PostQuitMessage(0)` at `0x10018490`, otherwise `DefWindowProcA` at `0x100184A8`) is referenced by
nothing in the file, and USER32 imports no `RegisterClassA`/`CreateWindowExA`, so the DLL cannot create
the window it would serve. **[certain]** for both facts.

---

## 7. Import inventory

154 named imports in 7 DLLs, 151 of which have at least one `call dword ptr [IAT]` site in `.text`.
Full resolved list: `_pxd_imports.txt`. Slots are **not** in name order — always resolve the RVA
through the table.

| DLL | Imports | IAT range | What it is for | Representative sites |
|---|---:|---|---|---|
| `KERNEL32.dll` | 110 | `0x10043034`–`0x100431EC` | files, mapping, threads, critical sections, memory — plus the static CRT's own plumbing | `CreateThread` `0x100179A8`, `InitializeCriticalSection` ×7 `0x100178EF`–`0x10017936`, `WaitForSingleObject` `0x10017ADB`, `CreateEventA` `0x10017972` |
| `WINMM.dll` | 23 | `0x10043218`–`0x10043270` | `waveOut` ×7 (enumeration + master volume), `waveIn` ×9 (recording), `mixer` ×6, `timeGetTime` | `waveOutSetVolume` `0x100130EC`, `waveInOpen` `0x10013400`, `mixerOpen` `0x10017953`, `mixerGetLineInfoA` ×10, `timeGetTime` `0x1001C65D` |
| `USER32.dll` | 5 | `0x10043200`–`0x10043214` | one hidden WndProc's plumbing, the cursor helper, `wsprintfA` | `DefWindowProcA` `0x100184A8`, `PostQuitMessage` `0x10018490`, `LoadCursorA`/`SetCursor` `0x10021796`/`0x100217A7`, `wsprintfA` ×14 |
| `GDI32.dll` | 7 | `0x10043014`–`0x1004302C` | the pattern brush and the sample thumbnails | `CreateBitmap` `0x1001069B`, `CreatePatternBrush` `0x100106AC`, `SelectObject` `0x10019C87`, `DeleteDC` `0x10019D0B` |
| `ADVAPI32.dll` | 4 | `0x10043000`–`0x1004300C` | the uninstall key only | `RegCreateKeyExA` `0x10022486`-region, `RegDeleteKeyA` `0x100224FF` |
| `LZ32.dll` | 3 | `0x100431F0`–`0x100431F8` | `SZDD` decompression, reached through compiler thunks | `jmp dword ptr` thunks at `0x10022E4C` / `0x10022E46` / `0x10022E40` |
| `ole32.dll` | 2 | `0x10043278`–`0x1004327C` | the whole DirectSound path | `CoInitialize` `0x1001AD1B`, `CoCreateInstance` `0x1001AD39` |

**Three imports have no call site at all** — `GetEnvironmentStringsW`, `InterlockedDecrement`,
`VirtualFree`, all KERNEL32. They come from the static CRT's import list; a scan of `.text` for
`FF 15`/`FF 25` targeting their slots finds nothing (151 of 154 slots are referenced). **[certain]**
for the scan, **[likely]** for "unused" — indirect references through a copied pointer cannot be ruled
out statically, but nothing in `.text` names those slots.

The `WINMM` breakdown is the useful part: 7 `waveOut*` + 9 `waveIn*` + 6 `mixer*` + `timeGetTime`.
Note that `waveOut*` is used only for enumeration and `waveOutSetVolume` (see
`PXD32D5-D4-engine.md` §2.3) while `mixer*` carries the actual volume and input controls (§2.6).

---

## 8. Useful negatives

| Absent / dead | Evidence |
|---|---|
| **No `dsound.dll` import** | 7 imports, none from DirectSound; a whole-file byte search for `dsound` finds nothing. The device comes from `CoCreateInstance` (`0x1001AD39`) |
| **No vendor or copyright string** | byte search for `Throll`, `Musicsoft`, `Hypergenerator`, `opyright`, `Stuttgart`, `Rave` → nothing (the 1998 build carries all of them) |
| **No resource section, no `VERSIONINFO`** | data directory 2 is empty; there is no `.rsrc` section at all |
| **No `waveInGetDevCaps`** | not among the 23 WINMM imports |
| **No window-creation API** | USER32 imports are only `DefWindowProcA`, `LoadCursorA`, `SetCursor`, `PostQuitMessage`, `wsprintfA` — no `RegisterClass*`, no `CreateWindowEx*` |
| **No `MessageBoxA` import** | the string `MessageBoxA` at `0x100449CC` and `user32.dll` at `0x100449D8` are CRT literals resolved through `LoadLibraryA`/`GetProcAddress` (`0x10035AB4` region), not IAT slots |
| **No `msvcrt.dll`** | the CRT is static: `R6002`…`R6028`, `Microsoft Visual C++ Runtime Library`, the `ios::` strings and the whole locale table are in `.rdata` |
| **No ACM / decoder imports** | compressed input is `LZ32` (`SZDD`) only — no `acmStream*`, no codec DLL |
| **Dead literals (no reference anywhere in the file)** | `c:\debug.txt` ×2 (`0x1004BA44`, `0x1004BA68`), `%s : %ld (%ld)` (`0x1004BA54`), `%s : %ld` ×2 (`0x1004BA78`, `0x1004BA84`), `c:\w.wav` (`0x1004B430`), `Test-Meldung` (`0x1004BA90`) |
| **Dead code** | the window procedure at `0x1001847C`; the mixer helper at `0x10018715` (no `E8`/`E9` and no absolute/RVA pointer anywhere); `ASelectMic`'s body behind its unconditional `xor eax,eax` |
| **Three unreferenced KERNEL32 imports** | `GetEnvironmentStringsW`, `InterlockedDecrement`, `VirtualFree` (§7) |

---

## 9. Reproducing this file

```bash
python _pxd_strings.py                                  # -> _pxd_strings.txt (805 entries)
python _pxd_imports.py                                  # -> _pxd_imports.txt (154 entries)
PYTHONPATH=/tmp/caplib python _pxd_iatref.py 0x10043268 # who calls this slot
PYTHONPATH=/tmp/caplib python _pxd_dump.py ARegUnIn     # confirm a string's owner
```

The whole-file dword scan used for the dead-literal table (§8) is in
`PXD32D5-D4-worklog.md` §6.
