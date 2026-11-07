# work/ — reverse-engineering workspace

The research side of the repository. It holds the Python port of the eJay
engine pieces, the notes that justify each claim, and the small scripts used to
produce the evidence.

The clean results live outside this folder: `../lib/` for standalone tools and
`../player/` for the extensible `.MIX` player.

## Layout

| path | contents |
|---|---|
| `src/` | Python port and standalone players (standard library only) |
| `docs/` | port and playback notes, plus the Hyper Generator write-ups |
| `pxd/` | the 2001 engine DLL's document set and analysis scripts (binary **not checked in**) |
| `tools/` | PE readers/disassemblers (`pxd_dis.py`, `disapp.py`) |
| `dumps/` | derived per-mix text dumps used by the Techno notes |
| `data/` | real `.pxd` fixtures — **not checked in**; tests skip when absent |

## Quick start

Run from `work/`:

```sh
python src/test_pxd32d5.py                       # full port suite
python src/pxd2wav.py song.pxd -o out/           # convert a .pxd to WAV
python src/mixplay.py song.mix --list            # Rave .mix arrangement
python src/sdmixplay.py song.mix --list          # same, engine-free
python src/sdmixplayer2.py "../disks/Techno_eJay/MIX/WAMBAM.MIX" --list
PXD_DLL=/path/to/pxd32d5_d4.dll python tools/pxd_dis.py 0x100149E0 40
```

`tools/` needs Capstone; install it into a scratch directory and use
`PYTHONPATH` (see [`AGENTS.md`](AGENTS.md)). `src/` must stay standard-library
only. `sounddevice` is optional and imported lazily by the playback paths.

## Status

* `tPxd` decoding and WAV conversion are ported and verified against the
  documented fixtures; the fixtures themselves are not checked in.
* Playback transport, sinks and the engine-free players are implemented.
* Open items are tracked in [`AGENTS.md`](AGENTS.md) ("Open threads") and the
  `pxd/` worklog.

## Documentation

* [`AGENTS.md`](AGENTS.md) — rules, invariants, commands and open threads.
* [`docs/README.md`](docs/README.md) — notes in this folder.
* [`pxd/README.md`](pxd/README.md) — the DLL analysis document set.
* [`../docs/README.md`](../docs/README.md) — repository-wide documentation index.
