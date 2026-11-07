# The Hyper Generator (Rave eJay)

The HYPER GENERATOR is a **feature of the Rave eJay application**, not of the
audio engine. Two plain-text tables in `disks/Rave_eJay/RAVE/EJAY` (`HYPSOUND`, `HYPRESET`)
describe its sound bank and its 20 factory presets, and the application's own
help strings (`KONST`, `HKONST`, `Rave`) describe its screen. The generator's
sound processing lives in the application binary, which this project only
partially analyses, so the meaning of the preset fields below is recorded as
**verified layout** plus **(unverified)** hypotheses.

Everything in this note is read-only observation of the shipped data files;
no sample or table was executed. See `HYPER_GENERATOR_SEARCH.md` for the
string search that established where the feature does (not) live, and
`HYPER_GENERATOR_DSP.md` for the DSP-code extraction progress in the
application binary `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE`.

## 1. Where the feature lives

| investigation | result |
|---|---|
| `pxd32d5_d4.dll` (this project's engine) | no `hyper`/`generator` string; no hyper feature |
| `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (the application) | identifiers `hyper`, `hyperweg`, `hypersub`, `hyp1`…`hyp8`, `hypmenu`, `hypermenu`, `hypreset`, `hyper_Click`, `hypersub_Click`, `hypercall`, `HypePlay`; the exact phrase "hyper generator" is absent |

So the `.pxd` decoder in `../src/pxd32d5.py` decodes hyper **samples** like any
other `tPxd` stream, but it cannot generate or process them.

### 1.1 What the application binary contains

`disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (777 728-byte VB6 PE, image base
`0x400000`) holds the Hyper Generator's UI form data, event handlers, and an
audio-processing function. Earlier analysis covered functions
`0x40F998`–`0x4AC1F0`; the entry point `0x40D398` and the UI event handlers
(`hyper_Click`, `HypePlay`, `hypercall`) live below that and are recovered by
disassembly with [`../tools/disapp.py`](../tools/disapp.py) (see
`HYPER_GENERATOR_DSP.md`).

Verified findings from static analysis:

* Install mode `word_4AD01A == 1` creates the `HYPER` and `HYPERSAV`
  directories (`sub_49A070`, VA `0x49A070`) — the feature is install-gated.
* Hyper strings and their code references: `hyper_Click` (VA `0x416E88`,
  xref `0x41322C`), `HypePlay` (VA `0x4159D4`, xref `0x413178`),
  `hypercall` (VA `0x4159C8`, xref `0x413174`).
* The audio-processing controller is `sub_487140` (VA `0x487140`). It drives a
  COM-style object through vtable slots 475/476 (offsets `+1900`/`+1904`),
  each taking three `__int16*` sample-buffer pointers — those two methods are
  the actual filter/distortion/echo DSP and have not yet been disassembled.
* No external audio DSP library is imported (`DllFunctionCall` targets are
  `user32`, `gdi32`, `kernel32` only); the DSP is implemented in-application.

## 2. The sound bank: Sound Group HYPER

`disks/Rave_eJay/RAVE/EJAY\HYPSOUND`, 3 948 bytes, pure ASCII, CRLF line endings only, no BOM,
ends with CRLF. Its 272 lines are eight groups; each group is

```
<group name>\r\n
<count>\r\n
<file>\r\n
<label>\r\n
...                                         (repeated <count> times)
```

The label is `NNN <display name>`; `NNN` is the sample's global id, and the
file name is the same id in 4 digits. The 128 ids are contiguous `1..128`,
unique, and every file name matches its id (`r1hg%04d.pxd`); display names are
unique too (longest: `Hard plastic Bottle`, 19 characters).

| group | count | ids | files | first … last label |
|---|---|---|---|---|
| Vibes | 18 | 1–18 | `r1hg0001..0018.pxd` | `001 Peel Off` … `018 Saw` |
| Rave | 16 | 19–34 | `r1hg0019..0034.pxd` | `019 Bull's Eye` … `034 The Latest Rave` |
| Trash | 13 | 35–47 | `r1hg0035..0047.pxd` | `035 Fat Trash` … `047 Deep Thrill` |
| Hardbass | 17 | 48–64 | `r1hg0048..0064.pxd` | `048 Rubber Band` … `064 Hard Board` |
| Softbass | 17 | 65–81 | `r1hg0065..0081.pxd` | `065 Burner` … `081 Jam Bass` |
| Space | 14 | 82–95 | `r1hg0082..0095.pxd` | `082 Space Bowl` … `095 Floating Capsule` |
| Comic | 16 | 96–111 | `r1hg0096..0111.pxd` | `096 Boomerang` … `111 Viking Arrow` |
| Strikes | 17 | 112–128 | `r1hg0112..0128.pxd` | `112 Great Can` … `128 Awful Beat` |

### 2.1 Where the samples are installed

The sounds themselves are not in the normal sample index, but they are
installed in a sibling `HYPER` directory of the `AA`…`BS` sample directories:

* `EJAY\PXD` (1 149 records) has the categories `bass`, `drum`, `effect`,
  `loop`, `sequence`, `special`, `sphere`, `voice` — **no** `hyper` entry.
* `EJAY\MAX` (full install) and `EJAY\MIN` (minimal install) both end with the
  same contiguous 128-line block `hyper\r1hg0001.pxd` … `hyper\r1hg0128.pxd`,
  so the bank is installed as a sibling directory `hyper\` of the `AA`…`BS`
  sample directories.
* That directory is present at `disks/Rave_eJay/RAVE/HYPER` (128 files,
  `R1HG0001.PXD`–`R1HG0128.PXD`), so a mix that references a hyper sample
  resolves through it. (Both `.MIX` fixtures only use bank samples.)

### 2.2 The PXD comment agrees

`data/TEST.PXD` is a copy of hyper sound 1,
`disks/Rave_eJay/RAVE/HYPER/R1HG0001.PXD` — its `tPxD` comment (see
`../../docs/formats/PXD_FORMAT.md` for the header) reads

```
Peel off
001
Rave eJay

hyper
58800
```

i.e. display name, id, producer, an empty line, the **group name `hyper`**, and
`58800`. Line 2 is not a name split: across the 128 hyper files
(`r1hg0001`–`r1hg0128`, absent from the sample index) it is a unique
sequential id `001`–`128`. The header declares 14 700 frames (0.333 s at
44.1 kHz), so a hyper sound is a short one-shot, not a rendered bar.

`58800` is the grid constant of `../../docs/formats/MIX_FORMAT_RAVE.md` §2.1 (one bar). Across
the install image it is the last comment field of 1 277 of the 1 278 `tPxD`
files (the exception is `EJAY\INTRO.PXD`, whose comment ends with
`Rave eJay Intro`). It is **not** the sample's own length — that question is
now closed: the comment is the sample's six-line library record copied from
the sample index `disks/Rave_eJay/RAVE/EJAY\PXD` (name part 1 / id / producer / empty /
category / bar size), and line 6 holds the bank-wide bar quantum
58 800 = 4 beats at 180 BPM = 1.333 s, identical in every file whatever its
own length. Verified by joining every bank comment to its index record
(`../../docs/formats/PXD_FORMAT.md`, "Comment-line semantics" — resolved, [certain]). The
bank also declares frame counts that are exact multiples of 58 800 in 1 144
of the 1 148 index-joined files. Four are off by a little: `R1FX021.PXD`
(+1 frame), `R1VX060.PXD` (−1 837), `R1DF013.PXD` and `R1SF047.PXD` (+1 838
over two bars); these four off-by-a-few samples are exporter rounding in the
*frame count*, not in the comment. So a hyper sound of 14 700 frames says
`58800` for the same reason as every other one-shot — the constant is the bar
size, and 14 700 is exactly a quarter bar.

## 3. The presets: HYPRESET

`disks/Rave_eJay/RAVE/EJAY\HYPRESET`, 1 732 bytes, ASCII, CRLF only, no BOM, ends with CRLF.
40 lines = 20 records of two lines each:

```
<name>\r\n
<A:30><sp><B:32><sp><C:5><sp><D:5>\r\n
```

The data line is always 75 characters and all four fields have the same width
in all 20 records, so field values are exactly the digits shown — a number
cannot be read in two different widths. The letters A–D are this note's names;
the file has no field headers.

| field | width | content | observed values |
|---|---|---|---|
| A | 30 | 15 two-digit numbers, read as 5 triples | see 3.4 |
| B | 32 | 16 two-digit numbers, one per 16th of a bar | 0–18, `0` = rest |
| C | 5 | five binary digits | 9 distinct values, last digit always `1` |
| D | 5 | five-digit number | 33–123, all distinct |

### 3.1 D is the preset's hyper sound

All 20 values of D are live ids from §2, and all 20 are different. The names
line up with the referenced sounds, which is the evidence that D is the sound
selector rather than an unrelated number:

| preset | D | sound (group id name) |
|---|---|---|
| Hard B | 50 | Hardbass `050 Half Pipe` |
| Sub Bass | 68 | Softbass `068 Dull Buzz` |
| Kick Away | 121 | Strikes `121 Boxing Glove` |
| Il Ritmo | 112 | Strikes `112 Great Can` |
| Snare Break | 123 | Strikes `123 Thin Snare` |
| Nose | 33 | Rave `033 Rave Vibration` |

Distribution over the groups: Hardbass 6, Comic 4, Strikes 4, Softbass 3,
Rave 1, Trash 1, Space 1, Vibes 0. The ids are not sorted by name or id, so the
file order is presumably the order the app lists them in **(unverified)**.

### 3.2 B is the 16-step matrix

The screen help describes exactly such a row: *"Sequencer Matrix. Activate or
deactivate single notes with a mouse click. Sequence length is one bar. The
numbers 1 to 16 above the Matrix correspond to the 16th divisions of a
note."* B has 16 slots; 203 of the 320 slots are `0`, and the number of
active steps per preset ranges from 1 (`Rave Hit`) to 12 (`Snare Break`).
Patterns are musically regular — `Kick Away` places `15` on steps 1, 5, 9, 13
plus a pickup on step 15, `Shake It` places `10` on steps 1, 3, 7, 11, 15,
and `Il Ritmo` fills steps 1–5 and then every other step.

**Assumption: each non-zero B value is a note index.** The screen's keyboard
is labelled `C1 Db1 D1 Eb1 E1 F1 Gb1 G1 Ab1 A1 Bb1 B1 C2` — 13 keys covering
one chromatic octave (§4). Values run to `18`, which exceeds the 13-key range,
so either the note range extends beyond the labelled keys, the value is packed
(e.g. octave + pitch), or the meaning is something else entirely. Reading B as
note index remains **(unverified)** but is the interpretation used by
`../src/hyperplay.py`, which treats each non-zero B slot as a trigger of the
preset's base sound at that step.

### 3.3 C is five switches

C is always five `0`/`1` digits, and nine combinations occur (`00001`,
`00011`, `00111`, `01001`, `01011`, `01101`, `01111`, `11101`, `11111`). The
last digit is `1` in all 20 presets, so it is either a reserved/version flag or
a switch that factory presets always enable; the first digit is set in only 3
presets. The screen has exactly five on/off toggles — filter, distortion, echo,
1/16 cut, volume (`H_FILTER`, `H_DISTORTIONLED`, `H_ECHO`, `H_116`,
`H_VOLUMELED`) — which is the strongest available mapping, but the bit order is
not established **(unverified)**.

A cross-check against the A field (a switch off would leave its parameters at
zero) only matches 6 of 20 presets, so C is not simply "A triple is zero".

### 3.4 A is 15 numbers, most plausibly five parameter sets

A is always 15 two-digit numbers. As 5 triples the value sets are not drawn
from one range, which suggests three different quantities:

| slot | observed values | note |
|---|---|---|
| `A[3i]` | 0–10 and 13 | small selector or mode |
| `A[3i+1]` | 0, 1, 10, 11, 20, 21, 30, 40, 41, 50, 51, 60, 70, 80, 81, 90, 91 | only multiples of 10, plus `+1`; reads naturally as tenths, 0.0–9.1 |
| `A[3i+2]` | 0–99 | amount in percent |

The shape (5 × 3) matches the five toggle groups above, but the screen has four
filter faders, two distortion faders and three echo faders, so a one-to-one
device mapping does not fit. Whether A is effect parameters, note data, or
something else is **(unverified)**; the raw values are in Appendix A.

### 3.5 The 20 presets

| # | preset | D | sound | C | steps on |
|---|---|---|---|---|---|
| 1 | Feedback | 55 | Hardbass `055 Little Ball` | 01101 | 2 |
| 2 | Shake It | 119 | Strikes `119 Tambourine` | 11111 | 5 |
| 3 | Kick Away | 121 | Strikes `121 Boxing Glove` | 01011 | 5 |
| 4 | Fly Away | 88 | Space `088 Eliminator` | 01111 | 2 |
| 5 | Rave Hit | 98 | Comic `098 Angry Conductor` | 01111 | 1 |
| 6 | Bird Attack | 99 | Comic `099 Deep Freeze Mice` | 01011 | 7 |
| 7 | Click Bass | 104 | Comic `104 Boy Toy` | 01101 | 6 |
| 8 | Smash | 105 | Comic `105 Wind Up` | 01111 | 3 |
| 9 | Il Ritmo | 112 | Strikes `112 Great Can` | 00001 | 10 |
| 10 | Snare Break | 123 | Strikes `123 Thin Snare` | 01011 | 12 |
| 11 | Water Work | 76 | Softbass `076 Round Egg` | 00111 | 6 |
| 12 | Sub Bass | 68 | Softbass `068 Dull Buzz` | 01001 | 6 |
| 13 | Christmas | 66 | Softbass `066 Lighthouse` | 01111 | 3 |
| 14 | Core | 63 | Hardbass `063 Knock Out` | 00011 | 7 |
| 15 | Breaking | 59 | Hardbass `059 Ear Drum` | 01001 | 10 |
| 16 | Fun Bass | 56 | Hardbass `056 Short Ball` | 01011 | 9 |
| 17 | Peace | 54 | Hardbass `054 Sweep High` | 01101 | 5 |
| 18 | Hard B | 50 | Hardbass `050 Half Pipe` | 11111 | 6 |
| 19 | Hole | 36 | Trash `036 Short & Hard` | 01111 | 6 |
| 20 | Nose | 33 | Rave `033 Rave Vibration` | 11101 | 6 |

## 4. The screen, from the application's own help strings

`EJAY\KONST` lists 90 `H_*` UI element identifiers (name plus layout numbers);
`EJAY\HKONST` gives on-screen help for 88 of them (and for `H_RKOPF`, which
`KONST` lacks), and `EJAY\Rave` holds the dialog texts. The hyper screen's
elements are:

| identifier | role (from `HKONST`) |
|---|---|
| `H_2PLAY`, `H_2STOP`, `H_2SAVE`, `H_LIVESAVE`, `H_RESET`, `H_2BACK`, `H_2HELP`, `H_MINI2`, `H_EXIT2` | transport, save, live-save, reset, back, help, window buttons |
| `H_2NAME`, `H_VORLED`, `H_ZURUECKLED` | sound preset display and previous/next arrows |
| `H_LEDFELD` | 16-step sequencer matrix |
| `H_C`…`H_C2` (13) plus `H_G`, `H_AS`, `H_A`, `H_B`, `H_H` (5) | keyboard, 18 keys total, labelled `G Ab A Bb B C1 Db1 D1 Eb1 E1 F1 Gb1 G1 Ab1 A1 Bb1 B1 C2` |
| `H_G`, `H_AS`, `H_A`, `H_B`, `H_H` | labels `G Ab A Bb B`, i.e. the same notes without an octave |
| `H_FILTER`, `H_FILTER1`…`H_FILTER4` | filter on/off; cutoff, resonance, overdrive, depth |
| `H_DISTORTIONLED`, `H_DISTORTION1`, `H_DISTORTION2` | distortion on/off; dirty, noise |
| `H_ECHO`, `H_ECHO1`…`H_ECHO3` | echo on/off; time, feedback, depth |
| `H_VOLUMELED`, `H_2VOLUME`, `H_MASTERVOLUME`, `H_116` | sample volume, recording volume, soundcard volume, 1/16 cut |

Behaviour the help text states explicitly:

* the matrix is **one bar**, columns are the 16th divisions, the keyboard left
  of it shows the pitch;
* **Save** writes the current sequence as a **one-bar sample** and puts it into
  Sound Group HYPER; `Rave` separately offers "Save Hyper Sample as" with a
  `*.wav` filter, i.e. export of such a sample;
* **Record/Live-save** records a whole session in real time "including each
  fader adjustment", again into Sound Group HYPER;
* **Reset** resets all devices;
* filter section = lowpass cutoff + resonance + overdrive + wet/dry;
  distortion = "dirty" + "noise"; echo = delay time + feedback + wet/dry;
  `1/16 Cut` cuts each note to a 16th;
* `Rave` also carries the demo limits: "The playback of the Hypergenerator
  will be stopped after 60 sec. in this Demo Version" and "This Demo Version
  contains only a part of the sound presets and has no save function". Both
  messages also exist in a binary that is not a demo, so their presence proves
  nothing about this copy.

## 5. Consequences for this project

* Nothing here changes the port: `pxd32d5.py`, `mixplay.py` and `sdmixplay.py`
  never touch the hyper tables. Hyper samples, where they exist, are ordinary
  `tPxd` streams with a `hyper` group tag in the comment, and decode with
  `RWavToTemp` unchanged.
* The generator's own processing is in
  `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE`, not the DLL. The audio controller is
  `sub_487140` (VA `0x487140`); it delegates the actual
  filter/distortion/echo math to its COM object's vtable methods at slots 475/
  476 (offsets `+1900`/`+1904`), which take three `__int16*` sample-buffer
  pointers. Those methods have not yet been disassembled — see
  `HYPER_GENERATOR_DSP.md` for the extraction path. Whether the screen's
  echo uses the engine's `sub_1000E3E0` chain is **(unverified)**.
* The bank's files are present at `disks/Rave_eJay/RAVE/HYPER` (128 files), so
  the preset tables can be listed and their sounds decoded and played.

## 6. Open questions

1. Meaning of the A triples (effect parameters vs. note data) and of the B
   values above the 13 labelled keys.
2. Order and polarity of the five C switches.
3. Does the app read `HYPRESET` in this exact 2-line, fixed-width form, and are
   A/B/C stored as decimal text or converted to bytes at load time?
4. How a live-saved sample enters the HYPER group: the strings say it becomes a
   sample, but nothing in the data files shows whether `HYPSOUND` is rewritten.
5. ~~Whether the trailing `58800` in a `tPxD` comment is a bar-grid marker~~
   — **answered**: it is the bank-wide bar size in frames (58 800), the last
   line of the six-line library record every bank `.pxd` carries; it is not
   the sample's own length (`../../docs/formats/PXD_FORMAT.md`, "Comment-line semantics").
   The four off-by-a-few frame counts are exporter rounding in the frame
   count; the comment value itself never varies.
6. Disassemble `sub_487140`'s COM-object vtable methods at slots 475/476
   (offsets `+1900`/`+1904`) — the actual filter/distortion/echo DSP — using
   `../tools/disapp.py` (`HYPER_GENERATOR_DSP.md` §2).

## Appendix A — the 20 preset data lines, verbatim

Fields are `A B C D` as in §3 (`A` 30 chars, `B` 32, `C` 5, `D` 5).

```
056017081076065012048131043035 13000000000001000000000000000000 01101 00055
040099094009100078091107089012 10001000000010000000100000001000 11111 00119
044072131131131131131131067016 15000000150000001500000015001500 01011 00121
000080044027062059081131076028 12130000000000000000000000000000 01111 00088
000028049116102059075131038059 13000000000000000000000000000000 01111 00098
046084038060102088075070131024 13001300111010101000000000000000 01011 00099
004099092105102088096080131048 11001300000013001300000018001500 01101 00104
004099092051102088096080131022 13000000000013000000000013000000 01111 00105
131000131000131000131000131024 12121212120012001300010018000100 00001 00112
000068044102099076089131081024 08000800080008000808080808080808 01011 00123
131012025131099076089131052000 13000100000010000300000008000600 00111 00076
131012025131099076048052131020 13000000000013001000130012001300 01001 00068
000036081044099076048131065000 13000000000013000000000008000000 01111 00066
028110064089099076094076012000 13000000131300000812000012001500 00011 00063
000105131089065012048131086027 13001500150012001300120015121512 01001 00059
048044000131065012048131086041 13001300120001000100030013130100 01011 00056
048131105088065084099131043001 13000000130005000000050000000300 01101 00054
030131033088065064099131043014 13000013000013001200001200001500 11111 00050
048129051068065107092105131028 13001500000012000800050000000600 01111 00036
000051046054099072025128067044 13001200130000001300010000001500 11101 00033
```
