# PXD32D5.DLL (build D4) — image layout

Companion to `PXD32D5-D4.md` (exports, calling conventions) and `PXD32D5-D4-engine.md` (behaviour).
This file is the static picture: headers, sections, directories, runtime globals, record layouts and an
address → section map. Addresses are absolute VAs (image base `0x10000000`), never bare RVAs.

Ground rules: static analysis only. The file was parsed, never loaded, executed, registered or
modified. §1–§4 need only `python _pxd_headers.py` plus a few lines of `struct`; §5–§7 additionally
need Capstone (`PYTHONPATH=/tmp/caplib python _pxd_dump.py …`).

---

## 1. Headers

| Property | Value |
|---|---|
| File | `pxd32d5_d4.dll`, 348,160 bytes (`0x55000`) |
| DOS header | `MZ` at 0, standard "This program cannot be run in DOS mode." stub, `e_lfanew` = `0xF0` |
| COFF header | `machine = 0x014C` (i386), 4 sections, `NumberOfSymbols = 0` (stripped), timestamp `0x3B5FE644` → 2001-07-26 09:43:32 UTC, `SizeOfOptionalHeader = 0xE0` |
| Optional header | magic `0x010B` (PE32), linker **6.0** (Visual C++ 6.0), no pdb path |
| Image base | `0x10000000` |
| Entry point | RVA `0x32A3D` → `0x10032A3D` — the CRT startup (`_DllMainCRTStartup`), inside `.text`, well past the last export |
| SizeOfImage | `0x9F000` (651,264) → image occupies `0x10000000`–`0x1009F000` |
| SectionAlignment / FileAlignment | `0x1000` / `0x1000` |
| SizeOfHeaders | `0x1000` |
| OS / image / subsystem version | 4.0 / 0.0 / 4.0 |
| Subsystem | 2 = `WINDOWS_GUI` |
| DllCharacteristics | `0x0000` — **no** `RELOCS_STRIPPED`, no `NX_COMPAT`, no `DYNAMIC_BASE`, no `NO_SEH`, no `FORCE_INTEGRITY` |
| CheckSum | 0 (never signed or verified) |
| Stack reserve / commit | `0x100000` / `0x1000` (VC6 defaults) |
| Heap reserve / commit | `0x100000` / `0x1000` |
| Characteristics | `0x210E` = `EXECUTABLE_IMAGE \| 32BIT_MACHINE \| LINE_NUMS_STRIPPED \| LOCAL_SYMS_STRIPPED` |

Because `RELOCS_STRIPPED` is clear and a base-relocation directory exists, the image is relocatable
despite the fixed `0x10000000` base; because `DllCharacteristics` is 0, it has no ASLR, no DEP
attribute and no load config (no `/GS` cookie — consistent with VC6). It is 32-bit x86, so it cannot
be loaded into a 64-bit process without a thunking layer. **[certain]** — all of it is header bytes,
printed by `_pxd_headers.py`.

---

## 2. Sections and the file ↔ image map

| Section | VA range | vsize | File range (offset) | rawsize | Characteristics | Decoded |
|---|---|---:|---|---:|---|---|
| `.text` | `0x10001000`–`0x10042162` | `0x41162` | `0x001000`–`0x043000` | `0x42000` | `0x60000020` | CODE \| EXECUTE \| READ |
| `.rdata` | `0x10043000`–`0x1004A182` | `0x7182` | `0x043000`–`0x04B000` | `0x8000` | `0x40000040` | INITIALIZED_DATA \| READ |
| `.data` | `0x1004B000`–`0x10098AEC` | `0x4DAEC` | `0x04B000`–`0x04F000` | `0x4000` | `0xC0000040` | INITIALIZED_DATA \| READ \| WRITE |
| `.reloc` | `0x10099000`–`0x1009E230` | `0x5230` | `0x04F000`–`0x055000` | `0x6000` | `0x42000040` | INITIALIZED_DATA \| READ \| DISCARDABLE |

