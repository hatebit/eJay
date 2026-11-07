# PXD32D4.DLL - eJay 2 audio engine: consolidated notes

Everything known about `pxd32d4.dll`, recovered by static analysis only: PE
parsing plus Capstone disassembly through
[`../tools/pxd_dis.py`](../tools/pxd_dis.py) (`PXD_DLL` selects the file).
The binary was never loaded, executed or patched. Addresses are absolute image
VAs (image base `0x10000000`); a claim without a tag is either a direct quote
of the instruction stream or is marked right there.

**Subject:** `disks/Dance_2/D_ejay2/ejay/PXD32D4.DLL`, 161,792 bytes,
MD5 `026ddd4cbbb7eb24d9a795d22b4aac77`, PE32 / i386, image base `0x10000000`,
entry point `0x00013230`, subsystem 2 (GUI), link timestamp 0, 4 sections.

| section | VA | virtual size | raw offset | raw size |
|---|---|---|---|---|
| `.text` | `0x10001000` | 1,181,440 (`0x120700`) | `0x400` | 120,832 |
| `.rdata` | `0x1001F000` | 10,678 (`0x2B36`) | `0x1DC00` | 10,752 |
| `.data` | `0x10022000` | 142,304 (`0x22BE0`) | `0x20600` | 16,896 |
| `.reloc` | `0x10045000` | 12,242 (`0x2FD2`) | `0x24800` | 12,288 |

Most of `.data` is BSS (only 16,896 of its 142,304 virtual bytes are backed by
the file), so the engine's counters, buffers and flags start at zero and are
initialised by `AInit` and friends. **[certain]**

Related material:

| file | content |
|---|---|
| `disks/Dance_2/D_ejay2/ejay/PXD32D4.DLL` | the analysed binary (ignored by git) |
| [`../tools/pxd_dis.py`](../tools/pxd_dis.py) | PE reader + disassembler; set `PXD_DLL` |
| [`../src/pxd32d4.py`](../src/pxd32d4.py) | Python port of the documented subset: engine facade, `APlay`, `AWaveDauer`, `RWavToTemp`, both decoders |
| [`PXD32R4.md`](PXD32R4.md) | Techno eJay engine of the same family (voice record) |
| [`../../docs/formats/PXD_FORMAT.md`](../../docs/formats/PXD_FORMAT.md) | the `tPxd` container |
| [`../../docs/formats/MIX_FORMAT_RAVE.md`](../../docs/formats/MIX_FORMAT_RAVE.md) | how a host arranges voices |

A partial Python port lives in
[`../src/pxd32d4.py`](../src/pxd32d4.py): the engine facade, the `APlay`
queue, `AWaveDauer`, the `RWavToTemp` conversion path (`a3 <= 0`) and the
`tP`/RIFF decoders, with tests in
[`../src/test_pxd32d4.py`](../src/test_pxd32d4.py). The numbered-sound path
(`a3 > 0`), DirectSound playback, recording and the sequencer are not
ported. Nothing in this note was derived from the later-build modules under
`../src/`; they are only a cross-check of the shared API family.

---

## 1. What the DLL is

A 32-bit Win32 sound engine for a 1998 eJay product, and the ancestor of the
engine used by the later eJay titles:

* an **audio engine** with a DirectSound mixer created through
  `CoCreateInstance` (there is no `dsound.dll` import), a `waveOut` device
  probe, a watchdog/player thread, critical sections and 75,600-sample
  mixing buffers;
* a **module/sample player**: a tracker-style replay core with per-voice
  state (`0x100429C8`, stride `0x84`), note/period tables, envelopes,
  filters, echo and a "stretcher";
* a **wave subsystem** that converts an input file or a slice of an open
  stream into a temp WAV (``%spxd32d%c.tmp``), caches it and maps it for
  playback, plus the proprietary `tP` ADPCM container;
* recording (`ARec*`, `waveIn*`) and UI helpers (`ABilder`, `AFenster`,
  `ASort*`, cursor).

Identity: the only product string is
`Copyright Bernhard Throll, Germany 1998` at `0x1002209B` **[certain]**. There
is no uninstall/registry code and no host-side conversion log text, so the
DLL is used from a host that owns those facilities.

## 2. Exported API

87 named exports, ordinal base 1, export directory RVA `0x21300`, internal
name `pxd32d4.dll` (`0x1002168E`). **[certain]**

| group | exports |
|---|---|
| engine front end | `ADevice` `AInit` `AEnd` `AStart` `AStop` `AMemory` `AExit` `ATimer` `ADSoff` `AClose` `ACloseAll` `Fade` |
| wave file layer | `AWaveDauer` `BWaveDauer` `RWaveLaden` `RWavePlay` `RWaveStop` `RWavePause1` `RWavePause2` `RWaveParam` `RGetParam` `RWaveGetTime` `RWaveGetInfo` `RWaveSetInfo` `RWaveTakt` `RWaveFilter` `RWaveSave` `RWaveRec` `RWaveTransfer` `RWavToTemp` `RGetName` |
| long-play/disk player | `DStart` `DCloseAll` `DGetZeit` `DPlayFile` `DPlayFileCheck` `DPlayFileClose` `DPlayUpdate` |
| recording | `ARecInit` `ARecStart` `ARecStop` `ARecPlay` `ARecInput` `ARecPegel` `ARecDuplex` `ARecTimer` `ARecTest` `ASelectMic` |
| export/convert | `AExport` `APos` `AGetTime` `AGetFree` `AGetFull` |
| mixer / voices | `ALautGet` `ALautSet` `ASetFader` `ASetPitch` `ASetPfad` `AMitte` `REffekt` `RDrum` `RpDrum` |
| UI / misc | `ABilder` `ABildpos` `AFenster` `ANummer` `ATyp` `Extra` `ExtraAus` `ASetCur` `ASortInit` `ASortIn` `ASortOut` `ASortStart` `ASortStart2` `RMenu` `RRecoSave` `RTimer` `Debimem` `ATest` `AGetInput` `AGetString` `ALoad` `AVbInfoCall` `AWelle` `AWellePos` |

