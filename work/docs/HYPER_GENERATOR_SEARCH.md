# Search: "hyper generator" in RAVEEJAY.EXE

> The data side of the feature — sound bank, presets, screen — is written up in
> `HYPER_GENERATOR.md`. This note only records the string search.

Target: `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (PE, 777728 bytes), inspected
with `../tools/disapp.py` (or a direct byte scan).

Result: **No "hyper generator" (or "generator") string exists in the binary.**

`"hyper"` occurs 18 times. Related identifiers present:

- `hyper`, `hyperweg`, `hypersub`
- `hyp1` … `hyp8`
- `hypmenu`, `hypermenu`
- `hypreset`
- `hyper_Click`, `hypersub_Click`
- `hypercall`, `HypePlay`

Conclusion: the name "hyper generator" is not present in `RAVEEJAY.EXE`.

## DLL check: `pxd32d5_d4.dll`

Searched the same way. Result: no "hyper" or "generator" strings; only one
"hyp" occurrence. The audio engine DLL contains no hyper-generator feature.

## What the shipped data does say

The tables `disks/Rave_eJay/RAVE/EJAY\HYPSOUND` (128 sounds in 8 groups under `hyper\`) and
`disks/Rave_eJay/RAVE/EJAY\HYPRESET` (20 presets) parse completely, and the help strings describe the
screen in detail — matrix of one bar with 16 steps, filter/distortion/echo,
one-bar save into Sound Group HYPER. See `HYPER_GENERATOR.md`.
