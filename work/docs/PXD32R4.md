# PXD32R4.DLL - Techno eJay audio engine: gain and pan

**Scope:** what `pxd32r4.dll` does with a voice's gain and pan, because
`docs/formats/MIX_FORMAT_TECHNO.md` only states the conclusion.

**Method:** static analysis only. The binary was never loaded, executed or
patched; every address below comes from Capstone disassembly through
[`../tools/pxd_dis.py`](../tools/pxd_dis.py) (`PXD_DLL` selects the file). The
plain-text result of the last run is quoted in §8.

**Subject:** `disks/Techno_eJay/EJAY/EJAY/PXD32R4.DLL`, 165,376 bytes, PE32 /
i386, image base `0x10000000`, 87 named exports. Sections: `.text`
`0x1000`+`0x1E136`, `.rdata` `0x20000`, `.data` `0x23000`+`0x22D40`,
`.reloc` `0x46000`.

Do not confuse it with `pxd32d5_d4.dll`, the
2001 Dance eJay3 engine (96 exports) that the `PXD32D5-D4-*` document set
analyses. The two share an API vocabulary (`AMitte`, `APlay`, `ASetFader`,
`RWavToTemp`, `RWaveLaden`, `DStart`, `REffekt`) and nothing else that matters
here.

## 1. Which binary plays a Techno mix

| Fact | Evidence | Confidence |
|---|---|---|
| `TECHNO.EXE` is a VB5 application | `MSVBVM50.DLL` ships beside it; file I/O goes through `[0x5253xx]` runtime dispatch | certain |
| `TECHNO.EXE` contains no audio code of its own | no `waveOut`, `dsound`, `DirectSound` or engine strings in it | certain |
| `TECHNO.EXE` names `pxd32r4.dll` | string at file offset `0x19DEC` | certain |
| That DLL is on the disc | `disks/Techno_eJay/EJAY/EJAY/PXD32R4.DLL` | certain |

So the mix is rendered by `PXD32R4.DLL`, not by `TECHNO.EXE` and not by the
Dance engine. Imports: `WINMM` 23 (7 `waveOut*`, 9 `waveIn*`, 6 `mixer*`,
`timeGetTime`), `USER32` 6, `GDI32` 8, `ole32` 2 (`CoInitialize`,
`CoCreateInstance`), `LZ32` 3, `KERNEL32` 89. There is no `dsound.dll`
import, and no `waveOutWrite`: output is DirectSound obtained through
`CoCreateInstance`, MME being used to enumerate devices and to set the
speaker volume. **[certain]** for the import table, **[likely]** for the
DirectSound reading (the same shape as `DStart` in the 2001 build).

## 2. Voice record

| Item | Value | Evidence |
|---|---|---|
| Voice array base | `0x10043B38` | `add eax, 0x10043b38` after `imul eax, eax, 0x84`, e.g. `0x10006AAC` |
| Voice stride | `0x84` bytes | same |
| Pan word | voice `+0x4A` | `AMitte` `0x100025F0` writes `0x10043B82` = base + `0x4A` |
| `AMitte(voice, value)` | plain setter, no classification | `0x100025F0`-`0x10002600` |

**[certain]** for the setter and the offsets. Note the difference from the
2001 build: there `AMitte` (`0x100112B6`) sorts the value into three zones
(117..139 to 0, <15 to 1, >240 to 2) before storing it; `PXD32R4` stores the
caller's word unchanged.

## 3. The gain path is linear

| Fact | Evidence | Confidence |
|---|---|---|
| Per-voice gain `(voice[0x7C] * voice[0x44]) >> 8` | `0x10005B1C`-`0x10005B26` and `0x10005C9C`-`0x10005CA6` | certain |
| Applied per sample as `(sample * gain) >> 16` | `0x10007609`-`0x10007615`, `0x1000786A`-`0x10007876` | certain |
| Result accumulates (`add word ptr [esi], ax`) into the mix buffer | `0x10007615`, `0x10007876` | certain |
| Clipping saturates to `0x8000` / `0x7FFF` | `0x1000766A`, `0x10007883` | certain |
| Unity is `+0x7C = 0x10000` (16.16) and `+0x44 = 0x100` (8.8) | `RWavToTemp` `0x10010ED4`, `0x10010EE1` | certain |
| `+0x44` is loaded from the play-event ring | `0x10006F28`-`0x10006F2E` (event = `voice+0x64 + n*0x108`, field `+0x104`) | certain |

The arithmetic: `0x10000 * 0x100 >> 8 == 0x10000`, then
`sample * 0x10000 >> 16 == sample`. Straight-through gain is exactly 1.0, and
the 8.8 word is the only level control on the path. `0x100` is therefore
"100 %", and a per-placement level can be expressed without ever leaving
integer math.