There is **no `P*` front-end family**: a host calls `ADevice`, `AInit`,
`AStart`, `APlay` and the `R*` functions directly. There is also no `W2P`
(WAV to PXD), no `Stretcher` export (the stretch code is internal) and no
registry export. The full address table is in Appendix A.

### Stubs and thin wrappers

| export | address | body |
|---|---|---|
| `ATimer` | `0x100084C7` | `return 1` |
| `RWaveTakt` | `0x10008F87` | `return 1` |
| `RWavePlay` | `0x10008DF1` | `return status_word` (`0x10043480`) |
| `RWaveFilter` | `0x10008F7B` | `return 1` |
| `RWaveSave` | `0x10008F6E` | `return 1` |
| `AVbInfoCall` | `0x10008F9B` | `return 1` |
| `RWaveGetInfo` / `RWaveSetInfo` / `RWaveRec` | `0x1000963D` / `0x10009646` / `0x10009652` | `return 1` |
| `AMitte` | `0x100025F0` | `voice[a1].pan_4A = (u16)a2; return 1` |

All bodies above are read from the instruction stream. **[certain]**

## 3. Imports

| DLL | count | what it tells us |
|---|---|---|
| `WINMM.dll` | 23 | `waveOutGetNumDevs/GetDevCapsA/Open/Close/Reset/GetID/SetVolume`, `mixerOpen/Close`, `mixerGetLineInfoA/GetLineControlsA/GetControlDetailsA/SetControlDetails`, the whole `waveIn*` recording family, `timeGetTime` |
| `USER32.dll` | 6 | `DefWindowProcA` `LoadCursorA` `SetCursor` `PostQuitMessage` `wsprintfA` `InvalidateRect` |
| `GDI32.dll` | 8 | `CreateCompatibleDC` `CreateDIBSection` `CreatePatternBrush` `CreateBitmap` `SelectObject` `BitBlt` `DeleteObject` `DeleteDC` |
| `ole32.dll` | 2 | `CoInitialize`, `CoCreateInstance` (DirectSound) |
| `LZ32.dll` | 3 | `LZOpenFileA` `LZRead` `LZClose` - some inputs are LZ-compressed |
| `KERNEL32.dll` | 89 | file mapping, temp paths, threads/sections, `OpenFile`, `GetDiskFreeSpaceA`, `GetDriveTypeA`, `GlobalAlloc`, CRT support |

Two absences matter: **no `waveOutWrite`** (output is DirectSound, MME is only
used to enumerate devices and set the speaker volume) and **no `ADVAPI32.dll`**
(there is no registry code in this build). **[certain]** for the import table;
**[likely]** for the DirectSound reading, which the trace strings in section 4
confirm.

## 4. Strings

| string | address | use |
|---|---|---|
| `Copyright Bernhard Throll, Germany 1998` | `0x1002209B` | build identity |
| `%spxd32d%c.tmp` | `0x10022194`, `0x100226AC` | numbered-sound temp file |
| `%spxd32da.tmp` .. `%spxd32dz.tmp` | `0x10022114` .. `0x10022144` | fixed temp names |
| `c:\pxd32da.tmp` .. `c:\pxd32dz.tmp` | `0x10022154` .. `0x10022184` | developer test paths |
| `pxd01.tmp`, `pxd02.tmp` | `0x100221B8`, `0x100221C4` | earlier temp names, still referenced |
| `PXD_Event` | `0x100221E0` | event name, pushed at `0x10008BC4` |
| `Fehler 20` | `0x100226BC` | error text pushed at `0x10010F8D` |
| `c:\memo.txt` | `0x100226CC` | hard-coded trace file, pushed at `0x10011E50` |
| `%s ML:%ld TP:%ld AP:%ld TPa:%ld APa:%ld TV:%ld AV:%ld` | `0x100226D8` | named-value trace |
| `c:\w.wav` | `0x100221EC` | developer test path |
| `CoCreate`, `DS-C-Level`, `Create Buffer0`, `GetFormat0`, `SetFormat0`, `Create Buffer2`, `Stop2`, `Release`, `LOCK`/`UNLOCK`, `Pitch`, `Pan1`, `Fader1`, `GetPos`, `Set C Pos`, `Set D Pos`, `DTime`, `HMXB` | `0x10022220` .. `0x100223A8` | DirectSound trace tags; `CoCreate` is pushed at `0x1000BDDB` |
| `AnfangsTakt`, `StartTakt`, `GetTakt`, `LautSprecher`, `LoopMode`, `StretchMode`, `KonvertMode`, `Metronom`, `ADrum`, `LDrum` | `0x1002248C` .. `0x10022638` | original variable names for the debug helper |

`Play`/`Play0`/`Play1` (`0x100221D0`, `0x100221FC`, `0x10022204`) and
`Microphone`/`Micro` (`0x1002220C`, `0x10022218`) are the remaining trace
tags. There are no `tPxD` or `RIFF` literals: both magics are compared as
16-bit immediates (`0x5074` at `0x10006175`, `0x4952` at `0x10006203`).
**[certain]**

## 5. Engine lifecycle and global state

### 5.1 `ADevice` (`0x10003B95`)

`waveOutGetNumDevs()` at `0x10003BA6`, then four `waveOutGetDevCapsA()` passes
(`0x10003C0D`, `0x10003D2B`, `0x10003D9E`, `0x10003E11`) over 52-byte
`WAVEOUTCAPSA` records. The first pass accepts `dwFormats & 0x800`
(16-bit stereo 44.1 kHz) at `0x10003C1F`; the remaining passes cover the
narrower format classes **[likely]**. If none matches, it builds a
`WAVEFORMATEX` for 44,100 Hz / 2 channels / 16 bit (`0xAC44`, `0x2B110`,
align 4, bits 16 at `0x10003C42`) and retries `waveOutOpen` with simpler
formats. It stores the achieved class in `word_1003B158` (0..3) and the device
id in `dword_10022068` (`-1` = mapper). **[certain]**

### 5.2 `AInit` (`0x10002671`)

1. Clears `0x10043394`, `0x10043380`, `0x10043384`, `0x10043388`,
   `0x1004338C`; stores `a1` in `0x1003D8F0`; sets `0x10039F68 = 0`,
   `0x10039F6C = 1`, `0x1003F49C = 0`, `0x1003F4A0 = 0`.
