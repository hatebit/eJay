# work/src/ — Python port and standalone players

Standard-library-only Python that reproduces the parts of the eJay engine
documented under `../docs/` and `../pxd/`. Nothing here imports `../../lib/` or
`../../player/`; those are independent clean implementations.

## Modules

| file | purpose |
|---|---|
| `pxd32d5.py` | the port: `PInit`, `RWavToTemp`, `PClose`, `Engine`, `Session`, `tPxd`/RIFF decoders |
| `pxd32d4.py` | eJay 2 (`PXD32D4.DLL`) port: engine facade, `APlay`, `AWaveDauer`, `RWavToTemp`, both decoders |
| `tp_codec.py` | reference decoder and ladder builder for the D4 `tP` code (`../docs/PXD32D4.md` §10.2-10.3) |
| `pxd2wav.py` | CLI built on the port (`.pxd` to WAV/PCM) |
| `pxdplay.py` | playback demo through the ported engine |
| `pxdsink.py` | output sinks: `FileSink`, stdlib `ctypes` `waveOut`, optional `sounddevice` |
| `pxdstream.py` | header/inspection helper for `.pxd` streams |
| `pxdhelpers.py` | shared helpers |
| `scan_pxd_headers.py` | batch header scan |
| `mixplay.py` | Rave eJay `.MIX`: grid + `EJAY/PXD` index, engine play requests |
| `sdmixplay.py` | standalone Rave `.MIX` player (own decoder + mixer) |
| `sdmixplayer2.py` | standalone Techno `.MIX` player (`RAVE20.INF` + archive) |
| `mixsamples.py` | list the `RAVE20.INF` samples a Techno mix references |
| `sdpxdplay.py` | standalone `.pxd` player |
| `hyperplay.py` | Hyper Generator preset player |
| `test_pxd32d5.py` | main verification suite |
| `test_tp_codec.py` | tests for the D4 reference decoder |
| `test_pxd32d4.py` | tests for the D4 engine port |
| `test_pxd2wav.py` | WAV conversion regression tests |
| `test_sdmixplay.py` | standalone Rave player tests |
| `test_sdpxdplay.py` | standalone `.pxd` player tests |
| `test_mixplay.py`, `test_mixplay_exact.py` | engine-driven `.MIX` tests |

## Running

Run from `work/` (the scripts resolve `../pxd/` and `../data/` relative to this
folder):

```sh
python src/test_pxd32d5.py
python src/test_pxd32d4.py
python src/pxd2wav.py song.pxd -o out/
python src/mixplay.py "../disks/Rave_eJay/MIX/TRANCE.MIX" --list
```

The fixture files (`data/bo-test.pxd`, `data/hyper-test.pxd`) are not checked
in; tests that need them skip when they are absent.

`sounddevice` is an optional, lazily imported dependency for the playback
commands. Everything else uses only the standard library.

## Documentation

* [`../AGENTS.md`](../AGENTS.md) — rules, invariants and commands.
* [`../docs/RWavToTemp.md`](../docs/RWavToTemp.md) — the conversion path.
* [`../../docs/formats/PXD_FORMAT.md`](../../docs/formats/PXD_FORMAT.md) — the
  `tPxd` container.
