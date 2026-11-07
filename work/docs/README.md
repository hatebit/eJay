# work/docs/ — port and playback notes

Focused write-ups for the Python port in `../src/`. Container references live in
[`../../docs/formats/`](../../docs/formats/); the DLL analysis set lives in
[`../pxd/`](../pxd/).

| document | contents |
|---|---|
| [`PXD32D4.md`](PXD32D4.md) | eJay 2 engine `PXD32D4.DLL`: PE facts, 87 exports, voices, temp waves, `tP` |
| [`PXD32R4.md`](PXD32R4.md) | Techno eJay engine `PXD32R4.DLL`: which binary plays a mix, gain path, pan |
| [`RWavToTemp.md`](RWavToTemp.md) | `PInit` / `RWavToTemp` / `PClose` in detail |
| [`PLAYBACK.md`](PLAYBACK.md) | playback path, sinks, transport and what is still unported |
| [`HYPER_GENERATOR.md`](HYPER_GENERATOR.md) | Hyper Generator data: `HYPSOUND`, `HYPRESET`, screen help |
| [`HYPER_GENERATOR_DSP.md`](HYPER_GENERATOR_DSP.md) | DSP extraction from `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` |
| [`HYPER_GENERATOR_SEARCH.md`](HYPER_GENERATOR_SEARCH.md) | string search for "hyper generator" |

Confidence tags and addresses are part of the deliverable: keep them when you
edit. The conventions are in [`../AGENTS.md`](../AGENTS.md).