2. Copies `dword_100262CC` to `0x1003A044`.
3. When `word_1003B158 != 0`, sets status bit `0x20` in `word_10043480`
   (`0x100026EE`).
4. Clears the voice array: `0x84 * word_10022058` bytes at `0x100429C8`,
   `0x11C` bytes at `0x10039E88`, `0x1B10` bytes at `0x1003DAA8`.
5. Clears **199** dwords at `0x1003A3E8` and sets `0x1003A434 = 0x7FFF`.
6. Continues with the memory check (`AMemory`), the pitch/period table and
   the buffer allocation at `~0x10002C00` (see section 5.3 and section 10).

The engine has **16 voices** here: `word_10022058 = 16` and
`word_1002205C = 16` in `.data`, and every voice loop compares against
`word_10022058`. That is why `RWaveParam` only maps parameters 60..75:

```
RWaveParam(a, v)                                   // 0x10008EAB
  dword_1003A3E8[a] = v
  if 60 <= a < 76:
      x = v / 32767 * 1.33                         // consts 0x1001F270/278
      if x > 1: x = x*x*x                          // 0x1001F280
      voice[a-60].gain_7C = int(x * 65536)         // 0x1001F288, 0x10042A44
```

**[certain]** for the constants and the range, **[likely]** for reading
`1.33`/`65536` off the `.rdata` doubles (they are used as x87 operands at
`0x10008ED0`..`0x10008F0A`).

### 5.3 Buffers (`~0x10002C00`)

The allocator copies a block of globals, then:

* `GlobalAlloc(0x7D0, 0x40)` + `GlobalLock` -> `0x10039BC8` / `0x1003D8C8`,
  zeroed with `memset(0x7D0)`: the shared DPCM delta table (section 10.2);
* for every voice: `GlobalAlloc(0x1FA4, 0x40)`, store at `voice + 4`,
  `GlobalLock` into `voice + 0`, `memset(0x1FA4)` - one 8,100-byte player
  struct per voice;
* `GlobalAlloc(0x1FA4, 0x40)` once more for the standalone struct at
  `0x1003D8FC`.

`0x7D0` is 2,000 bytes and `0x1FA4` is 8,100 bytes, the same structure sizes
the wave decoder uses. **[certain]**

### 5.4 `AEnd` (`0x1000838A`)

Returns `word_10043480` immediately unless `dword_100434A0 == 0x2A90CB20`;
otherwise `AStop()` (`0x100083CE`), `0x10008C5A(0)`, `0x10002E90(0)`,
`0x1000EDEB()`, temp-file disposal `0x10012F10(dword_1003AFE8)`, then the
status word. **[certain]** for the call sequence.

### 5.5 Start/stop protocol

| function | address | body |
|---|---|---|
| `AStop` | `0x1000554F` | clears ten playback counters, sets the command `0x1004342C = 1`, calls `0x1000551C`, returns 1 |
| `AStart(a1)` | `0x10008878` | `0x1003A4B8 = 0; 0x1004342C = 2; 0x1003A3A0 = a1;` calls `0x1000551C`, returns the status word (`ret 4`) |
| `AExit` | `0x10008C3A` | `0x1003A074 = 1; SetEvent(0x10041844); return 1` |
| `AMemory` | `0x10009885` | `GlobalMemoryStatus`; sets `word_10043418 = 1` when total physical memory is between 4,000,000 and 16,000,000 bytes, else 0 |

`0x1000551C` is the wait/dispatch helper shared by start and stop. **[certain]**

### 5.6 Flags and sentinels

| symbol | value / meaning | evidence |
|---|---|---|
| `dword_100434A0` | `0x2A90CB20` (714,132,256) = buffers and thread alive | `AEnd` guard `0x100083AF` |
| `word_10043480` | status/error bits; `0x20` set when the device class is not 0 | `0x100026EE` |
| `dword_1004336C` | 1 = engine started; `RWavToTemp`, `RWaveLaden` and `DStart` return 0/1 immediately while it is clear | `0x10010A0B`, `0x1000B32C`, `0x1000BCE2` |
| `dword_1004342C` | player command: `1` = reset, `2` = start | `AStop` `0x10005570`, `AStart` `0x10008885` |
| `dword_1003A3A0` | requested mix size from `AStart` | `0x10008892` |
| `dword_1003A4B8` | cleared by both start and stop | `0x10005566`, `0x1000887B` |
| `word_10022058` | voice count, 16 | `.data` |
| `dword_10022068` | chosen `waveOut` id, `-1` = mapper | `0x10003BE3` |
| `word_1003B158` | device class 0..3 | `0x10003BAE` |
| `dword_100433C0/C4/C8` | cached `(handle, offset, length)` of the stream slice | `0x10010A60` |
| `dword_10039F68` | 1 while a temp wave is mapped | `0x1000B351` |
| `dword_1003AFE8` | temp path passed to the `AEnd` cleanup | `0x100083FF` |

The status word's other bits are only seen as masks: `0xFE` cleared when the
delta table is built (`0x10002D65`), `0xF7` cleared on a start (`0x100088E2`),
`0xFB` cleared in `AGetString` (`0x100047FD`). Their meanings are
**(unverified)**.

## 6. The play-request queue (`APlay`)

`APlay` (`0x100089D0`) takes 12 arguments and only enqueues; nothing is
decoded or mixed here.

```
voice = 0x100429C8 + 0x84 * a8
slot  = *(voice + 0x64) + 0x108 * (u16)*(voice + 0x6A)
a9 &= ~3; a10 &= ~3; a11 &= ~3
slot[+0x10] = (u16)a1            // id/marker
slot[+0xF0] = a6                 // mode/source pointer
slot[+0xF4] = a4
slot[+0xF8] = a5
slot[+0xFC] = a2
slot[+0x100] = a3
slot[+0x104] = a12
lstrcpyA(slot + 0x12, name)
return 0 if dword_100434A0 != 0x2A90CB20
```