Two consequences that shape every other document:

* **`file offset == RVA` for the first three sections** (raw pointer and VA coincide), so a byte at
  file offset *n* in `.text`/`.rdata`/`.data` is at VA `0x10000000 + n`. Only `.reloc` breaks the rule
  (RVA `0x99000`, raw `0x4F000`). The whole file is exactly `0x1000 + 0x42000 + 0x8000 + 0x4000 +
  0x6000 = 0x55000` = 348,160 bytes — headers, four section bodies, nothing else (no overlay,
  no certificate).
* **`.data` has only `0x4000` bytes on disk but `0x4DAEC` bytes in memory.** Everything from
  `0x1004F000` to `0x10098AEC` (0x49AEC ≈ 294 KB) is zero-initialised BSS: it never appears in a file
  dump. **Every runtime global in these documents — `0x1006xxxx`, `0x1007xxxx`, `0x1008xxxx`,
  `0x1009xxxx` — lives in that zero-filled range** and can only be observed through the code that
  names it. **[certain]**

The inter-section gaps are `0xE9E` bytes before `.rdata` and `0xE7E` before `.data` (section
alignment padding, filled with `0x00`), and `0x10042162`–`0x10043000` after `.text` with `0xCC`
padding.

---

## 3. Data directories

| # | Name | RVA | Size | VA | Note |
|---:|---|---|---|---|---|
| 0 | Export | `0x49A30` | `0x752` | `0x10049A30` | 96 named exports, no forwarders (§4) |
| 1 | Import | `0x48C58` | `0xA0` | `0x10048C58` | 7 descriptors + null = `0xA0` (§4) |
| 5 | Base relocation | `0x99000` | `0x48C0` | `0x10099000` | 75 blocks, 9,012 entries (§4) |
| 12 | IAT | `0x43000` | `0x284` | `0x10043000` | the first `0x284` bytes of `.rdata` |

All twelve other directories are **empty**: Resource (2), Exception (3), Security (4), Debug (6),
Architecture (7), GlobalPtr (8), TLS (9), LoadConfig (10), BoundImport (11), DelayImport (13), CLR
(14), Reserved (15). **[certain]**

Useful negatives that follow from that: there is **no `.rsrc` section and no `VERSIONINFO`** (nothing
in the image says who built it — no company name, no product version, no original filename beyond the
internal `pxd32d5.dll`); no delay-load imports; no TLS callbacks (no `__declspec(thread)`); no load
config (no security cookie, no SEH table — the SEH frames seen in the code are on-stack, which is why
`W2P`, `BWaveDauer`, `Stretcher` and `ALoad` show two `ret` forms); no bound imports (the image is
never pre-linked to a specific DLL build); and no Authenticode signature.

---

## 4. Export, import and relocation directories

### 4.1 Export directory — `0x10049A30`

| Field | Value |
|---|---|
| `Characteristics` / `TimeDateStamp` | `0` / `0x3B5FE644` (same stamp as the COFF header) |
| `Name` | RVA `0x49E18` → `pxd32d5.dll` (the *internal* name; the file on disk is `pxd32d5_d4.dll`) |
| `OrdinalBase` | **1** |
| `NumberOfFunctions` / `NumberOfNames` | 96 / 96 (every function is named, no holes) |
| `AddressOfFunctions` (EAT) | RVA `0x49A58`, 96 dwords → `0x10049A58`–`0x10049BD8` |
| `AddressOfNames` | RVA `0x49BD8`, 96 dwords → `0x10049BD8`–`0x10049D58` |
| `AddressOfNameOrdinals` | RVA `0x49D58`, 96 words → `0x10049D58`–`0x10049E18` |
| Name strings | `0x10049E24`–`0x1004A17D` (`ABilder` … `Stretcher`, 96 names) |

