# Hyper Generator — DSP extraction notes (RAVEEJAY.EXE)

Everything below is from static analysis of
`disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (777 728-byte VB6 PE, image base
`0x400000`). Re-run the checks with [`../tools/disapp.py`](../tools/disapp.py);
nothing is execution — the binary is read-only reference material.

## 1. What the analysis covers

The analysed function range is `0x40F998`–`0x4AC1F0` (248 functions).
Everything below `0x40F998` — including the entry point `0x40D398` and the UI
event handlers (`hyper_Click`, `HypePlay`, `hypercall`) — was **not** covered
and must be recovered by disassembly.

The range does cover one large audio function:

| address | symbol | role |
|---|---|---|
| `0x487140` | `sub_487140` | audio processing / sample-position loop |

`sub_487140` uses `double` x87 FPU variables (`v8`, `v9`, …), `__int16` sample
buffers, and position counters (`dword_4AD0C4`, `dword_4AD0C8`). It drives a
COM-style object through its vtable (`*(_DWORD *)v168`). The two DSP process
methods are called at vtable slots 475/476:

| offset | vtable slot | signature | purpose |
|---|---|---|---|
| `+1900` (`0x76C`) | 475 | `int (__stdcall *)(unsigned int, __int16 *, __int16 *, __int16 *)` | DSP process A |
| `+1904` (`0x770`) | 476 | `int (__stdcall *)(unsigned int, __int16 *, __int16 *, __int16 *)` | DSP process B |

Both take `(this, &buf1, &buf2, &buf3)` where the three `__int16*` buffers are
locals `v148`, `v150`, `v137` filled just before each call:

**Slot 476 (`+1904`):**
* `buf1 = &v148` — set earlier in the loop (position-derived `__int16`)
* `v25 = getter(+136) - dword_4AD0C8`; `v26 = getter(+120)`; if `dword_4AD000`
  then `adj_fdiv_m32(0x40000000)` else `v26 /= 2.0`; `v150 = __vbaFpI2(v25 + v26)`
* `v137 = __vbaFpI2(getter(+128))`
* Call: `(*(*(_DWORD*)v168 + 1904))(v168, &v148, &v150, &v137)`

**Slot 475 (`+1900`):**
* `v148 = __vbaFpI2(getter(+112) - dword_4AD0C4)`  → `&buf1`
* `v32 = getter(+120) - dword_4AD0C8`; `v33 = getter(+136)`; same `/2` or
  `adj_fdiv` branch; `v150 = __vbaFpI2(v32 + v33)` → `&buf2`
* `v137 = __vbaFpI2(getter(+128))` → `&buf3`
* Call: `(*(*(_DWORD*)v168 + 1900))(v168, &v148, &v150, &v137)`

The `getter(+N)` calls are `(*(*(_DWORD*)v168 + 780))(v168)` → object → `(*(*(_DWORD*)obj + N))(obj, &float_out)`, reading float parameters from the object's parameter store at vtable sub-offsets 112, 120, 128, 136, 152 (filter cutoff / resonance / overdrive / wet-dry style values). `dword_4AD0C4` / `dword_4AD0C8` are global position/sample-rate counters; `dword_4AD000` selects between a division-by-two and an `adj_fdiv_m32(0x40000000)` code path.

The actual DSP math — filter cutoff/resonance/overdrive, distortion dirty/noise,
echo time/feedback/depth — lives inside those two vtable methods, **not** in
`sub_487140` itself. `sub_487140` is the controller: sample-position tracking,
gain/pan computation, state-object field writes, and delegation to the object's
process methods.

### Vtable base — runtime, not statically readable

`v168 = a1 & 0xFFFFFFFE` (the low bit of the VB6 object handle is stripped).
The vtable pointer is `*(_DWORD *)v168`, read from the object at runtime. The
object's class vtable is built by the VB6 runtime (msvbvm60) at object creation,
so slots 475/476 target addresses are **not present as static data** in the PE.
The only static reference to `sub_412BDD` (the `__stdcall` thunk that adjusts
`this` by `-0x893` and tail-jumps to `sub_487140`) is at file offset `0x1163c`
slot 0 — a small table, not a 477-slot vtable. Scanning `.text` found only jump
tables (clustered entries) at the two 477+-slot runs, not vtables.

Therefore the DSP method VAs cannot be recovered by pure static analysis; they
must be observed at runtime (e.g. by breaking on the `call [reg+0x76c]` /
`call [reg+0x770]` instructions at `sub_487140:0x488d4b` / `0x48841f` and
reading the vtable), or by finding the object-creation site that installs the
vptr.

The thunk `sub_412BDD` (VA `0x412BDD`) = `sub_487140(a1 - 2195)`; its
`sub dword ptr [esp+4], 0x893` then `jmp 0x487140` confirms the `this`
adjustment. It is referenced only from the table at file offset `0x1163c`.

### Verified references to hyper strings

Found via pointer search (32-bit immediate address in `.text`):

| string | VA | file offset | first xref |
|---|---|---|---|
| `hypercall` | `0x4159C8` | `0x0159C8` | `0x413174` |
| `HypePlay` | `0x4159D4` | `0x0159D4` | `0x413178` |
| `hyper_Click` | `0x416E88` | `0x016288` | `0x41322C` |

All three are inside the work range `0x412BD0`–`0x415138`, but the
functions at `0x413174`/`0x413178`/`0x41322C` are tiny `__cdecl` thunks
(~14 lines each), not DSP code.

### What is NOT DSP

`sub_413AE8`, `sub_413B7C`, `sub_413BBC`, `sub_413C78`, `sub_413CB8` are all
`DllFunctionCall` stubs loading `user32`, `gdi32`, `kernel32` — system DLLs,
not audio. No external audio DLL is imported.

## 2. Extraction path

### Step 1 — build a disassembler for the application

Use [`../tools/disapp.py`](../tools/disapp.py), a PE reader + capstone
disassembler modeled on `../tools/pxd_dis.py` but targeting
`disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (set `RAVE_APP` to override the
path). Usage from the repo root:

```sh
PYTHONPATH=work/tools python -c "
from disapp import dis
dis(0x487140, 60)       # 60 instructions from sub_487140
"
python work/tools/disapp.py find hyper_Click   # locate a string's VA
python work/tools/disapp.py xref 0x416E88      # code refs to a VA
```

The `Pe` class maps VAs to file offsets using the section table
(`.text`: VA `0x401000`→file `0x400`, size `0x0ab584`).

### Step 2 — disassemble sub_487140

Start at VA `0x487140`. This is the audio loop; the COM object's process
methods are called through vtable slots 475/476. The disassembly of `sub_487140`
will show the exact vtable base (`*(_DWORD *)v168` at function entry) and the
call instructions at offsets `+1900`/`+1904`.

### Step 3 — locate the COM object's vtable

Find callers of `sub_487140` to learn what `a1` (the object pointer) is and
where its vtable pointer comes from. Alternatively scan `.data` for vtable
structures whose slots `+1900`/`+1904` point into `.text`.

### Step 4 — disassemble the process methods

Once you have the VAs of vtable slots 475 and 476, disassemble from those
addresses. That is the actual DSP code (filter cutoff/resonance/overdrive,
distortion dirty/noise, echo time/feedback/depth, per the `HKONST` help text).

## 3. What the application's own text confirms

From `disks/Rave_eJay/RAVE/EJAY\HKONST` (screen help) and `disks/Rave_eJay/RAVE/EJAY\Rave` (dialog texts):

* `H_SEITE2` opens the HYPER GENERATOR screen.
* `H_2PLAY` starts the generator; `H_2STOP` stops it; `H_2SAVE` writes a
  one-bar sample into Sound Group HYPER; `H_LIVESAVE` records the session
  (incl. fader moves) into HYPER; `H_RESET` resets all devices.
* Filter = cutoff (`H_FILTER1`) + resonance (`H_FILTER2`) + overdrive
  (`H_FILTER3`) + wet/dry depth (`H_FILTER4`).
* Distortion = dirty (`H_DISTORTION1`) + noise (`H_DISTORTION2`).
* Echo = delay time (`H_ECHO1`) + feedback (`H_ECHO2`) + wet/dry depth
  (`H_ECHO3`).
* `H_116` = 1/16 cut (each note truncated to a 16th).
* `H_LEDFELD` = 16-step sequencer matrix, one bar, columns = 16th divisions.
* Keyboard `H_C`…`H_C2` = C1…C2, 13 keys.
* `HYPRESET` (20 records) and `HYPSOUND` (128 ids, `r1hg%04d.pxd`) are the
  data tables; see `HYPER_GENERATOR.md` §2–§3.