**[certain]** for the mask, the voice arithmetic, the slot stride and the
field writes (`0x10008A03`..`0x10008A90`). The 264-byte slots and the 16-bit
cursor at `+0x6A` are the same layout the later engine family uses; the ring
length itself was not read out of the post-write code, where the cursor is
bumped and wrapped **(unverified)**.

Voice record (stride `0x84`, base `0x100429C8`):

| offset | meaning | evidence |
|---|---|---|
| `+0x00` | player struct pointer (`GlobalLock`ed 8,100 bytes) | `0x10002DDC` |
| `+0x04` | player struct handle | `0x10002DBB` |
| `+0x44` | level, 8.8 (`0x100` = unity) | `RWavToTemp` `0x10010A4F` |
| `+0x4A` | pan word | `AMitte` `0x10002600` |
| `+0x64` | play-slot array pointer | `APlay` `0x10008A24` |
| `+0x6A` | play-slot cursor (word) | `APlay` `0x10008A17` |
| `+0x7C` | gain, 16.16 (`0x10000` = unity) | `RWaveParam`, `RWavToTemp` `0x10010A42` |

## 7. Temp files and `RWavToTemp`

Three 220-byte temp paths are visible:

| symbol | purpose |
|---|---|
| `0x1003B060` | cache for a slice of an already-open stream |
| `0x1003D9C8` | the canonical temp wave produced by `RWaveLaden` |
| `0x10039DA8`, `0x1003D988` | further temp paths reused by the helpers |

Numbered sounds are named `wsprintf("%spxd32d%c.tmp", prefix, a3 + 99)`, so
`a3 = 1` gives `pxd32dd.tmp` (and the older fixed names `pxd01.tmp`,
`pxd02.tmp` still appear in `.data`). **[certain]** for the format string and
the `+99`, **[likely]** for the prefix being `PathName` (the argument order at
`0x10004857` was not resolved).

```c
int __stdcall RWavToTemp(LPCSTR name,   // input file, or "" with a4
                         LPCSTR out,    // output name when a3 <= 0
                         int    a3,     // > 0: render sound #a3
                         HANDLE a4,     // open handle to copy from
                         LONG   a5,     // slice offset
                         LONG   len,    // slice length
                         int    a7);    // de-click tail + block padding
// 0 = success, 1 = failure
```

| step | address | behaviour |
|---|---|---|
| session block size | `0x10010A01` | `[ebp-0x360] = 0x12770` (75,632) |
| guard | `0x10010A0B` | `dword_1004336C == 0` -> return 0 |
| session base | `0x10010A25` | `[ebp-0xE0] = 0x1003D8F8` - the **address** is used as the struct base |
| session init | `0x10010A35` | `+0x54 = 0`, `+0x7C = 0x10000`, `+0x44 = 0x100` |
| stream cache | `0x10010A60` | compare `(a4, a5, len)` with `0x100433C0/C4/C8` |
| slice copy | `0x10010A84`..`0x10010C16` | `CreateFileA(0xC0000000, CREATE_ALWAYS)`, `SetFilePointer`, `SetEndOfFile`, reopen, `CreateFileMappingA(PAGE_READWRITE)`, `MapViewOfFile(FILE_MAP_WRITE)`, one `ReadFile`, unmap, close; short read clears the cache and returns 1 |
| duration | `0x10010C4E` | `AWaveDauer(name)` then `(v - sign) / 2` -> `v14`, mono 16-bit bytes at 44.1 kHz |
| preallocate | `0x10010D8E`..`0x10010E22` | output `CreateFileA(CREATE_ALWAYS)`, size, `SetEndOfFile`, reopen, map |
| classification | `0x10010D55` | `0x1000AFC5(session)` - stream sniffing, the twin of section 10.1 |
| header | `0x10010F92` | `0x10001A64(...)` - RIFF header writer **[likely]** |
| tail | `0x100117C3`..`0x1001185A` | pad to 9,450-byte blocks, at most 16 |

Details verified in this pass:

* the cache triple is `(handle, offset, length)`; a failed or short read
  writes `dword_100433C0 = 0` and returns 1 (`0x10010BE2`, `0x10010BF7`);
* a successful copy sets the three dwords and continues with the temp file as
  the input (`0x10010C01`..`0x10010C1B`);
* the tail division is by `0x24EA` (9,450 = `2 * 4725`) at `0x100117CA`,
  `+1`, clamped to 16 at `0x100117E6`, then zero words are written up to
  `blocks * 0x1275 * 2` (`0x100117FF`);
* the sound path computes `frames << 14`, divides by the pitch step, and
  clamps to `0x12750` (75,600) at `0x10011218`..`0x1001122E`;
* the resampler masks the 14-bit fraction with `0x3FFF` and interpolates two
  `int16` taps (`0x1001128B`), i.e. the same 14-bit linear interpolator shape
  as the later build.

**Not read in this pass:** the exact loop that keeps the left channel when
`a3 <= 0`, and the `sub_10013198`-style header byte layout. The presence of
`a7`-style padding and of a header call is certain, their byte order is
**(unverified)**.

## 8. `AWaveDauer` / `BWaveDauer`

`AWaveDauer` (`0x10003650`) opens the file read-only, `ReadFile`s **270**
(`0x10E`) bytes into a 304-byte frame, requires `got >= 270`, and normalises to
44.1 kHz / 16 bit / stereo bytes:

| branch | rule | address |
|---|---|---|
| `"RI"` | start from `GetFileSize`; use the RIFF size `i32@4` when `size/7 + size > len > size - size/7` | `0x1000371C`..`0x1000376D` |
| | else use the `data` size `i32@40` when `3*v > len`, `v > 1000`, `v/6 < len`, `v < len` | `0x10003770`..`0x100037C0` |
| | `wFormatTag != 1` -> negate | `0x100037DD` |
| | `nChannels == 1` -> `<<1` | `0x10003805` |
| | `wBitsPerSample == 8` -> `<<1` | `0x1000382C` |
| | `nSamplesPerSec == 11025` -> `<<2`, `== 22050` -> `<<1` | `0x10003853`, `0x10003872` |
| `"tP"` | `4 * i32@(u8 at 4 + 6)` | `0x10003884`..`0x100038E5` |
| other | 0 | `0x100038E7` |

