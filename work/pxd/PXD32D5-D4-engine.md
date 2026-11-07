# PXD32D5.DLL (build D4) — what the engine does

Companion to `PXD32D5-D4.md` (exports + calling conventions). This file is the behavioural map: what
the code does, with the address / string / import evidence for each claim.

Everything below comes from static reading of `pxd32d5_d4.dll` (348,160 bytes, link stamp 2001-07-26).
Confidence is marked per claim: **[certain]** = directly observable in the code, **[likely]** = the only
reading that fits all the evidence, **[guess]** = plausible, not proven.

---

## 1. One-paragraph summary

`pxd32d5.dll` is the audio engine of **Dance eJay3**. It is a DirectSound-based sampler and sequencer:
the host pushes sample events into per-voice rings with `APlay`, a worker thread mixes them and keeps up
to 28 DirectSound buffers fed, and the same module owns sample loading and decompression (200 slots,
Microsoft `SZDD`), waveform thumbnails as GDI DIB sections, a `waveIn` recording path with 40 queued
buffers, a temp-file cache for converted samples, a text-command property protocol (`REffekt`, `RDrum`),
and the product's uninstall registry entry. Output is 44.1 kHz 16-bit stereo throughout.

Unlike the 1998 engine, this build does **not** import `dsound.dll`:
the device is created at runtime with `CoCreateInstance` on `CLSID_DirectSound`
(`{47D4D946-62E8-11CF-93BC-444553540000}` at `0x100434B0`) and `IID_IDirectSound`
(`{279AFA83-4981-11CE-A521-0020AF0BE560}` at `0x100434C0`). **[certain]**

Identity evidence:

| Evidence | Address | Text |
|---|---|---|
| Uninstall key | `0x1004BAA4` | `Software\Microsoft\Windows\CurrentVersion\Uninstall\Dance eJay3` |
| Bundled collection name | `0x1004B218` | `eJay SoundCollection` |
| Conversion strings | `0x1004B160`, `0x1004B1A4` | `PXD2Wav Konvertierung: pxd -> wav`, `WAV2PXD Konvertierung: wav -> pxd (Textinfo)` |
| Wake/exit event name | `0x1004B424` | `PXD_Event` |

---

## 2. Initialisation contract

### 2.1 The magic and the status word

Two globals gate everything:

* `0x10096DFC` holds **`0x2A90CB20`** once the engine is up. It is written by the internal helper at
  `0x1001186B` (store near `0x10011CCF`) and cleared by `0x10011CFB` (store near `0x10011ED0`); the
  immediate appears in 18 code paths. `APlay` checks it at `0x1001777B` and returns 0 instead of
  scheduling when it is missing. **[certain]**
* `0x10096DE0` is the `int16` **status word**. Nearly every export ends with
  `movsx eax, word ptr [0x10096DE0]`, so the caller receives the engine's last status, not a local
  result. `ADevice` zeroes it at `0x10012AF0`. **[certain]**

### 2.2 `AInit(hwnd)` — `0x1001149F`

Ordered, from the stores:

| Step | Evidence |
|---|---|
| Clear the five record counters `0x10096CF8`, `0x10096CE4`, `0x10096CE8`, `0x10096CEC`, `0x10096CF0` | `0x1001149F`–`0x100114CD` |
| Store the host window at `0x1008E378` | `0x100114DA` |
| Clear the map/stream block `0x100825C0`, `0x100825C4`; set `0x100825CC = 1` | `0x100114DF`–`0x100114F3` |
| Zero-fill the voice array: `memset(0x10095108, 0, 0x84 * count)`, plus blocks at `0x100824E0` (0x124) and `0x1008E730` (0x2128) | calls to the CRT memset at `0x10031910`, `0x10011546`–`0x10011573` |
| Zero `0x12B` dwords at `0x10082B1C`; set `0x10082B68 = 0x7FFF`; zero `0x3C` dwords at `0x1008B774` | `0x1001159E`, `0x100115AB`, `0x100115D6` |
| Build the 25-entry rate table at `0x100668F0` (see §4.4) | `0x1001167A`–`0x1001176A` |
| Store the four doubles 1.0 / 2.0 / 3.0 / 4.0 at `0x10066968`, `0x1006696C`, `0x10066970`, `0x10066974` | four CRT store calls at `0x100115EA`–`0x10011629` |
| Set `0x100826C4 = 0x7D00` (32000) or `0x72D8` (29400) for product type 2 | `0x10011637`, `0x1001164D` |
| `AMemory()`, then `0x10082670 = 0x7274` (29300) or `0x9354` (37716) for types 2/3/4; `0x1008BADC = 0x28`; `0x1008274C = 0x1800` | `0x10011675`, `0x100117A0`–`0x100117D7` |
| Temp-file setup (`0x10010D83`), magic write (`0x1001186B`), engine thread start (`0x100178D4`), then two further inits at `0x10021D8A` and `0x1001A900` | calls at `0x100117E3`–`0x10011816` |

The argument is stored at the same global `AFenster` writes, so "the host window" is one dword shared by
both exports. **[certain]**

### 2.3 `ADevice(...)` — `0x10012AEA`

1 dword is declared, never read, and the body works purely off globals. It zeroes the status word
(`0x10012AF0`), then probes the **waveOut** device space even though playback later goes to DirectSound:

* `waveOutGetNumDevs()` at `0x10012AF9`;
* mode `0` = mapper: `0x1004B300 = 0xFFFFFFFF`, `waveOutGetDevCapsA` at `0x10012B60`;
* modes `1`, `2`, `3`: `waveOutOpen` / `waveOutGetDevCapsA` / `waveOutGetID` / `waveOutClose` rounds
  over the enumerated devices, storing the surviving index at `0x1004B300`.

The chosen mode lands in the word `0x1008BBE0` (`0`..`3`). Final state: `0x1008BBE0 = 0`,
`0x1004B300 = 0`. **[certain]** for the calls; **[likely]** that mode 0 is "wave mapper".

The surviving value is then used by `ALautSet`, which still drives volume through
`waveOutSetVolume` (`0x100130EC`) after opening `0x100829E8` with a 44.1 kHz stereo format built at
`0x10082AF0`. So MME is used for **device enumeration and the master volume**, DirectSound for the
audio path. **[certain]**

### 2.4 `DStart(...)` — `0x1001ACDA`

