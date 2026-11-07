# lib/ — standalone eJay tools

Small, read-only, standard-library-only readers and players for the eJay
formats. This is the clean implementation: it does not import `work/` and it
never touches the original DLL.

## Tools

| file | what it does |
|---|---|
| `pxd_file.py` | parse and decode a `tPxd` (`.pxd`) sample; `PxdFile`, `PxdDecoder`, `PxdComment` |
| `pxd_info.py` | print a `.pxd` summary; `--samples` decodes and reports statistics |
| `pxd_play.py` | play one `.pxd` through `sounddevice` |
| `pxd_to_wav.py` | convert `.pxd` to WAV (or headerless PCM with `--raw`) |
| `mix_file.py` | parse a Rave eJay `.MIX` arrangement and its `EJAY/PXD` sample index |
| `mix_info.py` | print a `.MIX` summary; `--events` lists collapsed events |
| `mix_play.py` | play a Rave eJay `.MIX` without the original engine |

Run any tool directly; the scripts add their own folder to `sys.path`, so the
current directory does not matter:

```sh
python lib/pxd_info.py path/to/sample.pxd
python lib/pxd_info.py --samples path/to/sample.pxd
python lib/pxd_to_wav.py path/to/sample.pxd -o out/
python lib/mix_info.py path/to/song.MIX --events --index path/to/EJAY/PXD
python lib/mix_play.py path/to/song.MIX --res path/to/RAVE
```

## Requirements

* Python 3.13 or newer (see `../pyproject.toml`).
* The standard library only for parsing, listing and conversion.
* `sounddevice` only for `pxd_play.py` and `mix_play.py`. It is imported
  lazily, so the other tools and imports work without it.

```sh
python -m pip install sounddevice
```

## Documentation

* [`AGENTS.md`](AGENTS.md) — rules for changing this folder.
* [`../docs/formats/PXD_FORMAT.md`](../docs/formats/PXD_FORMAT.md) — `tPxd`
  container and codec.
* [`../docs/formats/MIX_FORMAT_RAVE.md`](../docs/formats/MIX_FORMAT_RAVE.md) —
  Rave eJay `.MIX` grid and sample index.
* [`../docs/README.md`](../docs/README.md) — the full documentation index.