**[certain]**. Note that the 270-byte read stays inside the 304-byte frame
here; the tP offset `h[4] + 6` is at most 261, so the 4-byte read is inside the
270 bytes read.

`BWaveDauer` (`0x100038F7`) is the handle variant: it rejects a null/`-1`
handle, seeds the length from `a3` (`[ebp+0x10]`), `SetFilePointer`s to the
offset, reads 270 bytes and applies the same checks (`0x1000399E` onwards).
**[certain]** for the signature and the shared checks.

## 9. `RWaveLaden` and playback

`RWaveLaden` (`0x1000B329`):

1. return 0 while `dword_1004336C == 0` (`0x1000B32C`);
2. `EnterCriticalSection(0x1003A0C8)`, call `0x1000C101(4)`;
3. if `dword_10039F68 == 1`, unmap and close the previous temp wave
   (`0x1000B351`..`0x1000B384`), then `LeaveCriticalSection`;
4. unless `a2 == 0x7B`, call
   `RWavToTemp(name, 0x1003D9C8, 0, a4, a5, a6, 0)` (`0x1000B3B4`); a
   non-zero result returns 1;
5. open `0x1003D9C8`, `GetFileSize`, map it read/write
   (`0x1000B3DB`..`0x1000B43D`);
6. initialise the wave state: `0x10039F78 = 0x10039F7C = 0x12750`,
   `0x10039FA0 = 0`, and zero two 151,200-byte buffers at `0x1003B160` and
   `0x1003B164` (`0x1000B45A`..`0x1000B4BD`).

So the loaded temp wave is mono 16-bit 44.1 kHz and the engine keeps two
75,600-frame working buffers. **[certain]** for the stores and the
`0x24EA0` (151,200) clear size.

`DStart` (`0x1000BCDC`) is DirectSound setup: guard `0x1004339C`, status word,
`0x1000B912`, `0x10008DFD` (event), three `CoCreateInstance` attempts with the
GUIDs at `0x1001F428` / `0x1001F438` and the object at `0x10041C98`
(`0x1000BD3B`, `0x1000BD78`, `0x1000BDB1`), storing the result in
`0x1003A3E4`, with the `CoCreate`, `DS-C-Level`, `Create Buffer0`,
`GetFormat0`, `SetFormat0`, `Create Buffer2` trace tags around it. There is no
`waveOutWrite` anywhere in the import table. **[certain]** for the calls;
**[likely]** for the three-attempt reading of the retry ladder.

## 10. The `tP` container and codec

### 10.1 Stream classification (`0x1000AFC5`)

Called from `RWavToTemp` at `0x10010D55`. The same test appears in the
streamer at `0x10006F6B`:

| magic at 0 | result |
|---|---|
| `tP` (`0x5074`) | `session[10] = 1`; read offset `4 + h[4] + 2 + 4 + 2` (`0x1000617B`..`0x100061F5`) |
| `RI` (`0x4952`), size > 0 | `session[10] = 0`; RIFF size checks with `/9`, scan for `data` (`0x1000621A`..`0x10006233`) |
| otherwise | unknown stream |

**[certain]** for the two magics, the `tP` container offsets and the WAV
field map; see sections 10.4 and 10.5.

### 10.2 Shared delta ladder (`0x10003252`)

`GlobalAlloc(0x7D0)` + `GlobalLock`, `memset(0x7D0)` (`0x10002CD9`..
`0x10002D62`), then the 256-entry `int16` DPCM step ladder, built by the loop
at `0x10003252`..`0x100033A8`; it is symmetric around index 128 = 0 and peaks
at +/-25,266 (12,633 before the final doubling). **[certain]**

Both loop values are x87 doubles held in locals:

| step | rule | address |
|---|---|---|
| locals | `v = 2.2`, `step = 1.0565` | `0x10003252`..`0x10003267` |
| index 128 | 0 | `0x10003274` |
| `j = 1..5` | `t[128+j] = t[127+j] + 1` | `0x100032A0`..`0x100032C6` |
| `j = 6..127` | `t[128+j] = t[127+j] + (int)(v - 0.52)` | `0x100032D0`..`0x100032FF` |
| conversion | `fistp` with round-to-zero (`0x10012A00`) | `0x100032EB` |
| update | `v *= step`, `step -= 0.00022` | `0x10003307`..`0x10003319` |
| mirror | `t[128-k] = -t[128+k]`, `k = 1..128` | `0x10003321`..`0x10003369` |
| double | `t[i] <<= 1` in 16 bits | `0x1000336B`..`0x100033A8` |

The constants are doubles in `.rdata`, read with `fsub qword ptr`: `0.52` at
`0x1001F238` and `0.00022` at `0x1001F240`. The routine clears status bit
`0x01` while building the table (`0x10002D65`), and the ladder feeds every
decoder through the pointers `0x10039BC8` / `0x1003D8C8`.

The result is value-for-value identical to the ported family ladder
`pxd32d5.DELTA_TABLE`, which imports the same builder (`d4_delta_table()`,
also the decoder default) instead of repeating the recurrence.

### 10.3 `tP` bytecode decoder (`0x1000759D`)

The 16-bit-destination decoder is `0x1000759D`, reached from the wrapper
`0x100059AE`; the twin `0x100077E5` (wrapper `0x10005BA9`) is the PCM path of
section 10.4. Neither body is exported; `RWavToTemp` calls the two wrappers
once per block.

Call contract, **[certain]** from `0x100059AE`..`0x10005B1C`:

| voice field | role | address |
|---|---|---|
| `+0x38 % +0x80` | byte offset inside the current block | `0x100059C0`..`0x100059CA` |
| `+0x74` | block base; source = base + offset, plus 2 when `+0x4A == 2` | `0x100059D0`, `0x100059E5` |
| `+0x2C` | read end | `0x10005A05` |
| `+0x30` | byte count of the current block | `0x10005A1A` |
| `+0x80` | block size (source end = base + size) | `0x10005A29` |
| `+0x48` | one-shot "emit the carried sample" flag | `0x10005AA9`, `0x10005ABD` |
| `+0x08` | sample count of this block, seeds the accumulator | `0x10005AF6` |
| `+0x00` | code book base pointer | `0x10005B02` |
| `+0x7C * +0x44 >> 8` | gain word `0x10041838` | `0x10005B0D`..`0x10005B17` |