The DirectSound bring-up, 243 instructions. It calls `CoInitialize` (`0x1001AD1B`, and again on each
retry) and `CoCreateInstance(CLSID_DirectSound, NULL, CLSCTX_ALL, IID_IDirectSound, &0x10093ED8)`
(`0x1001AD39`), retrying up to three times. Every step is followed by an `HRESULT` check that logs a
fixed label through the internal logger at `0x1001064D`:

| Label | Address | Step |
|---|---|---|
| `CoCreate` | `0x1004B464` | after `CoCreateInstance` |
| `Init` | `0x1004B470` | interface method `+0x28` |
| `DS-C-Level` | `0x1004B478` | method `+0x18`, argument = the host window `0x1008E378` |
| `Create Buffer0` | `0x1004B484` | method `+0x0C` |
| `GetFormat0` | `0x1004B494` | method `+0x14`, writes a format block ending at `0x10093EC6` |
| `SetFormat0` | `0x1004B4A0` | method `+0x18` (again) and `+0x38` with `&0x10093EB4` |
| `Create Buffer2` | `0x1004B4C4` | second `+0x0C` call |
| `Release`, `Release Sound` | `0x1004B4E8`, `0x1004B4EC` | teardown in `DCloseAll` |
| `LOCK`, `UNLOCK` | `0x1004B4F8`, `0x1004B504` | the lock/unlock helpers |

After `GetFormat0` the code compares the returned rate with `0xAC44` (44100) at `0x1001AF52`; when it
does not match, the 44.1 kHz block is written and the buffer is re-armed. A `Sleep` follows at
`0x1001AFE8` before the final cooperative-level call and the `0x10096D50 = 1` "device open" flag
(`0x1001B036`). **[certain]** for the sequence and the labels; **[likely]** for the mapping of the
numeric offsets onto the documented DirectSound methods — see the open question in the worklog.

### 2.5 `PInit` / `PStart` / `PClose` — `0x10022318`, `0x1002234A`, `0x10022339`

Thin convenience wrappers, useful as documentation of the intended host order:

```
PInit()  = ADevice(0); AInit(0); RWaveParam(0x3C, 0x7D00)
PStart() = AStart(0xA80F570); RWaveParam(0x32, 1)
PClose() = AStop(); AEnd()
```

**[certain]** (direct call/disassembly reading).

### 2.6 The mixer path