* The name pointer table is **sorted ASCII-ascending** (`ABilder`, `ABildpos`, `AClose`, …, `W2P`) —
  the PE loader binary-searches it — and the ordinal table runs `0 … 95` in that same order. So
  **ordinal = 1 + alphabetical index**, unrelated to address order: EAT[0] is `ABilder` (`0x10017883`,
  ordinal 1) while EAT[95] is `W2P` (`0x100104C6`, ordinal 96). The `Ord` column of
  `PXD32D5-D4.md` comes from this table. **[certain]**
* The EAT is therefore **not** RVA-sorted; a scan that assumes "lowest ordinal = first function in the
  image" is wrong here.
* **No forwarders**: every EAT entry points outside the `0x49A30`–`0x4A182` directory range, i.e. all
  96 are real code RVAs inside `.text`.

### 4.2 Import directory — `0x10048C58`

Seven `IMAGE_IMPORT_DESCRIPTOR`s (20 bytes each) plus the null descriptor fill exactly the advertised
`0xA0`. All timestamps and forwarder chains are 0 (not bound).

| # | DLL | ILT (thunks) | IAT (slots) | Names |
|---:|---|---|---|---:|
| 0 | `WINMM.dll` | `0x10048F10` | `0x10043218` | 23 |
| 1 | `USER32.dll` | `0x10048EF8` | `0x10043200` | 5 |
| 2 | `GDI32.dll` | `0x10048D0C` | `0x10043014` | 7 |
| 3 | `ole32.dll` | `0x10048F70` | `0x10043278` | 2 |
| 4 | `LZ32.dll` | `0x10048EE8` | `0x100431F0` | 3 |
| 5 | `ADVAPI32.dll` | `0x10048CF8` | `0x10043000` | 4 |
| 6 | `KERNEL32.dll` | `0x10048D2C` | `0x10043034` | 110 |

154 named imports + 7 null terminators = 161 thunks × 4 = `0x284`, exactly the IAT directory size —
the IAT is contiguous and sits at the head of `.rdata` (`0x10043000`–`0x10043284`), the hint/name
tables and ILTs follow at `0x10048C58`–`0x10049A2E`. The descriptor order in memory is *not* the
alphabetical or the dependency order; never address a slot by position, always resolve the RVA
through the table (`_pxd_imports.py`). See `PXD32D5-D4-strings-imports.md` §7 for the per-DLL
inventory and which slots have no caller at all.

### 4.3 Base relocations — `0x10099000`

75 blocks (page RVA + block size), 9,012 entries: **8,967 `IMAGE_REL_BASED_HIGHLOW`** (type 3) and
**45 `ABSOLUTE`** padding entries (type 0) — `8967*2 + 45*2 + 75*8 = 0x48C0`, the exact directory
size. The page RVAs span `0x1000`–`0x4D000`: 66 blocks in `.text`, 6 in `.rdata`, 3 in the
file-backed part of `.data`, none in BSS and none in `.reloc`. **[certain]** — parsed block by block.

So the image expects to be rebased, and every absolute VA in `.text` (globals, string addresses,
`jmp`/`call` targets) is patched on load; the addresses used in these documents are the *preferred*
ones, which is what a static read gives you.

---

## 5. Interface offsets observed on the DirectSound objects

`DStart` obtains the device through `CoCreateInstance` and then drives it (and the buffers it creates)
through vtable calls. The offsets below are **[certain]** — they are the literal displacements in the
`call dword ptr [reg + N]` instructions, with the call site and the log label that follows each one.
The **method names are [guess]**: the two objects do not fit a single published vtable order (see the
note under the table).