The body takes its state from the globals `0x1003AE4C` (destination),
`0x1003AE70` (destination base), `0x1003AE84` (padded destination end),
`0x1003AE88` (source end), `0x1003A020` (`int16` accumulator),
`0x1003AE80` (code book), `0x1003D8C8` (delta ladder, section 10.2) and
`0x10039FFC` (carry flag).

Opcode table:

| byte(s) | meaning | address |
|---|---|---|
| `0x00`..`0xF3` | play code book row `opcode`, at `codebook + opcode*16`; walk `int16` steps until `0xFFFF` | `0x1000768B`..`0x100076FC` |
| `0xF4`..`0xFE` | define: next byte = target row, next `opcode-0xF3` bytes = ladder indices; write that many `int16` steps at `row*16`, append `0xFFFF`, then play the row | `0x10007739`..`0x10007776` |
| `0xFF` | one step: next byte indexes the ladder, `acc += ladder[u8]`, emit one sample | `0x100076FE`..`0x10007737` |

Emission is one shared block at `0x100076A7`..`0x100076C3` (copies at
`0x10007606`, `0x100076C0`, `0x100076F1`, `0x1000772E`):

1. `acc += delta` (16-bit wrap, `0x100076A7`);
2. `eax = (int16)acc * gain` (`0x100076B0`); on overflow clamp to `0x8000`
   or `0x7FFF` (`0x10007613`, `0x10007647`);
3. otherwise `eax >>= 16` (`0x100076BD`);
4. `add word ptr [dst], ax`: accumulate into the sample already in the
   buffer, storing `0x8000` or `0x7FFF` on overflow (`0x1000765B`,
   `0x10007669`);
5. `dst += 4`: one 16-bit sample per 4-byte stereo frame; the right word is
   never written by the decoder.

Control flow:

* when `word_10039FFC` is non-zero one sample is emitted before the opcode
  loop (`0x100075EA`..`0x10007606`); the wrapper loads that flag from
  `voice+0x48` and then clears the field (`0x10005AA9`, `0x10005ABD`), so it
  fires once per block;
* `0xFFFF` ends the current delta run, not the block (`0x1000769D`,
  `0x100076CE`, both jumping to the end test at `0x1000777B`);
* the block ends when `dst >= 0x1003AE84` or `src >= 0x1003AE88`
  (`0x1000777B`..`0x1000778B`);
* the accumulator is written back to `word_1003A020` and the destination
  pointer is split into `word_1003A018` / `word_1003A014` (`0x1000779B`..
  `0x100077AD`), matching the later family's state globals.

A row is 16 bytes, i.e. seven steps plus the `0xFFFF` terminator. The define
opcode accepts up to eleven steps, so `0xFB`..`0xFE` (8..11 steps) overrun
the row into the next one; whether real streams use those opcodes is
**(unverified)**. Rows not defined by the stream come from the code book
pointer at `voice+0` (section 5.3); the loader that fills them was not read,
so their initial content is **(unverified)**.

### 10.4 RIFF / PCM path (`0x100077E5`)

The classifier of section 10.1 accepts a stream whose first two bytes are
`RI` (`0x10006202`) and then parses it as a RIFF/WAVE file. Fields used,
**[certain]**:

| WAV offset | field | use | address |
|---|---|---|---|
| `0x04` | RIFF size | `/9` tolerance, raises the session limit `+0x24` | `0x10006221`..`0x10006274` |
| `0x10` | `fmt ` size | clamped to at least 16 | `0x10006277`..`0x10006290` |
| `0x14`..`0x64` | chunk ids, 2-byte scan steps | finds the literal `data` (two word compares) | `0x100062C9`..`0x100063A4` |
| `data+4` | `data` size | `3*v > len`, `v > 1000`, `v - v/9 < len` sanity | `0x10006336`..`0x10006397` |
| `0x18` | sample rate | 11025 -> flag 8, 22050 -> flag 4, else flag 2 | `0x100063C4`..`0x10006433` |
| `0x16` | channels | 2 -> flag `0x20`, byte count not doubled | `0x10006436`..`0x1000645E` |
| `0x22` | bits per sample | 8 -> flag `0x10`, byte count doubled | `0x10006468`..`0x10006494` |
| `data+8` | payload | session read offset `+0x0C`, block size `+0x14` | `0x10006497`..`0x100064C2` |

The rate/format byte is 2 (44.1 kHz), 4 (22.05 kHz) or 8 (11.025 kHz), plus
`0x10` for 8 bit and `0x20` for stereo. The same function also clears
`+0x28` and `+0x48` for this branch (`0x1000621A`, `0x100064BC`..
`0x100064C5`).

Decoder contract (`0x10005BA9`..`0x10005C9C`): `0x1003B038` source,
`0x1003B040` destination, `0x1003B048` destination end, `0x1003B04C` source
end, `0x1003B044` the voice's format word `+0x28`, gain `0x10041838`
(`0x10005C51`..`0x10005C97`). Path selection, **[certain]**:

| test on the format word | path | address |
|---|---|---|
| low byte == 2 (44.1 kHz, 16 bit, mono) | `s >> 1` with the sign bit restored, one sample per word | `0x1000782D`, `0x10007844`..`0x10007888` |
| low byte & `0x10` (8 bit) | `ax = (b + 0x80) << 8`, then the same halving | `0x1000788A`..`0x10007916` |
| otherwise (16 bit) | word read, same halving | `0x10007918`..`0x10007993` |

Each output sample is added into the existing left word, saturated to
`0x8000` / `0x7FFF`, and the destination advances 4 bytes
(`0x10007867`..`0x1000786C`, `0x10007968`..`0x10007970`), exactly like the
`tP` decoder. Upsampling is integer sample-and-hold with no interpolation:
the repeat count is `(format >> 9) & 7` (`0x100078C4`, `0x10007940`) and the
rate map yields 1 / 2 / 4 repetitions for 44.1 / 22.05 / 11.025 kHz. Bit 13
of the same word selects the channel stride: set = stereo, the loop skips
the unused right byte or word (`0x100078C8`..`0x100078CD`,
`0x10007943`..`0x1000794A`); clear = mono.