The WinMM mixer API is imported (6 of WINMM's 23 imports) and is opened once during start-up:

| Step | Evidence |
|---|---|
| `mixerOpen(&0x100826BC, 0, 0, 0, 0)` in the engine-start helper; the handle is zeroed again if the call fails | `0x10017953` |
| Three unexported helpers in the `ADSoff`–`AGetInput` gap walk a destination line (`MIXERLINE`, size `0xA8`, component type 7), its sources and the fader control `0x50030001`, then write it back: `0x100188EA`, `0x10018B34`, `0x10018DA6` | `mixerGetLineInfoA` at `0x10018925`, `0x10018984`, `0x10018B7F`, `0x10018BDE`, `0x10018DE6`, `0x10018E45`; `mixerSetControlDetails` at `0x10018B0F`, `0x10018D7B` |
| `ALautSet` -> `0x10018B34` (speaker volume), `ALautGet` -> `0x10018DA6` (read back, `0x10013185` is the second instruction of the export), `ARecInput` -> `0x100188EA` (record-input fader) | direct call sites `0x10013020`, `0x10013185`, `0x100138E1` |
| A fourth helper of the same shape starts at `0x10018715` (guards on `0x100826BC`, `MIXERLINE` `0xA8`, component type 7) but **nothing in the image references it**: no `E8`/`E9` lands there and the dword `0x010018715` (or RVA `0x18715`) does not occur anywhere in the file | `_pxd_dump.py 0x10018706-0x10018770`, byte scan |
| `AGetInput` calls `mixerGetLineInfoA`/`mixerGetLineControlsA`/`mixerGetControlDetailsA` itself | `0x10019063`, `0x10019130`, `0x100191B5` |
| `mixerClose(0x100826BC)` in `AEnd` | `0x1001721E` |

So the volume and record-input controls ride on the mixer API while the audio itself rides on
DirectSound; MME `waveOut` (see §2.3) is only used for enumeration and for `waveOutSetVolume`.
**[certain]** for the calls and the addresses.

---

## 3. The voice and event model

### 3.1 Records

| Item | Value | Evidence |
|---|---|---|
| Voice array base | `0x10095108` | `APlay` `0x10017797` (`imul eax, 0x84` + add) |
| Voice stride | `0x84` bytes | same |
| Voice count word | `0x1004B2F8`, default **32** (`0x20`) in `.data` at `0x1004B2F8`..`0x1004B2FE` | file bytes, `0x1004B2F8` |
| Voice count for product type `0x14` | **48** (`0x30`), written to `0x1004B2F8`, `0x1004B2FA`, `0x1004B2FC`, `0x1004B2FE` | init helper `0x1001186B` region |
| Event ring pointer | voice `+0x64` | `0x100177AF` |
| Event write index | voice `+0x6A` (word), advanced `(i+1) % 30` | `0x100177A2`, `0x1001786A` |
| Event stride | `0x108` bytes | `imul edx, edx, 0x108` at `0x100177A6` |
| Events per voice | **30** | `idiv 0x1E` at `0x1001786D` |
| Pan/centre word | voice `+0x4A` (from `0x10095152 = 0x10095108 + 0x4A`) | `AMitte` |

### 3.2 Event fields (written by `APlay`)

| Offset | Source | Reading |
|---|---|---|
| `+0x000` | arg 9, masked `& 0xFFFFFFFC` | start time (byte offset) |
| `+0x004` | start + arg 10, or `0x6921CFF0` when arg 10 `<= 0` | end time; the sentinel means "to the end" |
| `+0x008` | arg 11, masked `&~3` | level |
| `+0x010` | arg 1 (word) | sound number |
| `+0x012` | arg 6, `lstrcpyA` | text field |
| `+0xF0` | arg 4 | dword parameter |
| `+0xF4` | arg 3 | dword parameter |
| `+0xF8` | arg 5 | dword parameter |
| `+0xFC` / `+0x100` | arg 2 / arg 3 | the two name pointers, made equal when either is NULL |
| `+0x104` | arg 12 | dword parameter |

**[certain]** for the stores (`0x100177B7`–`0x10017859`). The `&~3` masks on start, duration and
level round everything to one 16-bit stereo frame (4 bytes), so scheduling never lands mid-frame.
**[certain]**

### 3.3 `APlay` — `0x1001775B`, 12 dwords

```
eax = arg9 & 0xFFFFFFFC            ; start, frame aligned
arg10 &= 0xFFFFFFFC                ; duration
arg11 &= 0xFFFFFFFC                ; level
if [0x10096DFC] != 0x2A90CB20: return 0
voice = 0x10095108 + arg8 * 0x84
event = voice->[0x64] + voice->[0x6A] * 0x108
event->[0x10] = (word) arg1
if arg3 == 0: arg3 = arg2
if arg2 == 0: arg2 = arg3
event->[0xFC] = arg2 ; event->[0x100] = arg3
event->[0x104] = arg12 ; event->[0xF4] = arg4 ; event->[0xF8] = arg5 ; event->[0xF0] = arg6
lstrcpyA(event + 0x12, arg7)
event->[0] = arg9
event->[4] = (arg10 > 0) ? arg9 + arg10 : 0x6921CFF0
event->[8] = arg11
voice->[0x6A] = (voice->[0x6A] + 1) % 30
return 0
```

So the argument order is: sound number, name, name2, param A, param B, param C, text, **voice index**,
start, duration, level, extra. [certain] for the mechanics; the *meaning* of the four parameter dwords
(`0xF0`..`0x104`) is not recoverable from this function alone — they are copied through untouched.

`PPlay` (`0x10022370`) shows the command form: it calls `APlay(0, 0, 0, 0, 0, "c", a1..a6)` — the
literal at `0x1004B304` is the one-character string `"c"`, i.e. a command event rather than a sample.
[certain]

### 3.4 `AMitte(voice, value)` — `0x100112B6`

Not a plain setter. It **classifies** the value into a three-state zone before storing it at voice
`+0x4A`:

| Input | Stored |
|---|---|
| `0x75`..`0x8B` (117..139) | `0` |
| `< 0x0F` (15) | `1` |
| `> 0xF0` (240) | `2` |
| anything else | the raw word |

Voice index must be `0..0x30` (0..48) or the call returns 0. Reading: `0` = centre, `1` = hard left,
`2` = hard right, else an intermediate pan value. **[likely]**

### 3.5 Voice parameters on the DirectSound side

| Export | Address | Effect |
|---|---|---|
| `ASetFader(_, level)` | `0x10017567` | maps `10..30000` onto a signed attenuation (floor `-0xF60` = −3936) and calls voice-table offset `+0x3C` on `0x10093F50` (slot 1); failure logs `Fader1` (`0x1004B41C`) |
| `ASetPitch(bias)` | `0x1001BE5C` | for voices `1..0x1C` stores `bias + 0x93A8` into slot `+0x48`, and for active slots calls table offset `+0x44`; failure logs `Pitch` (`0x1004B560`) |
| `RWavePause1()` | `0x100184E9` | walks active voices and calls offset `+0x48`; failure logs `Play0` (`0x1004B440`) |
| `RWavePause2()` | `0x1001858C` | the mirror image, offset `+0x30`; failure logs `Play1` (`0x1004B448`) |

**[certain]** for the walk and the offsets; the offset→method naming is discussed in
`PXD32D5-D4-layout.md` §5.

---

## 4. The DirectSound output layer

### 4.1 Buffers

One `0xA0`-stride record array at `0x10093EB0` holds the DirectSound state *and* the reproducible
voices; `voice * 0xA0` is added to that base everywhere (`ASetPitch`, `RWavePause1/2`, `DPlayUpdate`).
`DPlayFileClose` and `DPlayFileCheck` add the same product to the displacement `0x10093F38`, which is
`0x10093EB0 + 0x88` — i.e. MSVC folded `record + 0x88` into the address, so there is **no second
array**; the two bases are one array seen through two folded constants. **[certain]** for the
addresses; **[likely]** for "one array", the arithmetic being the evidence (see below).

| Field (record = `0x10093EB0 + voice * 0xA0`) | Use |
|---|---|
| `+0x00` | buffer interface pointer (slot 0 = primary buffer, the `CreateSoundBuffer` out-parameter `&0x10093EB0`) |
| `+0x04` | format block handed to the `+0x38` call in `DStart` (`&0x10093EB4` at `0x1001AFAF`) |
| `+0x16` | second WAVEFORMATEX, the `GetFormat` target `0x10093EC6`; its `nSamplesPerSec` (`+0x1A`, `0x10093ECA`) is compared with `0xAC44` at `0x1001AF52` and its `wBitsPerSample` (`+0x24`, `0x10093ED4`) with `0x10` at `0x1001AF47`; both are cleared at `0x1001AEE8`/`0x1001AEF1` |
| `+0x28` | `IDirectSound*` (`0x10093ED8`), the `CoCreateInstance` out-parameter |
| `+0x2C` | DSBUFFERDESC (`0x10093EDC`), the first argument of the `+0x0C` create call |
| `+0x44` | dword `== 1` "voice in use" marker (`DPlayUpdate`, `ASetPitch`, `RWavePause1/2`) |
| `+0x48` | pitch/rate value written by `ASetPitch` (`bias + 0x93A8`) |
| `+0x88` | mapped-file handle, the one `DPlayFileClose` tests and finally closes (displaced base `0x10093F38`) |
| `+0x8C` | mapped view, `UnmapViewOfFile` at `0x1001C2DD` (base `0x10093F3C`) |
| `+0x90` | second handle, `CloseHandle` at `0x1001C2FA` (base `0x10093F40`) |
| `+0x94` | right operand of the `DPlayFileCheck` comparison (base `0x10093F44`) |
| `+0x98` | dword cleared with the record (base `0x10093F48`) |

Slots `1..0x1C` (1..28) are the playable voices — every loop starts at 1, never 0 — so slot 0
(`0x10093EB0`..`0x10093F50`) is a scratch block for the device pointer, the two format blocks and the
buffer descriptor, even though its offsets are spelled exactly like a voice record. **[certain]** for
the loop bounds and the field uses listed.

The apparent "second array" resolves arithmetically: `0x10093F38 - 0x10093EB0 == 0x88 == 0xA0 - 0x18`,
so `voice * 0xA0 + 0x10093F38 == record + 0x88`, and `+0x98` (`0x10093F48`) still lands inside the same
`0xA0`-byte record (`0x88 + 0x10 < 0xA0`). Earlier text read those displacements as `slot+0x38` /
`slot+0x3C` / `slot+0x40`; that reading is wrong, see the corrections log in `PXD32D5-D4-worklog.md`
§2.

### 4.2 Mapped-file playback

`DPlayFile(path, a2, voice)` (`0x1001C49A`, 218 instructions) sets up a memory-mapped view for one
voice. Argument 3 is the voice: it is pushed straight into `DPlayFileClose` at `0x1001C4E8` and into
`DStart` at `0x1001C4FC`, and it is compared with `0xA` at `0x1001C4D9`. Argument 1 is the file name
handed to `CreateFileA` at `0x1001C514`. (An earlier note called these `voice, offset, length`; that
ordering is wrong — see `PXD32D5-D4-worklog.md` §2.)

`DPlayFileCheck(voice)` (`0x1001C44B`, 23 instructions) returns 0 when the mapped-file handle at
`voice * 0xA0 + 0x10093F38` is 0, otherwise calls `DGetZeit(voice)` and compares
`voice * 0xA0 + 0x10093F0C` with `voice * 0xA0 + 0x10093F44`, returning 1 when the left side is `<=`
the right. For voice 1 the left operand *is* `0x10093FAC`, the global `DGetZeit` refreshes at
`0x1001C1C8` — so the left side is "current play time" and the right side is the stored end value.
**[certain]** for the two displacements and the direction of the compare; **[guess]** for which return
value means "ran out of data".

`DPlayFileClose(voice)` (`0x1001C278`) unmaps and closes (displacements relative to `0x10093F38` =
record `+0x88`):

```asm
01c2dd  mov ecx, [eax + 0x10093f3c]     ; record +0x8C, mapped view
01c2e4  call UnmapViewOfFile
01c2f3  mov eax, [edx + 0x10093f40]     ; record +0x90, mapping handle
01c2fa  call CloseHandle
01c309  mov edx, [ecx + 0x10093f38]     ; record +0x88, file handle
01c310  call CloseHandle
```

So samples larger than the mixer's buffer budget are played **straight out of a mapped file** rather
than copied into RAM. **[likely]** — the pattern (map, poll position, unmap) is unambiguous; the policy
that decides when to use it is inside `DPlayFile`.

### 4.3 `DPlayUpdate` — `0x1001DE49`

The per-tick mixer step, 0 arguments, returns the step result:

1. Bail out with 0 if `0x10096CC8` (device/engine open) is 0 (`0x1001DE56`).
2. Bail out with 1 if the record word `0x100823F8 == 1` or the state word `0x10096D50 != 1`
   (`0x1001DE66`–`0x1001DE8D`), or if `0x10096D00 != 0`.
3. Walk voices `1..0x1C`; for every slot whose `+0x44` word is 1, call `DPlayFileClose` (`0x1001DED2`).
4. Take the lock `0x10082718`, call the internal mixing step `0x1001D74E` when `0x10096D52 == 1`,
   release the lock, return the step result.

**[certain]**

`DGetZeit` (`0x1001C1BD`) is the clock this feeds: it moves `0x10096CBC` into `0x10093FAC` and, when
the device is open (`0x10096CC8 != 0`), runs the internal update `0x1001BF40` twice under the lock
`0x100950E0`. `AGetTime` (`0x100173C7`) combines it with `waveInGetPosition`
(`0x10017435`) and four counters at `0x10096CE4`..`0x10096CF0`.

### 4.4 The rate table at `0x100668F0`

25 dwords, written literally by `AInit` (`0x1001167A`–`0x1001176A`):

```
0x8000 0x7979 0x7204 0x6BA1 0x65A4 0x5FDC 0x5A7A 0x5566 0x50A0 0x4C17 0x47D9 0x43CD 0x4000
0x3CBC 0x3902 0x35D1 0x32D2 0x2FEE 0x2D3D 0x2AB3 0x2850 0x260B 0x23EC 0x21E6 0x2000
```

`0x4000` sits in the middle and `0x8000 / 0x4000 = 2`, `0x2000 / 0x4000 = 0.5`; the 24 steps between
them are equal-ratio (each ≈ 1.0595 = 2^(1/12)). That is a **pitch/rate multiplier table in semitones**,
−12..+12, with 1.0 at index 12. **[certain]** for the values, **[likely]** for the semitone reading.

---

## 5. Transport and the worker thread

### 5.1 Request word

`0x10096D88` is the transport request, read by the worker:

| Value | Meaning | Written at |
|---|---|---|
| `0` | idle | `AInit` region, `AStop` (`0x10014537` sets 1, the worker clears it) |
| `1` | stop requested | `AStop` `0x10014537` |
| `2` | start requested | `AStart` `0x10017610` |

### 5.2 The bounded wait — `0x100144C9`

```asm
0144cd  mov dword ptr [ebp - 4], 0x14      ; counter = 20
0144d4  cmp dword ptr [0x10096d88], 0
0144db  jle 014512                          ; nothing requested -> return
0144dd  push 8
0144df  call Sleep
0144e5  dec counter
0144ee  cmp counter, 0 / jge loop
0144f4  if counter < 0 && [0x10096d88] == 1 -> return    ; stop acknowledged
0144ff  cmp counter, -0x1e / jge loop
014505  if [0x10096d88] == 2 -> return                    ; start acknowledged
014510  jmp loop
```

`Sleep(8)` per iteration, counter starts at 20 and runs down to −30: the stop path returns after 22
iterations (**≈176 ms**) and the start path after at most 52 (**≈416 ms**). After the timeout the
export simply returns the current status word, so a stuck worker does not hang the host forever.
**[certain]**

`AStart` (`0x10017603`) is the whole export:

```asm
mov  [0x10082bec], 0
mov  [0x10096d88], 2
eax = [ebp+8] ; mov [0x100829f0], eax
call 0x100144c9
movsx eax, word [0x10096de0]
ret 4
```

`AStop` (`0x10014516`) clears nine globals (`0x10096D30`, `0x10096D34`, `0x10082BEC`, `0x10093A7C`,
`0x100826B8`, `0x1008B764`, `0x100835A8`, `0x10096D18`, `0x1008E63C`), sets `0x10096D88 = 1`, waits and
returns 1. **[certain]**

### 5.3 The thread

`0x100178D4` is the engine-start helper (called from `AInit`). In order it does: the magic check;
seven `InitializeCriticalSection` calls (`0x10093A60`, `0x10093A90`, `0x100826D0`, `0x100826A0`,
`0x100950E0`, `0x10082730`, `0x10082718`); `0x10096CC8 = 1`; `mixerOpen(&0x100826BC, 0, 0, 0, 0)` at
`0x10017953` (the handle is zeroed again if the call fails); `CreateEventA(NULL, TRUE, FALSE,
"PXD_Event")` at `0x10017972`, whose handle is stored at `0x10093A84` and immediately `ResetEvent`ed;
and `CreateThread(NULL, 0, 0x10017AB4, 0x10093A84, 0, &0x1008E360)` at `0x100179A8` — the thread
parameter is **the address of the event handle**, not the handle itself. The thread handle goes to
`0x1008E62C` and `SetThreadPriority(handle, 1)` follows. **[certain]**

The thread procedure at **`0x10017AB4`** takes one argument (`ret 4`) and is SEH-framed. Its loop is a
**non-blocking poll**, not a blocking wait:

```asm
017ad3  push 0                      ; dwMilliseconds = 0
017ad5  mov  eax, dword [ebp+8]     ; lpParameter = &0x10093A84
017ad8  mov  ecx, dword [eax]       ; the event handle
017ada  push ecx
017adb  call WaitForSingleObject    ; 0 -> event set by AExit -> leave the loop
017ae5  je   0x10017b71
017aea  cmp  dword [0x100826c0], 0  ; exit flag written by AExit
017af1  ja   0x10017b71             ; > 0 -> leave the loop
017af5  call 0x10017255             ; pump
```

Each pass then calls, in order: the pump at `0x10017255`, `RTimer` **only when `0x10082BE4 == 1`**
(`0x10017B01`), `DPlayUpdate`, and the request word — `0x10014589` handles a stop request and
`0x10017632` (with the position from `0x100829F0`) handles a start request; both clear `0x10096D88`
back to 0. `0x10017B4D`–`0x10017B5C` is the SEH funclet for the frame. **[certain]** for the call graph
and the exit conditions; the pump itself is at `0x10017255`–`0x100173C7`.

`0x10017632` is the start body: it computes the sample-cache budget
`0x1008E370 = (AGetFree(drive) - 0x12) << 20`, but only when free space is at least `0x14` (20 MB),
otherwise 0 — i.e. **the cache gets `(free_MB − 18)` MB**. It then resets the active voices
`0..word [0x1004B2FA]`. **[certain]**

`AExit` (`0x100179DD`) sets `0x100826C0 = 1` and `SetEvent(0x10093A84)`; the stop helper `0x100179FD`
waits 2000 ms for the thread and then calls `TerminateThread`. **[certain]**

`AEnd` (`0x1001710E`) is the orderly shutdown: magic check, `AStop`, thread stop `0x100179FD`, clear the
state, delete the temp files through `OpenFile(..., 0x200)` at `0x100823FC`, `0x1008E64C`, `0x10082310`,
`0x1008BAE8`, and close the mixer handle `0x100826BC`. **[certain]**

---

## 6. Sample slots, loading and `SZDD`

### 6.1 Slots

`0x10093B88` is an array of **200 (`0xC8`) pointers**, allocated lazily; each slot object is `0x528`
bytes.

| Field | Use |
|---|---|
| `+0xF4` | DIB / bitmap handle (`DeleteObject` in `AClose`) |
| `+0xF8` | DC handle (`DeleteDC` in `AClose`) |
| `+0x100` | header copy |
| `+0x128` | magic probe |

`AClose(slot)` (`0x10019CB1`) tears one slot down; `ACloseAll()` (`0x10019D5E`) loops all 200 and does
the same. Both are **[certain]** — the loop bound `0xC8` and the two GDI calls are visible.

### 6.2 `ALoad(path)` — `0x1001974A`

315 instructions, one argument:

1. Guard on `0x10096CD0 == 0x4D2` (1234) — a "loaded" counter.
2. `OpenFile(path, ...)` (`0x100197B8`), then `_hread` of the header (`0x10019846`), `_lclose`.
3. If the header magic is **`0x44445A53` = `"SZDD"`** (Microsoft `LZ` compression), the body is expanded
   with the **LZ32** thunks: `LZOpenFileA` at `0x10022E4C`, `LZRead` at `0x10022E46`, `LZClose` at
   `0x10022E40` (`0x1001988A`–`0x100199E2`).
4. The decoded audio is read with `_hread` (`0x100199E2`, `0x10019BAD`).
5. A thumbnail is created with `CreateDIBSection` (`0x10019A37`), `CreateCompatibleDC` (`0x10019BD0`)
   and `SelectObject` (`0x10019C87`), and the handles stored at slot `+0xF4` / `+0xF8`.

**[certain]** for every call; **[likely]** that the DIB is the waveform thumbnail the `AWelle` path
draws.

### 6.3 `AWelle` and thumbnails

`AWelle(x, y, path)` keeps a 117-instruction body that opens the sample, computes a min/max envelope and
merges it into the display path; it is not a pure stub like its 1998 counterpart. `ABilder` (7
dwords) stores seven geometry/handle values into `0x1008BAB8`, `0x1008BABC`, `0x10082B0C`, `0x1006680C`,
`0x100950FC`, `0x1007A214`, `0x10066800`. `ABildpos` returns `0x1008E354`. **[certain]** for the
stores; **[guess]** for which of the seven is the window, the DC, the bitmap and the four rectangles.

`Extra`/`ExtraAus` are the GDI brush pair: `CreateBitmap(8, 8, 1, 1, 0x1004B2B0)` +
`CreatePatternBrush` (`0x1001069B`, `0x100106AC`), cached at `0x100829EC` / `0x100829F4` behind flag
`0x10096CCC`; `ExtraAus` deletes both. **[certain]**

---

## 7. Recording

The record path is `waveIn` at **44.1 kHz, stereo, 16-bit** (`0xAC44`, average `0x15888`), with
**40 (`0x28`) buffers of `0x1800` (6144) bytes**; header blocks start at `0x10083020` with stride
`0x20` (`WAVEHDR` is 32 bytes). **[certain]** (`ARecTest` builds the format at `0x100133A1`–`0x100133D9`;
`ARecInit` walks the header array at `0x100136AA`–`0x1001374F`).

| Export | Address | Role |
|---|---|---|
| `ARecInit(ignored)` | `0x1001353D` | magic-guarded; `ARecStop`, clears globals, `waveInOpen` into `0x10096DEC`, `waveInReset`, `waveInPrepareHeader` + `waveInAddBuffer` for the 40 headers; sets `0x10096D54 = 1` |
| `ARecStart()` | `0x1001380D` | `waveInStart`, creates the record file `0x10096DF0` from `0x100823FC` with `0x2191C0` bytes reserved; logs `Fehl beim Rec-Start` (`0x1004B3E4`) on failure; sets `0x100823F8 = 2` while running |
| `ARecTimer()` | `0x10013FFB` | drains finished buffers, `WriteFile`s them to the record file, updates the peak at `0x10066808`, `waveInUnprepareHeader`, re-prepares and re-queues |
| `ARecStop()` | `0x10013AA7` | 323 instructions of teardown: `waveInReset`, unprepare per buffer, close the file, clear the state words |
| `ARecPegel(sel)` | `0x10013FE2` | selector 0 → live level `0x10082600`, else peak `0x10066808` |
| `ARecTest(path)` | `0x10013348` | self-test: opens waveIn twice (directly, then through `ADSoff`) and stores 0/1/2 in `0x10096CF8` |
| `ARecDuplex(ignored)` | `0x10013525` | sets the duplex flag `0x10096CFC = 1` |
| `ARecPlay()` | `0x100138B6` | magic-guarded, 10 instructions: measures the *temp record file* with `AWaveDauer(0x100823FC)` and returns that duration; no preview event is pushed |
| `ARecInput(dword)` | `0x100138DA` | pushes the declared argument into the mixer routine `0x100188EA` (which sets the waveIn destination fader to 0), then `xor eax,eax; ret 4` |

**[certain]** for the import calls and the constants. The record buffer headers are re-queued in
`ARecTimer`, so recording is a classic **double-buffer ring**, not a callback — no `waveInProc` is
passed (all four `waveInOpen` sites pass `dwCallback = 0` and `dwFlags = 0`: `0x10013400` and
`0x10013449` in `ARecTest`, `0x100135E9` and `0x10013613` in `ARecInit`; the out-parameter is always
`&0x10096DEC`). **[certain]**

---

## 8. Conversion, temp files and the `W2P` path

* `RWavToTemp(in, out, drive, a4, a5, a6, a7)` — `0x1002071C`-region, **912 instructions**, 7 arguments.
  It converts/loads a wave file into a temp file, caching the result by the triple
  `0x10096D24`, `0x10096D28`, `0x10096D2C`, and formats the target name with
  `wsprintfA("%spxd32p%c.tmp", ..., drive + 0x63)` at `0x1002071C` (the `+ 0x63` turns a 1-based index
  into `'a'`..`'z'`). **[certain]** for the format string and the argument count.
* `RWaveLaden(path, a2, a3, a4, a5)` — `0x10019E…`, 5 arguments: calls
  `RWavToTemp(path, 0x1008E64C, a3, a4, a5, 0, 0)` and then maps `0x1008E64C`. **[certain]** (2 in-image
  callers push 5).
* `W2P(a, b)` — `0x100104C6`: constructs/drives the converter object at `0x100564E0`
  (`0x1000F55D`, `0x1000F580`, `0x1000F59D`, run at `0x1000FB3E`). Direction is **WAV → PXD**, matching
  the `WAV2PXD Konvertierung` string at `0x1004B1A4`. **[likely]**
* Temp names are formatted from the `GetTempPathA(0xFA, 0x10093AA8)` result with the fallback literal
  `c:\`; the five buffers are `0x100823FC`, `0x1008E64C`, `0x10082310`, `0x100829F8`, `0x1008BAE8`, and
  the literals `c:\pxd32pa.tmp` … `c:\pxd32pz.tmp` sit at `0x1004B384`–`0x1004B3C4`. **[certain]**
* `ASetPfad(prefix)` (`0x1001773E`) copies the prefix to `0x100835E0` and re-runs the temp setup at
  `0x10014233`; `AGetString(dest, sel)` (`0x10013785`) hands the caller one of the temp names, including
  the `"%spxd32p%c.tmp"` form. **[certain]**

---

## 9. The text-command protocol: `REffekt`, `RDrum`, `RpDrum`

These three exports are a **property protocol**, not signal-processing calls. Each compares the string
argument with a table of names using `lstrcmpiA` and writes one global per command. The command names
are contiguous from `0x1004B620` to `0x1004B9C8`:

| Group | Commands (address) |
|---|---|
| Transport / status | `GetPlayStatus` `0x1004B620`, `GetPlayFertig` `0x1004B630`, `PlayStart` `0x1004B64C`, `PlaySimmulation` `0x1004B658`, `GetPlayTime` `0x1004B668`, `SetPlayTime` `0x1004B674`, `GetPlayBuffer` `0x1004B680`, `GetPlayBufferBreite` `0x1004B690`, `GetVersatz` `0x1004B7F8` |
| Sequencer | `LoopMode` `0x1004B774`, `PlayMatrix` `0x1004B780`, `MatrixMode` `0x1004B78C`, `MetroStart` `0x1004B798`, `MetroStop` `0x1004B7A4`, `StretchMode` `0x1004B7B0`, `KonvertMode` `0x1004B7BC`, `StretchRegler` `0x1004B7E0`, `AnfangsTakt` `0x1004B81C`, `StartTakt` `0x1004B834`, `GetTakt` `0x1004B900`, `GetAnzeige` `0x1004B840` |
| Record | `RecordAn` `0x1004B7C8`, `RecordAus` `0x1004B7D4`, `RecMode` `0x1004B7F0` |
| Filter | `CutOff` `0x1004B6AC`, `Resonance` `0x1004B6B4`, `OverDrive` `0x1004B6C0`, `FilterVolume` `0x1004B6CC`, `FilterLed` `0x1004B740`, `DCutOff` `0x1004B87C`, `DResonance` `0x1004B884`, `DFilterLed` `0x1004B8CC` |
| Echo | `EchoTime` `0x1004B6DC`, `FeedBack` `0x1004B6E8`, `EchoVolume` `0x1004B6F4`, `EchoLed` `0x1004B74C`, `DEchoTime` `0x1004B890`, `DFeedback` `0x1004B89C`, `DEchoLed` `0x1004B8D8` |
| Distortion / robot | `RobotColor` `0x1004B700`, `RobotVolume` `0x1004B70C`, `Distortion1` `0x1004B718`, `Distortion2` `0x1004B724`, `DistortionLed` `0x1004B754`, `RoboLed` `0x1004B76C`, `DDistortion` `0x1004B8A8`, `DDistortionLed` `0x1004B8E4` |
| Levels | `SampleVolume` `0x1004B730`, `VolLed` `0x1004B764`, `DrumVolume` `0x1004B85C`, `LautSprecher` `0x1004B84C`, `DVolume` `0x1004B8BC`, `DrumPan` `0x1004B964` |
| Drum machine | `DrumMute` `0x1004B640`, `Taste` `0x1004B6A4`, `ADrum` `0x1004B804`, `LDrum` `0x1004B80C`, `Loop` `0x1004B814`, `LoopLinks` `0x1004B828`, `DrumPitch` `0x1004B870`, `Reverse` `0x1004B868`, `DSwing` `0x1004B8B4`, `DrumDoppel` `0x1004B908`, `DrumPlayStart` `0x1004B914`, `DrumPreload` `0x1004B924`, `DrumPlayStop` `0x1004B930`, `Metronom` `0x1004B940` |

`REffekt(cmd, value)` handles the effect/transport group and writes the effect globals
`0x10082B6C`–`0x10082BA4`, `0x10090758`–`0x10090778`; `RDrum(a, b, cmd)` handles the drum group and
writes `0x1009071C`–`0x1009076C`, `0x1008E824`–`0x1008E830`, plus the `0x3B1`-entry (945) per-second
peak table at `0x1008F774`; `RpDrum(a, b, c)` is an 11-instruction re-order and tail call into `RDrum`.
**[certain]** for the string table, the dispatcher shape and the tail call; the per-command global
assignments are read from the `lstrcmpiA` branches in `REffekt` (`0x1001E…`) and `RDrum` (`0x1001F…`).

`Stretcher(a, b, ratio, d)` (`0x100223A5`) is the one export with a **float** argument: it compares the
ratio against the double `0.1` at `0x10043418` and calls one of two object methods on `0x1008B8F0`
(`0x1000506E` above the threshold, `0x10005444` below). Reading: time-stretch/quality selection — a
ratio above 0.1 uses the full stretcher. **[likely]** for the meaning, **[certain]** for the compare.

---

## 10. Sample browser

A sorted index over a name table, same design as the 1998 build but with different limits:

* `ASortInit()` — `word [0x1008E41C] = 0`.
* `ASortIn(name)` — caps at **`0x1900` (6400)** entries; writes index `n` into
  `word [0x10090860 + n*2]` and `lstrcpyA`s the name into record `n` of the table whose base pointer is
  `0x100836F0`, **stride `0x80` (128 bytes)**. An empty or NULL name still consumes an index.
  **[certain]** (`shl eax, 7` at `0x10010B4A`).
* `ASortStart()` / `ASortStart2()` — call the CRT `qsort` at `0x100323D4` over the word array with
  comparators `0x10010B74` / `0x10010BB6`. **[certain]**
* `ASortOut()` — pre-increments `0x1008E41C` and returns `word [0x1009085E + n*2]`; `0x1009085E` is
  `0x10090860 − 2`, so the pre-increment makes the first call return element 0. **[certain]**

---

## 11. Registry and installation glue

Two exports talk to the registry, both with `ADVAPI32`:

* `ARegUnIn(uninstall, display)` — `0x10022460`: `RegCreateKeyExA(HKLM,
  "Software\Microsoft\Windows\CurrentVersion\Uninstall\Dance eJay3", ...)` at `0x1004BAA4`, then
  `RegSetValueExA(key, "DisplayName", REG_SZ, ..., display)` (`0x1004BAE4`) and
  `RegSetValueExA(key, "UninstallString", REG_SZ, ..., uninstall)` (`0x1004BAF0`), `RegCloseKey`.
  Returns 1. **[certain]**
* `ARegDelete()` — `0x100224FB`: `RegDeleteKeyA(HKLM, "Software\...\Uninstall\Dance eJay3")`
  (`0x1004BB00`), returns 1. **[certain]**

So the DLL itself writes the Windows "Add/Remove Programs" entry for the product — the host passes the
display name and the uninstall command line. **[certain]** for the mechanics, **[likely]** for the
direction of the two arguments (the order was read from which `RegSetValueExA` consumes which frame
slot).

Debug logging is separate: `Debimem(tag)` (`0x100217DD`) appends
`"%s ML:%ld TP:%ld AP:%ld TPa:%ld APa:%ld TV:%ld AV:%ld"` (`0x1004B9F8`, pushed at `0x1002183A`) to
**`c:\memo.txt`** (`0x1004B9EC`, pushed at `0x1002180A`) using `GlobalMemoryStatus` values. There is no
second logger: the four literals that suggest one — `c:\debug.txt` (`0x1004BA44`, `0x1004BA68`),
`"%s : %ld (%ld)"` (`0x1004BA54`) and `"%s : %ld"` (`0x1004BA78`, `0x1004BA84`) — have **no reference
anywhere in the file**, and the same is true of `c:\w.wav` (`0x1004B430`) and `"Test-Meldung"`
(`0x1004BA90`). An earlier note claimed `0x1004BA44`/`0x1004BA68` "point a second logger"; that was
an inference from the string contents, not from a code reference — see `PXD32D5-D4-worklog.md` §2.
**[certain]** (whole-file dword scan for each VA).

---

## 12. What the DLL is *not*

* **Not a `dsound.dll` client by import.** The DirectSound device is created with
  `CoCreateInstance` (`0x1001AD39`); the only COM imports are `CoInitialize` and `CoCreateInstance`
  from `ole32.dll`. **[certain]**
* **No `waveInGetDevCaps`** — that import does not exist, so the record path cannot query input-device
  capabilities. The six `mixer*` imports it would complement *are* present and used (§2.6), and
  `ASelectMic`'s microphone selector is dead code (§7). **[certain]**
* **No `acmStream*`, no decoder imports.** Compressed input is handled by `LZ32` (`SZDD`) only.
* **No networking, no installer, no resource section.** The only registry use is the uninstall key.
* **The 1998 features that are gone from the exports:** the file writer (`RWaveRec`/`RWaveSave` are
  stubs here), the popup window and menu (`RMenu`), the Visual Basic callback (`AVbInfoCall`), and the
  GDI `Fade` routine. The RIFF comment *format* did not disappear with them: two unexported functions
  still compare a freshly read 0x18-byte block against `LIST`, `INFO`, `ICMT` and the 4-byte tag
  `eJay`, requiring a length of at least `0x15` (`0x10005D62`–`0x10005D8A` and
  `0x1000814C`–`0x10008174`), otherwise they fall back to a table of `0x3E8` words. See
  `PXD32D5-D4-strings-imports.md` §6. **[certain]** for the comparisons, **[likely]** that this is the
  saved-project comment reader living on inside the converter object.

---

## 13. Export → responsibility

Grouped view; per-function argument details stay in `PXD32D5-D4.md`.

| Layer | Exports |
|---|---|
| Lifecycle / transport | `ADevice`, `AInit`, `AStart`, `AStop`, `AEnd`, `AExit`, `ATimer`, `AFenster`, `AGetTime`, `AMemory`, `ANummer`, `Extra`, `ExtraAus`, `ASetPfad` |
| Convenience wrapper | `PInit`, `PStart`, `PStop`, `PPlay`, `PClose` |
| DirectSound layer | `DStart`, `DCloseAll`, `DPlayFile`, `DPlayFileCheck`, `DPlayFileClose`, `DPlayUpdate`, `DGetZeit`, `ASetFader`, `ASetPitch`, `RWavePause1`, `RWavePause2` |
| Scheduling / mixing | `APlay`, `ABilder`, `ABildpos`, `AMitte`, `ATyp`, `AWaveDauer`, `BWaveDauer`, `ALautSet`, `ALautGet` |
| Sample storage | `ALoad`, `AClose`, `ACloseAll`, `AWelle`, `AWellePos`, `RWaveLaden`, `RWavToTemp`, `ARecPegel`-adjacent buffers |
| Recording | `ARecInit`, `ARecStart`, `ARecStop`, `ARecPlay`, `ARecInput`, `ARecPegel`, `ARecTimer`, `ARecTest`, `ARecDuplex`, `AGetInput`, `ASelectMic` |
| Conversion | `W2P`, `RWavToTemp`, `RWaveLaden`, `Stretcher` |
| Property protocol | `REffekt`, `RDrum`, `RpDrum` |
| Wave/file misc | `RWavePlay`, `RWaveStop`, `RWaveParam`, `RGetParam`, `RWaveGetTime`, `RWaveSave`, `RWaveFilter`, `RWaveTakt`, `RWaveGetInfo`, `RWaveSetInfo`, `RWaveRec`, `RWaveTransfer`, `RGetName`, `AExport`, `AGetString` |
| Sample browser | `ASortInit`, `ASortIn`, `ASortOut`, `ASortStart`, `ASortStart2` |
| Host integration | `AGetFree`, `AGetFull`, `AMemory`, `ARegUnIn`, `ARegDelete`, `Debimem`, `ASetCur`, `ATest`, `APos`, `RMenu`, `RRecoSave`, `RTimer`, `Fade` |

---

## 14. Confidence summary

| Claim | Confidence | Basis |
|---|---|---|
| Dance eJay3 engine, 2001 VC6 build | high | uninstall key, collection string, link stamp |
| Output is DirectSound created through `CoCreateInstance` | certain | CLSID/IID at `0x100434B0`/`0x100434C0`, ole32 imports, `DStart` |
| 44.1 kHz / 16-bit / stereo everywhere | certain | `ADevice`, `ARecTest`, `ALautSet`, `DStart` rate check |
| 44.1 kHz primary-buffer check and re-format | certain | `0x1001AF52` compare against `0xAC44` |
| 32 voices default, 48 for product type `0x14`; `0x84` stride; 30-event rings of `0x108` | certain (sizes) / likely (count rule) | `.data` bytes at `0x1004B2F8`, init helper |
| `APlay` argument roles | high | direct offset stores |
| Frame-aligned scheduling on start/duration/level | certain | `&~3` masks |
| 28 reproducible DirectSound voices (slots 1..0x1C) | certain | loop bounds in `ASetPitch`, `DPlayUpdate` |
| Bounded transport wait: ~176 ms stop, ~416 ms start | certain | `0x100144C9` counter and `Sleep(8)` |
| Sample cache budget `(free_MB − 18) MB` | certain | `0x10017632` shift and compare |
| 200 sample slots of `0x528` bytes with DIB thumbnails | certain (array/loop) / high (field roles) | `ALoad`, `AClose`, `ACloseAll` |
| `SZDD` decompression through `LZ32` | certain | magic `0x44445A53`, three thunks |
| `waveIn` recording, 40 × `0x1800` buffers, no callback | certain | constants, `waveInPrepareHeader` loop |
| 25-entry semitone rate table 0.5..2.0 | likely | literal values at `0x100668F0` |
| `REffekt`/`RDrum` = string-command property protocol | certain (strings + `lstrcmpiA`) / likely (per-command globals) | command table `0x1004B620`–`0x1004B9C8` |
| Uninstall entry written by `ARegUnIn` | certain | registry calls and key literal |
| Numeric mapping of the DirectSound vtable offsets to method names | likely, and internally inconsistent | the `DStart` labels fit one slotting, `Play`/`Stop`/`SetFormat` fit one slot lower — see `PXD32D5-D4-layout.md` §5 and the worklog open question |
| Export ordinals are alphabetical, not address order | certain | export directory: EAT[0] = `ABilder` (ordinal 1), EAT[95] = `W2P` (ordinal 96) |
| The worker thread is a non-blocking poll: `WaitForSingleObject(event, 0)` + exit flag `0x100826C0` | certain | `0x10017AD3`–`0x10017AF3`, event created at `0x10017972` |
| One `0xA0` record array at `0x10093EB0`; the mapping fields are the same records seen through the folded base `0x10093F38` | certain (addresses) / likely (single array) | `ASetPitch`/`RWavePause1/2` vs `DPlayFileClose` displacements, `0x88 = 0xA0 - 0x18` |
| The `mixer*` API is in use: `mixerOpen` at start, three helpers behind `ALautSet`/`ALautGet`/`ARecInput` | certain | §2.6 |
| A fourth mixer helper at `0x10018715` has no reference anywhere in the image | certain (no reference) | `E8`/`E9` scan, no absolute or RVA pointer to it |
| The `LIST`/`INFO`/`ICMT`/`eJay` comment check survives in two unexported functions | certain (comparisons) / likely (meaning) | `0x10005D62`–`0x10005D8A`, `0x1000814C`–`0x10008174` |
| Which host `.exe` shipped this copy | unknown | not in the image |