**There is no constant-power law.** All 19,657 `.text` instructions were
scanned: no `fsqrt`, no square-root table, no pan table. The x87 code that
does exist is `fmul`/`fdiv` on level, fade, effect and conversion paths only.
**[certain]** for the absence, **[likely]** for "the engine cannot compute
one".

## 4. Pan is a channel selector, not a curve

The pan word `voice[0x4A]` is only compared, never scaled:

| Site | Test | Effect |
|---|---|---|
| `0x100059EF` | `== 2` | output word cursor `+= 2`, i.e. one 16-bit slot of the 4-byte stereo frame |
| `0x10005BED` | `== 2` | same, in the 16-bit-source variant |
| `0x10006E41` | `== 3` | different event-ring index handling |
| `0x10006AC8` | `== 0` | centre branch, uses global `0x10043B04` |
| `0x10006B98` | `== 0` | centre branch, computes the play length |
| `0x10007E74` | `== 0` | centre branch in the scheduler scan |

**[certain]** for the comparisons and the `+2`; **[likely]** that the `+2`
slot is the right channel. No branch attenuates the opposite channel, so the
word selects where a voice goes, not how loud it is.

## 5. The mix cores are source-format variants

| Selector | Core | Source |
|---|---|---|
| `[voice+0x28] == 1` | `0x100059BD` | 16-bit source; reads the `tPxD` code book (`[voice]`, entries 16 bytes apart) |
| otherwise | `0x10005BB8` | 8-bit DPCM (`mov ah, byte [edi]; add ah, 0x80`) |

Selected at `0x10006C48`, `0x1000750D` and `0x10011A71`. **[certain]**. They
are not the left/right pair: both write the same 16-bit slot of a 4-byte
frame.

## 6. What this means for a mix

* No gain of `0.5` occurs anywhere on the path, so a centre voice is full
  scale in both channels and a panned voice is full scale in one. The model is
  **unity-centre**. **[likely]**
* The `.MIX` stores no pan at all: a track block is `u8 track, u32 count`
  (`docs/formats/MIX_FORMAT_TECHNO.md` §12). The stereo image is carried by
  *which sample* a track plays:

| Track pair | WAMBAM samples |
|---|---|
| 4 / 5 | `dj 1L` / `dj 1R`, `baller beats 1L` / `baller beats 1R` |
| 13 / 14 | `thunder L` / `thunder R`, `big-drop sugar 4L` / `big-drop sugar 4R` |

  **[certain]** for the file, **[likely]** for the engine reading.
* A hard-panned track is therefore not "6 dB louder than a centred one": it is
  at the reference level while a centred track has to be full scale in *both*
  channels. A player that mixes a centre voice at `0.5/0.5` sits 6 dB low.

## 7. Open questions

1. Whether a centre voice is written to both words of the 4-byte frame in one
   pass, or the voice loop runs once per channel. The mix core advances the
   destination by 4 bytes per sample and writes a single 16-bit word
   (`0x10007615`-`0x1000761A`), so the second write is not in that loop.
   Closing it needs the caller of the two cores
   (`0x10006C45`-`0x10006C68`) traced through its buffer base `[0x1003EAF8]`.
2. Whether the long entry's 10 parameter bytes feed `APlay` argument 12
   (which lands in `voice[0x44]`, the 8.8 level). That would make
   per-placement volume recoverable from the mix. **[guess]** until bytes that
   decode to a sane 0..`0x100` range are found.

## 8. Reproducing

```sh
cd work
export PXD_DLL=../disks/Techno_eJay/EJAY/EJAY/PXD32R4.DLL
export PYTHONPATH=/tmp/caplib        # capstone, installed outside the tree
python tools/pxd_dis.py 0x100059eb 40   # pan read in the 16-bit core
python tools/pxd_dis.py 0x10007609 20   # gain applied to the sample
python tools/pxd_dis.py 0x10010ed4 10   # unity constants in RWavToTemp
```

The last run reported: 87 exports, 19,657 `.text` instructions, six pan-word
reads (`0x100059EB`, `0x10005BE9`, `0x10006AC4`, `0x10006B98`, `0x10006E3D`,
`0x10007E70`), no `fsqrt`.

## 9. Where this is used

* `docs/formats/MIX_FORMAT_TECHNO.md` §13 - the conclusion.
* `OPEN_ISSUES.md` L8 - the reversal, the fix in both players, and the
  before/after measurements.
* `work/src/sdmixplayer2.py` and `player/formats/techno/` - the two players
  that apply it.