Because the repeat count is read from bits 9-11, the format word must carry
the format byte in both halves. The RIFF branch above assembles the low byte
only, so the duplication happens elsewhere (the wrapper copies the whole word
at `0x10005C7F`); that producer is **(unverified)**.

### 10.5 The `tPxd` container

Offsets as consumed by the D4 readers. `len` is the byte at `0x04` and counts
itself, so the header is `4 + len + 8` bytes long.

| offset | size | field | D4 evidence |
|---|---|---|---|
| `0x00` | 2 | magic `tP` (`0x5074`) | `0x10006163`..`0x10006179` |
| `0x02` | 2 | not inspected | skipped by the `+4` at `0x1000618B` |
| `0x04` | 1 | `u8` length, counts itself | `0x10006194`..`0x1000619F` |
| `0x05` | `len - 1` | free text / comment | skipped by `h += len` |
| `4+len` | 2 | not inspected | `0x100061A2` |
| `4+len+2` | 4 | frame count | `0x100061B7`, `0x10003884` |
| `4+len+6` | 2 | not inspected | `0x100061AB` |
| `4+len+8` | ... | ADPCM byte code | read offset, `0x100061C3`..`0x100061F5` |

The streamer takes the low `int16` of the frame count and stores twice its
value as the block's sample count (`0x100061B4`..`0x100061BF`); `AWaveDauer`
reads the same field as `int32` and reports `4 * count` bytes at 44.1 kHz /
16 bit / stereo (`0x10003884`..`0x100038E5`). Both therefore assume the count
spans all channels. The payload start `4+len+8` becomes the session read
offset `+0x0C` (`0x100061D8`), and the block is flagged with `+0x48 = 1`
(`0x100061CF`) so that the decoder emits its carried sample first. The field
meanings match the container description in
[`docs/formats/PXD_FORMAT.md`](../../docs/formats/PXD_FORMAT.md); this table
records only what the D4 readers touch.

## 11. Numbers

| constant | value | use |
|---|---|---|
| voice count | **16** | `word_10022058` |
| voice stride | **132** (`0x84`) | `0x100429C8` |
| play-slot stride | **264** (`0x108`) | `APlay` |
| player struct | **8,100** (`0x1FA4`) | one per voice |
| delta table | **2,000** (`0x7D0`) | shared |
| mix buffer | **75,600** (`0x12750`) frames | `RWaveLaden`, resampler clamp |
| mixing block | **4,725** (`0x1275`) frames = 9,450 bytes | tail padding |
| decode block | **75,632** (`0x12770`) bytes | `RWavToTemp` session |
| code book row | **16** bytes | `0x10007690`, decoder |
| delta indices | **256** | `0xFF` operand, `0x10002C80` ladder |
| PCM repeat | **1 / 2 / 4** | rate bits 9-11, `0x100078C4` |
| WAV header read | **270** (`0x10E`) bytes | `AWaveDauer` |
| wave work buffers | **151,200** (`0x24EA0`) bytes each | `RWaveLaden` |
| liveness magic | **714,132,256** (`0x2A90CB20`) | `AEnd`, `APlay` |
| output rate | **44,100** Hz | `ADevice`, `AWaveDauer` |
| nominal mix rate | **32,000** Hz | `RWaveParam(60, 32000)` callers |

## 12. Reconstruction status

| piece | state |
|---|---|
| PE facts, exports, imports, strings | complete, quoted above |
| `ADevice`, `AInit`, `AEnd`, `AStart`, `AStop`, `AExit`, `AMemory`, `AMitte` | bodies read, documented |
| `APlay` queue layout | read; ring wrap unread |
| `AWaveDauer`, `BWaveDauer` | normalisation fully read |
| `RWaveLaden` | read; the temp wave is mapped and two 151,200-byte buffers cleared |
| `RWavToTemp` | guards, cache, preallocation, classification, tail and resampler read; the left-channel loop and header byte layout not read |
| `DStart` | DirectSound setup and trace tags confirmed; buffer feed not read |
| `tP` delta ladder | recurrence read; identical to `pxd32d5.DELTA_TABLE` |
| `tP` decoder `0x1000759D` | wrapper contract, opcode table, emission and control flow read; code book seeding unread |
| RIFF/PCM decoder `0x100077E5` | WAV field map, format word, 8/16 bit, stereo and hold upsampling read |
| `tPxd` container | offset table above, confirmed by both readers |
| `tP` decoder reference | `../src/tp_codec.py`, tests in `../src/test_tp_codec.py` |
| engine facade, `APlay`, `AWaveDauer`, `RWavToTemp`, decoders | `../src/pxd32d4.py`, tests in `../src/test_pxd32d4.py`; the numbered-sound path and playback are not ported |
| effects chain, tracker sequencer | not analysed |
| recording (`ARec*`), UI/GDI helpers, `AExport`, `DPlay*` | not analysed |

The `tP` decoder of section 10.3 has a reference implementation in
`../src/tp_codec.py`, and `../src/pxd32d4.py` ports the documented
engine facade, queue, duration and conversion paths; the rest of the
note is still specification only.

## 13. Open questions

* the ring length of the play queue and the exact wrap of the cursor at
  `voice+0x6A`;
* the meaning of the `word_10043480` bits `0x01`, `0x08`, `0x10`, `0x40`;
* what `dword_1003A4B8` gates (cleared by both start and stop);
* the argument list of `AInit` and the role of `dword_1003D8F0`;
* the byte layout written by `0x10001A64` (the RIFF header writer);
* whether `0x1003D8F8` is really a struct base or the address of a pointer -
  `RWavToTemp` stores the immediate address while other code indexes the same
  region as an array (`0x10041D08`/`0x10041D0C` use a separate `0xA0` stride);
* the `0x7B` (123) special case in `RWaveLaden`;
* the code book initialisation for streams that do not define their entries
  inline;