| Object | Offset | Stack args after `this` | Call site | Label pushed afterwards | [guess] reading |
|---|---:|---|---|---|---|
| device `0x10093ED8` | `+0x0C` | 3 — `&0x10093EDC`, `&0x10093EB0`, 0 | `0x1001AEC5`, `0x1001B0AB` | `Create Buffer0` `0x1004B484`, `Create Buffer2` `0x1004B4C4` | `CreateSoundBuffer(desc, &buffer, NULL)` |
| device `0x10093ED8` | `+0x18` | 2 — hwnd `0x1008E378`, 1 | `0x1001AE83`, `0x1001AF88`, `0x1001B013` | `DS-C-Level` ×3 (`0x1004B478`, `0x1004B4A0`, `0x1004B4B8`) | `SetCooperativeLevel(hwnd, DSSCL_PRIORITY)` |
| device `0x10093ED8` | `+0x28` | 1 — 0 | `0x1001AE16` | `Init` `0x1004B470` | `Initialize(NULL)` |
| buffer `0x10093EB0` | `+0x14` | 3 — `&0x10093EC6`, `0x12`, `&[ebp-8]` | `0x1001AF22` | `GetFormat0` `0x1004B494` | `GetFormat(lpWAVEFORMATEX, 18, &written)` |
| buffer `0x10093EB0` | `+0x38` | 1 — `&0x10093EB4` | `0x1001AFC3` | `SetFormat0` `0x1004B4AC` | `SetFormat(lpWAVEFORMATEX)` |
| buffer slot 1..0x1C | `+0x30` | 3 — 0, 0, 1 | `0x10018607` (`RWavePause2`) | `Play1` `0x1004B448` | `Play(0, 0, 1)` |
| buffer slot 1..0x1C | `+0x48` | 0 | `0x1001855E` (`RWavePause1`) | `Play0` `0x1004B440` | `Stop()` |
| buffer slot 1 | `+0x3C` | 1 — attenuation `0x10096DF4` | `0x100175DC` (`ASetFader`) | `Fader1` `0x1004B41C` | `SetVolume(level)` |
| buffer slot 1..0x1C | `+0x44` | 1 — `bias + 0x93A8` | `0x1001BF0D` (`ASetPitch`) | `Pitch` `0x1004B560` | `SetFrequency(hz)` |

Two independent signals disagree, which is why the names stay guesses:

* the labels and the argument *counts* fit the published `IDirectSound` / `IDirectSoundBuffer` order
  for `GetFormat` (`+0x14`), `SetCooperativeLevel` (`+0x18`) and `Initialize` (`+0x28`);
* but `Play` (`+0x30`), `SetFormat` (`+0x38`), `Stop` (`+0x48`) and the `ASetFader`/`ASetPitch`
  setters each sit **one slot (4 bytes) below** where that same order puts them, and the create call
  sits at `+0x0C` where the order expects `Compact` (0 arguments) — yet it is passed 3.

So either the host was compiled against a `dsound.h` whose table differs from the one recalled here,
or two of the labels are simply mis-assigned by the original author. **[guess]** for the mapping.
Closing it: put a real DirectSound SDK `dsound.h` (DX7/DX8) next to these offsets, or trace the calls
on a 32-bit VM with a sound device; recorded as an open question in `PXD32D5-D4-worklog.md` §4.
Until then, treat the offsets as opaque — nothing else in the document set depends on their names.

Note that `ASetFader` addresses the object as the *absolute* dword `0x10093F50`, i.e. record 1 of the
array in §7.3 — it is a fixed "master fader on voice 1", not a per-voice loop.

---

## 6. Runtime globals

Every address below is zero at load (BSS, §2) until the listed code writes it. "Evidence" is the
instruction or call that names the address; the *meaning* is tagged where it is inferred. The table
is grouped by subsystem, and it is deliberately exhaustive only for the globals the other documents
cite — a full pointer trace has not been done.

