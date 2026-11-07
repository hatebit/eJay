# eJay tools

Tooling and reverse-engineering notes for the eJay music-creation products.
The project reads and plays eJay `.MIX` arrangements and `tPxd` (`.pxd`)
samples without the original software, and documents the containers and the
engine behaviour it reproduces.

## Structure

| path | role |
|---|---|
| `disks/` | extracted ISO images (game data; ignored by git) |
| `docs/` | user-facing notes: product help and the format reference under `docs/formats/` |
| `iso/` | ISO download index (`index.json`) and the eJay product table |
| `lib/` | standalone, standard-library-only readers/converter/players |
| `player/` | the extensible `.MIX` player: shared mixer plus format plugins |
| `web/` | single-page browser `.pxd` to WAV converter |
| `work/` | reverse-engineering workspace: Python port, notes and analysis tools |
| `mix_player.md` | command-line manual for the player |
| `iso_download.py`, `iso_extract.py` | fetch an ISO from the index and unpack it |

`work/` is the research area and is deliberately noisier than `lib/` and
`player/`, which are the clean results of it. Agent/contributor rules live in
the nearest `AGENTS.md`; start with the root [`AGENTS.md`](AGENTS.md).

## Getting started

Python 3.13 or newer is required by `pyproject.toml`; the `lib/` tools
themselves use only the standard library.

```sh
# dependencies (pycdlib for ISO extraction)
uv sync
```

Download and unpack a disc image:

```sh
python iso_download.py "Rave eJay"
python iso_extract.py "Rave eJay"          # -> disks/Rave_eJay/
```

### Play a mix

Run from the repository root:

```sh
# list first (no audio device needed)
python -m player "disks/Rave_eJay/MIX/TRANCE.MIX" --pxd "disks/Rave_eJay/RAVE" --list
python -m player "disks/Dance_eJay/MIX/FREAK.MIX" --list
python -m player "disks/Dance_2/MIX/CAMRON.MIX" --list
python -m player "disks/Techno_eJay/MIX/WAMBAM.MIX" \
    --pxd "disks/Techno_eJay/EJAY/PXD" --list

# play
python -m player "disks/Rave_eJay/MIX/TRANCE.MIX" --pxd "disks/Rave_eJay/RAVE"
python -m player "disks/Dance_eJay/MIX/FREAK.MIX"
python -m player "disks/Dance_2/MIX/CAMRON.MIX"
```

Playback needs the optional `sounddevice` package (`python -m pip install
sounddevice`). The full option list, examples and troubleshooting are in
[`mix_player.md`](mix_player.md).

### Distribute as an executable

Build a single-file `dist/mix_player.exe` with PyInstaller:

```sh
python build.py
```

The script reads `mix_player.spec` and bundles `player`, `sounddevice`, and the
PortAudio DLLs into one executable. Run it from anywhere:

```sh
dist\mix_player.exe "disks/Rave_eJay/MIX/TRANCE.MIX" --pxd "disks/Rave_eJay/RAVE" --list
dist\mix_player.exe "disks/Dance_eJay/MIX/FREAK.MIX" --list
dist\mix_player.exe "disks/Dance_2/MIX/CAMRON.MIX" --list
dist\mix_player.exe "disks/Techno_eJay/MIX/WAMBAM.MIX" \
    --pxd "disks/Techno_eJay/EJAY/PXD" --list
```

`--list` works without `sounddevice`; playback needs the bundled PortAudio DLL
(which `build.py` includes). `build/` and `dist/` are gitignored.

### Convert or inspect one file

```sh
python lib/pxd_info.py sample.pxd
python lib/pxd_to_wav.py sample.pxd -o out/
python lib/mix_info.py song.MIX --events
```

## Tests

```sh
python -m player.test_mix_player
python work/src/test_pxd32d5.py
python work/src/test_pxd2wav.py
python work/src/test_sdmixplay.py
python work/src/test_sdpxdplay.py
```

## Documentation

| document | contents |
|---|---|
| [`mix_player.md`](mix_player.md) | player command-line manual |
| [`docs/README.md`](docs/README.md) | documentation index |
| [`docs/formats/INDEX.md`](docs/formats/INDEX.md) | format notes by product |
| [`player/README.md`](player/README.md) | player package overview |
| [`lib/README.md`](lib/README.md) | standalone tool overview |
| [`web/README.md`](web/README.md) | browser converter |
| [`work/README.md`](work/README.md) | reverse-engineering workspace and status |
| [`iso/README.md`](iso/README.md) | eJay product list |

## Safety

The original binaries (`*.dll`, `*.exe`) are read-only reference material. Do
not load or execute them; all behaviour is reproduced from static analysis and
reimplemented in pure Python.