* where the duplicated format byte in the PCM format word is produced;
* whether `0xFB`..`0xFE` (8..11 define steps) occur, given the 16-byte row;
* why the two 44.1 kHz paths halve every sample instead of using unity
  gain.

## Appendix A - full export table

| # | export | VA |
|---|---|---|
| 1 | `ABilder` | `0x10008AE0` |
| 2 | `ABildpos` | `0x10008B25` |
| 3 | `AClose` | `0x1000AE88` |
| 4 | `ACloseAll` | `0x1000AF35` |
| 5 | `ADSoff` | `0x100098F4` |
| 6 | `ADevice` | `0x10003B95` |
| 7 | `AEnd` | `0x1000838A` |
| 8 | `AExit` | `0x10008C3A` |
| 9 | `AExport` | `0x100053BE` |
| 10 | `AFenster` | `0x1000265D` |
| 11 | `AGetFree` | `0x10001B17` |
| 12 | `AGetFull` | `0x10001C56` |
| 13 | `AGetInput` | `0x1000A211` |
| 14 | `AGetString` | `0x10004814` |
| 15 | `AGetTime` | `0x10008643` |
| 16 | `AInit` | `0x10002671` |
| 17 | `ALautGet` | `0x1000422D` |
| 18 | `ALautSet` | `0x100040B9` |
| 19 | `ALoad` | `0x1000A9E0` |
| 20 | `AMemory` | `0x10009885` |
| 21 | `AMitte` | `0x100025F0` |
| 22 | `ANummer` | `0x10001AD7` |
| 23 | `APlay` | `0x100089D0` |
| 24 | `APos` | `0x1000ECAC` |
| 25 | `ARecDuplex` | `0x100045AF` |
| 26 | `ARecInit` | `0x100045C7` |
| 27 | `ARecInput` | `0x10004952` |
| 28 | `ARecPegel` | `0x10005054` |
| 29 | `ARecPlay` | `0x1000492E` |
| 30 | `ARecStart` | `0x10004885` |
| 31 | `ARecStop` | `0x10004B29` |
| 32 | `ARecTest` | `0x100043F3` |
| 33 | `ARecTimer` | `0x1000506D` |
| 34 | `ASelectMic` | `0x1000A48E` |
| 35 | `ASetCur` | `0x10011DC4` |
| 36 | `ASetFader` | `0x100087DA` |
| 37 | `ASetPfad` | `0x100089B3` |
| 38 | `ASetPitch` | `0x1000CCD4` |
| 39 | `ASortIn` | `0x10001F13` |
| 40 | `ASortInit` | `0x10001F03` |
| 41 | `ASortOut` | `0x10001E99` |
| 42 | `ASortStart2` | `0x10001EE0` |
| 43 | `ASortStart` | `0x10001EBD` |
| 44 | `AStart` | `0x10008878` |
| 45 | `AStop` | `0x1000554F` |
| 46 | `ATest` | `0x1000ECC0` |
| 47 | `ATimer` | `0x100084C7` |
| 48 | `ATyp` | `0x10002610` |
| 49 | `AVbInfoCall` | `0x10008F9B` |
| 50 | `AWaveDauer` | `0x10003650` |
| 51 | `AWelle` | `0x1000A86D` |
| 52 | `AWellePos` | `0x1000A9D2` |
| 53 | `BWaveDauer` | `0x100038F7` |
| 54 | `DCloseAll` | `0x1000C3A3` |
| 55 | `DGetZeit` | `0x1000CFF4` |
| 56 | `DPlayFile` | `0x1000D2A2` |
| 57 | `DPlayFileCheck` | `0x1000D253` |
| 58 | `DPlayFileClose` | `0x1000D080` |
| 59 | `DPlayUpdate` | `0x1000EBF9` |
| 60 | `DStart` | `0x1000BCDC` |
| 61 | `Debimem` | `0x10011E24` |
| 62 | `Extra` | `0x10001A8D` |
| 63 | `ExtraAus` | `0x10001AE1` |
| 64 | `Fade` | `0x10005785` |
| 65 | `RDrum` | `0x1000F806` |
| 66 | `REffekt` | `0x1000F3A5` |
| 67 | `RGetName` | `0x100043E7` |
| 68 | `RGetParam` | `0x10008F2E` |
| 69 | `RMenu` | `0x100096A6` |
| 70 | `RRecoSave` | `0x100096B0` |
| 71 | `RTimer` | `0x10009826` |
| 72 | `RWavToTemp` | `0x100109F8` |
| 73 | `RWaveFilter` | `0x10008F7B` |
| 74 | `RWaveGetInfo` | `0x1000963D` |
| 75 | `RWaveGetTime` | `0x10008F3F` |
| 76 | `RWaveLaden` | `0x1000B329` |
| 77 | `RWaveParam` | `0x10008EAB` |
| 78 | `RWavePause1` | `0x100096D7` |
| 79 | `RWavePause2` | `0x1000977A` |
| 80 | `RWavePlay` | `0x10008DF1` |
| 81 | `RWaveRec` | `0x10009652` |
| 82 | `RWaveSave` | `0x10008F6E` |
| 83 | `RWaveSetInfo` | `0x10009646` |
| 84 | `RWaveStop` | `0x10008E33` |
| 85 | `RWaveTakt` | `0x10008F87` |
| 86 | `RWaveTransfer` | `0x1000A835` |
| 87 | `RpDrum` | `0x10010004` |

## Appendix B - how these addresses were obtained

`tools/pxd_dis.py` reads the PE, maps a VA through the section table and
disassembles with Capstone. The export table, section facts and initialised
globals in this note were read with a short throwaway parser over the same file
(no script was added to the repository):

```sh
cd work
PXD_DLL=../disks/Dance_2/D_ejay2/ejay/PXD32D4.DLL \
  python tools/pxd_dis.py 0x100109F8 40
PXD_DLL=../disks/Dance_2/D_ejay2/ejay/PXD32D4.DLL \
  python tools/pxd_dis.py 0x10008EAB 40
```

Anything quoted above with an address can be re-derived that way. When adding
to this note, keep the tags and quote instruction addresses, not dump line
numbers.
