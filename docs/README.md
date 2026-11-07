# Documentation

Reference material for the eJay formats, the recovered engine behaviour and the
tools in this repository.

## Product and format references

| document | contents |
|---|---|
| [`formats/INDEX.md`](formats/INDEX.md) | format notes grouped by eJay product |
| [`formats/PXD_FORMAT.md`](formats/PXD_FORMAT.md) | `tPxd` (`.pxd`) sample container and DPCM codec |
| [`formats/MIX_FORMAT_DANCE.md`](formats/MIX_FORMAT_DANCE.md) | Dance eJay `.MIX` grid, optional metadata and both sample catalogs |
| [`formats/MIX_FORMAT_DANCE2.md`](formats/MIX_FORMAT_DANCE2.md) | Dance eJay 2.0 `.MIX` event table and kit archives |
| [`formats/MIX_FORMAT_RAVE.md`](formats/MIX_FORMAT_RAVE.md) | Rave eJay `.MIX` grid and `EJAY/PXD` index |
| [`formats/MIX_FORMAT_TECHNO.md`](formats/MIX_FORMAT_TECHNO.md) | Techno eJay `.MIX` trailer and event table |
| [`formats/INF_FORMAT.md`](formats/INF_FORMAT.md) | `RAVE20.INF` sample index |
| [`formats/HYPRESET_FORMAT.md`](formats/HYPRESET_FORMAT.md) | Hyper Generator `HYPRESET` records |
| [`RAVE_HELP.md`](RAVE_HELP.md) | Rave eJay manual text |
| [`TECHNO_HELP.md`](TECHNO_HELP.md) | Techno eJay manual text |

## Tool documentation

| document | contents |
|---|---|
| [`../mix_player.md`](../mix_player.md) | player command-line manual |
| [`../player/README.md`](../player/README.md) | player package overview |
| [`../player/docs/architecture.md`](../player/docs/architecture.md) | pipeline, data model and playback rules |
| [`../player/docs/formats.md`](../player/docs/formats.md) | what the Rave, Dance, Dance 2, Hiphop and Techno plugins do |
| [`../player/docs/adding-a-format.md`](../player/docs/adding-a-format.md) | extension guide |
| [`../lib/README.md`](../lib/README.md) | standalone tools |
| [`../web/README.md`](../web/README.md) | browser `.pxd` to WAV converter |

## Reverse-engineering notes

| document | contents |
|---|---|
| [`../work/docs/README.md`](../work/docs/README.md) | port, conversion and playback notes |
| [`../work/pxd/README.md`](../work/pxd/README.md) | DLL analysis document set (2001 Dance eJay3 engine) |
| [`../work/AGENTS.md`](../work/AGENTS.md) | evidence rules and invariants |