### 6.1 Core state

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x10096DFC` | dword | engine magic `0x2A90CB20`; written by `0x1001186B`-region, cleared by `0x10011ED0`-region, tested in 18 paths | `APlay` `0x1001777B`, thread helper `0x100178D4` |
| `0x10096DE0` | int16 | status word returned sign-extended by nearly every export | `movsx eax, word ptr [0x10096DE0]` at every epilogue; cleared in `ADevice` `0x10012AF0` |
| `0x10096CC8` | dword | engine-open flag, set 1 by the start helper | `0x1001793C` |
| `0x10096D50` | word | device-open flag (1 = DirectSound open) | `DStart` `0x1001B036`, tested in `DPlayFileClose` `0x1001C27B` |
| `0x10096D52` | dword | enables the mixing step inside `DPlayUpdate` | `DPlayUpdate` `0x1001DE49`-region |
| `0x10096D54` | dword | record path initialised | `ARecInit` `0x1001353D` |
| `0x10096D88` | dword | transport request: 0 idle / 1 stop / 2 start | `AStop` `0x10014537`, `AStart` `0x10017610`, thread `0x10017B14`–`0x10017B41` |
| `0x100826C0` | dword | exit flag for the worker thread | `AExit` `0x100179DD`, tested at `0x10017AEA` |
| `0x10082BE4` | dword | `== 1` enables `RTimer` in the loop | thread `0x10017B01` |
| `0x10096D00` | dword | non-zero bails out of `DPlayFile`/`DPlayUpdate` | `0x1001C4C6`, `DPlayUpdate` `0x1001DE66`–`0x1001DE8D` |
| `0x10082B14` | dword | last HRESULT from a vtable call, tested before logging | `ASetFader` `0x100175DF`, `ASetPitch` `0x1001BF10` |

### 6.2 Host, thread, locks

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x1008E378` | HWND | host window, shared by `AFenster` and `AInit` | `AInit` `0x100114DA`, passed to `SetCooperativeLevel` at `0x1001AE6D` |
| `0x1008E354` | dword | value returned by `ABildpos` | `0x100178CB` |
| `0x10093A84` | HANDLE | the named event `PXD_Event` (manual-reset, initially non-signalled) | `CreateEventA` at `0x10017972`, `ResetEvent` `0x10017983`, `SetEvent` `0x100179F0` / `0x10017A10` |
| `0x1008E62C` | HANDLE | engine thread handle | `CreateThread` result `0x100179AE`, `SetThreadPriority` `0x100179BC` |
| `0x1008E360` | dword | thread id out-parameter | `CreateThread` arg 6 at `0x10017993` |
| `0x10093A60`, `0x10093A90`, `0x100826D0`, `0x100826A0`, `0x100950E0`, `0x10082730`, `0x10082718` | CRITICAL_SECTION ×7 | the seven locks initialised at start-up; `0x10082718` guards the mixer/DirectSound step, `0x100950E0` the clock, `0x10082730` the transfer | `InitializeCriticalSection` ×7 at `0x100178EF`–`0x10017936` |
| `0x1009085C` | dword | `GetExitCodeThread` out-parameter | `0x100179C2` |

### 6.3 DirectSound and the record array (§7.3)

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x10093EB0` | ptr | primary buffer (`CreateSoundBuffer` out), also record-array base | `DStart` `0x1001AEAC` |
| `0x10093ED8` | ptr | `IDirectSound*` (`CoCreateInstance` out) | `0x1001AD26` |
| `0x10093EDC` | struct | DSBUFFERDESC passed to `+0x0C` | `0x1001AEB1` |
| `0x10093EB4`, `0x10093EC6` | WAVEFORMATEX ×2 | set-format block and get-format block (18 bytes each) | `0x1001AFAF`, `0x1001AF0F` |
| `0x10093F38` | — | folded base for the mapping fields (record `+0x88`) | `DPlayFileClose` `0x1001C2AA` |
| `0x10096CBC` | dword | raw DirectSound play cursor | `DGetZeit` `0x1001C1C3` |
| `0x10093FAC` | dword | current play time, refreshed from `0x10096CBC` | `DGetZeit` `0x1001C1C8` |
| `0x10096DF4` | long | last fader attenuation written by `ASetFader` | `0x10017570`–`0x100175A9` |
| `0x1008BBE0` | word | waveOut mode chosen by `ADevice` (0..3) | `ADevice` body |

### 6.4 Voices, events, parameters

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x10095108` | array | voice/channel array, stride `0x84` | `APlay` `0x10017797` (`imul …, 0x84`) |
| `0x1004B2F8` … `0x1004B2FE` | word ×4 | voice counts, default 32 in `.data`, rewritten to 48 for product type `0x14` | file bytes; init helper |
| `0x1004B300` | dword | waveOut device id / mapper value `0xFFFFFFFF` | `ADevice` |
| `0x10082B1C` | dword ×`0x12B` | `RWaveParam` parameter block | `AInit` `0x1001159E` |
| `0x10082B68` | word | set to `0x7FFF` at init | `0x100115AB` |
| `0x100668F0` | dword ×25 | semitone rate table written literally by `AInit` | `0x1001167A`–`0x1001176A` |
| `0x10066968`–`0x10066974` | double ×4 | the constants 1.0 / 2.0 / 3.0 / 4.0 | CRT store calls `0x100115EA`–`0x10011629` |
| `0x1008E370` | dword | sample-cache budget in bytes (`(free_MB − 18) << 20`) | `0x10017632`-region |
| `0x100829F0` | dword | start position handed to `AStart` → thread → `0x10017632` | `AStart` `0x1001761D` |

