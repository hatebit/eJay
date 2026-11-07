# HYPRESET — Hyper Generator preset table

File: `disks/Rave_eJay/RAVE/EJAY\HYPRESET` (1 732 bytes, ASCII, CRLF line endings, no BOM,
ends with CRLF). Describes the 20 factory presets of the Rave eJay Hyper
Generator. Each preset references one sound from the HYPSOUND bank
([`../../work/docs/HYPER_GENERATOR.md`](../../work/docs/HYPER_GENERATOR.md) is the
sibling document for `HYPSOUND`) plus a 16-step
sequencer pattern and effect switch settings.

See [`../../work/docs/HYPER_GENERATOR.md`](../../work/docs/HYPER_GENERATOR.md) §3
for the cross-referenced preset/sound table and §4 for the screen's UI
elements; see
[`../../work/docs/HYPER_GENERATOR_DSP.md`](../../work/docs/HYPER_GENERATOR_DSP.md)
for the
DSP controller that consumes these tables.

## File layout

```
<name>\r\n
<A:30> <B:32> <C:5> <D:5>\r\n
...                                         (repeated 20 times)
```

40 lines total: 20 records of two lines each. The data line is always 75
characters (30 + 1 + 32 + 1 + 5 + 1 + 5), single spaces separating the four
fields. All field widths are fixed across all 20 records, so a value cannot be
read in two different widths.

| field | width | content | observed values |
|---|---|---|---|
| A | 30 | 15 two-digit numbers, read as 5 triples | see §2.1 |
| B | 32 | 16 two-digit numbers, one per 16th of a bar | 0–18, `0` = rest |
| C | 5 | five binary digits | 9 distinct values, last digit always `1` |
| D | 5 | five-digit sound id | 33–123, all distinct |

The letters A–D are this document's names; the file has no field headers.

## Field D — sound selector

D is the preset's hyper sound id. All 20 values are live ids from HYPSOUND
(§2 of [`../../work/docs/HYPER_GENERATOR.md`](../../work/docs/HYPER_GENERATOR.md)),
and all 20 are different. The preset names
line up with the referenced sounds:

| preset | D | sound (group id name) |
|---|---|---|
| Hard B | 50 | Hardbass `050 Half Pipe` |
| Sub Bass | 68 | Softbass `068 Dull Buzz` |
| Kick Away | 121 | Strikes `121 Boxing Glove` |
| Il Ritmo | 112 | Strikes `112 Great Can` |
| Snare Break | 123 | Strikes `123 Thin Snare` |
| Nose | 33 | Rave `033 Rave Vibration` |

Distribution over the groups: Hardbass 6, Comic 4, Strikes 4, Softbass 3,
Rave 1, Trash 1, Space 1, Vibes 0. The ids are not sorted by name or id, so
the file order is presumably the order the app lists them in **(unverified)**.

## Field B — 16-step sequencer matrix

B has 16 slots, one per 16th division of a bar (the screen's `H_LEDFELD`
matrix). 203 of the 320 slots are `0`, and the number of active steps per
preset ranges from 1 (`Rave Hit`) to 12 (`Snare Break`). Patterns are
musically regular:

- `Kick Away` places `15` on steps 1, 5, 9, 13 plus a pickup on step 15
- `Shake It` places `10` on steps 1, 3, 7, 11, 15
- `Il Ritmo` fills steps 1–5 and then every other step

**Assumption: each non-zero B value is a note index.** The screen's keyboard
has 18 keys (from `EJAY\KONST`/`EJAY\HKONST`). The number-to-note mapping is:

| B value | note | UI element |
|---|---|---|
| 1 | G | H_G |
| 2 | Ab | H_AS |
| 3 | A | H_A |
| 4 | Bb | H_B |
| 5 | B | H_H |
| 6 | C1 | H_C |
| 7 | Db1 | H_DES |
| 8 | D1 | H_D |
| 9 | Eb1 | H_ES |
| 10 | E1 | H_E |
| 11 | F1 | H_F |
| 12 | Gb1 | H_GES |
| 13 | G1 | H_G2 |
| 14 | Ab1 | H_AS2 |
| 15 | A1 | H_A2 |
| 16 | Bb1 | H_B2 |
| 17 | B1 | H_H2 |
| 18 | C2 | H_C2 |

Values run to `18`, which matches the 18-key range exactly, so reading B as
note index maps 1→G through 18→C2. This remains **(unverified)** but is the
interpretation used by [`../../work/src/hyperplay.py`](../../work/src/hyperplay.py),
which treats each non-zero B slot as
a trigger of the preset's base sound at that step (pitch-shifted according to
the note value).

## Field C — five switches

C is always five `0`/`1` digits; nine combinations occur
(`00001`, `00011`, `00111`, `01001`, `01011`, `01101`, `01111`, `11101`,
`11111`). The last digit is `1` in all 20 presets, so it is either a
reserved/version flag or a switch that factory presets always enable; the first
digit is set in only 3 presets.

The screen has exactly five on/off toggles — filter, distortion, echo, 1/16
cut, volume (`H_FILTER`, `H_DISTORTIONLED`, `H_ECHO`, `H_116`, `H_VOLUMELED`)
— which is the strongest available mapping, but the bit order is not
established **(unverified)**.

A cross-check against field A (a switch off would leave its parameters at
zero) only matches 6 of 20 presets, so C is not simply "A triple is zero".

## Field A — 15 numbers, five parameter triples

A is always 15 two-digit numbers. As 5 triples the value sets are not drawn
from one range, which suggests three different quantities:

| slot | observed values | note |
|---|---|---|
| `A[3i]` | 0–10 and 13 | small selector or mode |
| `A[3i+1]` | 0, 1, 10, 11, 20, 21, 30, 40, 41, 50, 51, 60, 70, 80, 81, 90, 91 | only multiples of 10, plus `+1`; reads naturally as tenths, 0.0–9.1 |
| `A[3i+2]` | 0–99 | amount in percent |

The shape (5 × 3) matches the five toggle groups above, but the screen has
four filter faders, two distortion faders and three echo faders, so a
one-to-one device mapping does not fit. Whether A is effect parameters, note
data, or something else is **(unverified)**; the raw values are in §6.

## The 20 presets

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

## Appendix A — the 20 preset data lines, verbatim

Fields are `A B C D` as in §1 (`A` 30 chars, `B` 32, `C` 5, `D` 5).

```
056017081076065012048131043035 13000000000001000000000000000000 01101 00055
040099094009100078091107089012 10001000000010000000100000001000 11111 00119
044072131131131131131131067016 150000001500000015001500 01011 00121
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

## Open questions

1. Meaning of the A triples (effect parameters vs. note data) and of the B
   values above the 13 labelled keys.
2. Order and polarity of the five C switches.
3. Does the app read `HYPRESET` in this exact 2-line, fixed-width form, and
   are A/B/C stored as decimal text or converted to bytes at load time?
4. How a live-saved sample enters the HYPER group: the screen strings say it
   becomes a sample, but nothing in the data files shows whether `HYPSOUND` is
   rewritten.