## 4. Known gaps

1. **The process methods' VAs are unknown.** They are reached through the
   object's vtable at `+1900`/`+1904`; the vtable base is built by the VB6
   runtime at object creation and is not present as static data. To recover the
   DSP method addresses, break on the `call [reg + 0x76c]` at
   `sub_487140+0x30B` (`0x488d4b`) and `call [reg + 0x770]` at `sub_487140+0x2DF`
   (`0x48841f`) and read the vtable pointer held in the register at those points.
2. **The vtable object type is unknown.** `sub_487140`'s argument `a1` is a
   COM-style object; its class and vtable layout beyond slots 475/476 are not
   yet identified.
3. **The non-work range `0x401000`–`0x40F998`** (~61 KB) holds the entry
   point and UI event handlers but no DSP. It may contain sample-loading or
   preset-application logic that feeds the DSP parameters.
4. **No external audio DSP library** is imported (`DllFunctionCall` targets are
   `user32`/`gdi32`/`kernel32` only), so the DSP is implemented in-application,
   likely as methods of the COM object `sub_487140` drives.

## 5. Files referenced

| path | content |
|---|---|
| `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` | VB6 PE application (777 728 bytes) |
| `disks/Rave_eJay/RAVE/EJAY/HKONST` | hyper screen help text |
| `disks/Rave_eJay/RAVE/EJAY/KONST` | hyper screen UI layout (coordinates) |
| `disks/Rave_eJay/RAVE/EJAY/Rave` | dialog texts incl. demo limits |
| `disks/Rave_eJay/RAVE/EJAY/HYPSOUND` | 128-sound HYPER bank index |
| `disks/Rave_eJay/RAVE/EJAY/HYPRESET` | 20 factory presets |
| `work/tools/disapp.py` | PE reader + capstone disassembler for the app (created) |
| `work/docs/HYPER_GENERATOR.md` | data-table documentation (bank, presets, screen) |

## 6. Status

The hyper generator's **data format is fully documented** (`HYPER_GENERATOR.md`).
Its **DSP controller is fully mapped**: `sub_487140` (VA `0x487140`) computes
gain/pan from object parameter getters (vtable sub-offsets 112/120/128/136/152
via slot 780) and delegates to two
COM-object process methods at vtable slots 475 (`+1900`, `0x488d4b`) and 476
(`+1904`, `0x48841f`), each taking three `__int16*` sample buffers (`v148`, `v150`,
`v137`). The actual **filter/distortion/echo DSP math is inside those vtable
methods**, whose addresses are VB6-runtime-built and not statically readable —
recovering them requires a runtime breakpoint at the two `call [reg+0x76c/0x770]`
instructions.

## 7. CLI

`src/hyperplay.py` lists and plays the 20 factory presets from
`HYPRESET`. Each preset decodes its base sound (field D) and renders the
16-step sequencer pattern (field B, one slot per 16th of a bar, one bar =
58800 frames at 44.1 kHz) by triggering the base sound at each active step.
Each triggered sound is resampled to its note pitch (note value minus
``--base-note``, plus ``--transpose`` semitones, using linear-interpolation
resampling). Output goes through `sounddevice`'s `RawOutputStream` or a
Windows `waveout` sink:

```
python src/hyperplay.py --list              # list all 20 presets
python src/hyperplay.py 3                   # play preset 3 (Kick Away)
python src/hyperplay.py "Snare Break"       # play by name
python src/hyperplay.py 10 --sink waveout   # Windows waveOut backend
python src/hyperplay.py 3 --transpose 12    # play one octave higher
python src/hyperplay.py 3 --base-note 13    # G1 is the unpitched sample (sounds right)
python src/hyperplay.py 3 --loops 4         # repeat the pattern 4 times
python src/hyperplay.py --list-devices      # list output devices
```

**Note:** all hyper samples are in C-minor, and the default `--base-note 6` treats C1 as the natural pitch, which makes most notes sound off-key. Use `--base-note 13` (G1 = natural pitch) so that B value 13 (G1) plays unshifted and the C-minor scale lines up correctly.