### 6.5 Recording

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x10096DEC` | HANDLE | `waveIn` device handle | `waveInOpen` out at `0x100133FB`, `0x100135E4` |
| `0x10096DF0` | HANDLE | record file handle | `ARecStart` `0x1001380D` |
| `0x100823FC` | char[] | record temp file name (also measured by `ARecPlay`) | `AWaveDauer` argument `0x100138CE` |
| `0x10083020` | WAVEHDR ×40 | prepare/queue array, stride `0x20` | `ARecInit` walk |
| `0x10096CF8` | dword | `ARecTest` result 0 / 1 / 2 | `ARecTest` `0x10013348` |
| `0x10096CFC` | dword | duplex flag | `ARecDuplex` `0x10013528` |
| `0x10082600`, `0x10066808` | dword | live level and peak | `ARecPegel` `0x10013FEB`, `0x10013FF2` |
| `0x10096CE4` … `0x10096CF0` | dword ×4 | elapsed-time counters | `AGetTime`, cleared by `AInit` |

### 6.6 Mixer, samples, browser, debug

| Address | Type | Meaning | Evidence |
|---|---|---|---|
| `0x100826BC` | HANDLE | `mixerOpen` handle, closed by `AEnd` | `0x1001794E` / `0x1001721E` |
| `0x10082AD8` | dword | cached speaker level | `ALautSet` `0x10013020`-region, `ALautGet` `0x10013185` |
| `0x10093B88` | ptr ×200 | sample slot pointer array (lazy allocation, `0x528` each) | `ALoad`/`AClose` |
| `0x10096CD0` | dword | guard value `0x4D2` (1234) in `ALoad` | `ALoad` head |
| `0x100829EC`, `0x100829F4` | HBITMAP, HBRUSH | `Extra`'s cached pattern pair, flag `0x10096CCC` | `Extra` `0x1001069B` |
| `0x1008E41C` | word | browser cursor | `ASortInit`/`ASortOut` |
| `0x10090860` | word ×6400 | browser permutation index | `ASortIn` `0x10010B4A`-region |
| `0x100836F0` | ptr | browser name table base, stride `0x80` | `ASortIn` |
| `0x10082224`, `0x10096BD8` | char[] | the two strings written by `AExport` | `AExport` |
| `0x1004B9EC`, `0x1004BA44` | literals | `c:\memo.txt`, `c:\debug.txt` | `Debimem`, internal logger |

---

## 7. Structures

Sizes and field offsets are **[certain]** where they come from an `imul`/`idiv` or a literal store;
the *meaning* of a field is as tagged in `PXD32D5-D4-engine.md`.

### 7.1 Voice / channel record — 0x84 bytes, array at `0x10095108`

| Offset | Size | Use | Evidence |
|---:|---|---|---|
| `+0x4A` | word | pan/centre, written by `AMitte` after classification | `0x10095152` = base + `0x4A` |
| `+0x64` | dword | pointer to the 30-event ring | `APlay` `0x100177AF` |
| `+0x6A` | word | ring write index, `(i + 1) % 30` | `0x100177A2`, `0x1001786A` |

The rest of the 0x84 bytes is not yet mapped. Count: 32 by default, 48 for product type `0x14`
(`0x1004B2F8`-region); `AMitte` accepts indices `0..0x30` (0..48).

### 7.2 Event record — 0x108 bytes, 30 per voice

Written by `APlay` (`0x100177B7`–`0x10017859`):

| Offset | Source | Use |
|---:|---|---|
| `+0x000` | arg 9, `& 0xFFFFFFFC` | start (byte offset, frame-aligned) |
| `+0x004` | start + arg 10, or `0x6921CFF0` when arg 10 ≤ 0 | end; `0x6921CFF0` = "to the end" |
| `+0x008` | arg 11, `&~3` | level |
| `+0x010` | arg 1 (word) | sound number |
| `+0x012` | arg 7 (`lstrcpyA`) | text, fixed field of the record |
| `+0x0F0` | arg 6 | dword parameter |
| `+0x0F4` | arg 4 | dword parameter |
| `+0x0F8` | arg 5 | dword parameter |
| `+0x0FC`, `+0x100` | args 2, 3 | the two name pointers (equalised when either is NULL) |
| `+0x104` | arg 12 | dword parameter |

`+0x105`..`+0x107` and `+0x018`..`+0x0EF` are not written by `APlay`; whether they belong to this
record or to padding is **open** (`PXD32D5-D4-worklog.md` §4).

### 7.3 DirectSound / mapping record — 0xA0 bytes, base `0x10093EB0`

One array, two folded displacements: `0x10093EB0 + voice*0xA0` and `0x10093F38 + voice*0xA0`
(`= record + 0x88`). See §5 for the interface offsets and `PXD32D5-D4-engine.md` §4.1 for the field
table. Record 0 is a scratch block (device pointer, two `WAVEFORMATEX`s, `DSBUFFERDESC`); records
`1..0x1C` are the 28 playable voices.

| Offset | Use |
|---:|---|
| `+0x00` | `IDirectSoundBuffer*` (slot 0 = primary buffer) |
| `+0x04`, `+0x16` | `WAVEFORMATEX` blocks (set / get) |
| `+0x28`, `+0x2C` | `IDirectSound*` and `DSBUFFERDESC` (slot 0 only, see the caveat below) |
| `+0x44` | "in use" dword (`== 1`) |
| `+0x48` | pitch value |
| `+0x88`, `+0x8C`, `+0x90`, `+0x98` | mapped-file handle, mapped view, mapping handle, clear-on-close |
| `+0x94` | right operand of the `DPlayFileCheck` comparison |

Caveat: `0x10093ED8`/`0x10093EDC` sit at what would be record 0's `+0x28`/`+0x2C`, and `0x10093FAC`
(the play-time scalar) sits inside record 1's `+0x5C` — but `DGetZeit` writes `0x10093FAC` as a plain
absolute, not indexed. So the block is best read as "an array whose first record doubles as device
scratch, with a scalar allocated inside it", not as a clean C array. **[likely]**

### 7.4 Sample slot — 0x528 bytes, 200 slots, pointer array at `0x10093B88`

| Offset | Use | Evidence |
|---:|---|---|
| `+0xF4` | DIB section / bitmap handle | `DeleteObject` in `AClose` |
| `+0xF8` | compatible DC | `DeleteDC` in `AClose` |
| `+0x100` | copy of the file header | `ALoad` |
| `+0x128` | magic probe (`0x44445A53` = `SZDD`) | `ALoad` `0x1001988A`-region |

### 7.5 Other blocks

| Block | Size | Base | Use |
|---|---:|---|---|
| `WAVEHDR` queue | 40 × `0x20` | `0x10083020` | `waveInPrepareHeader` / `waveInAddBuffer` ring |
| Parameter block | `0x12B` dwords | `0x10082B1C` | `RWaveParam(index, value)` / `RGetParam` |
| Map/stream block | `0x124` bytes | `0x100824E0` | zeroed by `AInit` |
| Display block | `0x2128` bytes | `0x1008E730` | zeroed by `AInit` |
| Browser name table | stride `0x80` | pointer at `0x100836F0` | `ASortIn` records, cap `0x1900` |
| Browser permutation | `0x1900` words | `0x10090860` | `qsort` output, `ASortOut` reads it back |
| Effect/drum globals | — | `0x10082B6C`–`0x10082BA4`, `0x1009071C`–`0x10090778` | written per command by `REffekt`/`RDrum` |
| Peak table | `0x3B1` (945) entries | `0x1008F774` | written by `RDrum`/`DPlayFile` |
| `MIXERLINE` | `0xA8` | on the stack (`[ebp-0xDC]`) | the mixer helpers, `cbStruct` written first |

---

## 8. Address → section cheat sheet

| Range | What lives there |
|---|---|
| `0x10000000`–`0x10001000` | DOS header, stub, COFF + optional headers, section table (SizeOfHeaders `0x1000`) |
| `0x10001000`–`0x100104C5` | `.text`, **before the first export**: the converter/stretcher object code (methods `0x1000506E`, `0x10005444`, the `ICMT` readers at `0x100059A5` and `0x10007D40`) |
| `0x100104C6`–`0x100224FB` | the 96 export bodies **and the unexported helpers that sit in the gaps** (pump `0x10017255`, start helper `0x100178D4`, thread proc `0x10017AB4`, mixer helpers `0x10018715`–`0x10019023`) |
| `0x10022500`–`0x10042162` | `.text` tail: compiler thunks (LZ32 thunks `0x10022E40`–`0x10022E4C`), the static CRT (memset `0x10031910`, qsort `0x100323D4`, startup `0x10032A3D`), C++ string/RTTI code |
| `0x10043000`–`0x10043284` | **IAT** (161 slots, 7 DLLs) |
| `0x10043285`–`0x10048C57` | `.rdata` literals: doubles (`0.1` at `0x10043418`, CLSID/IID at `0x100434B0`/`0x100434C0`), CRT/STL strings, locale and code-page tables |
| `0x10048C58`–`0x10049A2E` | import descriptors, hint/name tables, ILTs |
| `0x10049A30`–`0x1004A17D` | **export directory**, EAT, name table, ordinal table, the 96 export names |
| `0x1004B000`–`0x1004BB40` | `.data` file-backed: application strings (`.flt`/`.env1`/`.env2`, conversion titles, temp names, log labels, the `REffekt`/`RDrum` command table `0x1004B620`–`0x1004B9C8`, uninstall key) and initialised words such as the voice counts at `0x1004B2F8` |
| `0x1004BB50`–`0x1004F000` | `.data` file-backed CRT/STL: RTTI names, `R6xxx` runtime-error strings, code-page tables |
| `0x1004F000`–`0x10098AEC` | **zero-filled BSS — all runtime globals** (see §6) |
| `0x10099000`–`0x1009E230` | `.reloc` (75 blocks, discarded after load) |
| `0x1009E230`–`0x1009F000` | alignment tail to `SizeOfImage` |

---

## Reproducing this file

```bash
python -m pip install --target /tmp/caplib capstone      # once, scratch dir only
cd pxd32d5_d4
python _pxd_headers.py                                   # §1–§3, no Capstone
PYTHONPATH=/tmp/caplib python _pxd_dump.py DStart ASetPitch DPlayFileClose   # §5
PYTHONPATH=/tmp/caplib python _pxd_dump.py 0x100178d4-0x100179dd            # §6.2
PYTHONPATH=/tmp/caplib python _pxd_imports.py                                # §4.2
```

For the export directory fields (§4.1) and the relocation histogram (§4.3) the snippets are in
`PXD32D5-D4-worklog.md` §6.
