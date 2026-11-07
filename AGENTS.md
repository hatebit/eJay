# AGENTS.md — repository-wide rules

This repository reconstructs the eJay formats and players from static
analysis. Read the nearest folder-level `AGENTS.md` before changing anything in
`work/`, `work/pxd/`, `player/`, `lib/` or `web/`.

## Ground rules

1. **Never execute, load or patch the original binaries.** The engine DLL
   analysed here is not checked in; use a local copy (see
   `work/pxd/README.md`), and anything extracted from `disks/` is reference
   material only. No `ctypes`, `LoadLibrary`, `rundll32`, `regsvr32`, or
   "just testing" an export.
2. **Static analysis only.** Claims about engine behaviour need an address and a
   confidence tag (`[certain]` / `[likely]` / `[guess]`). See
   [`work/AGENTS.md`](work/AGENTS.md) and [`work/pxd/AGENTS.md`](work/pxd/AGENTS.md).
3. **Stay inside the repository.** Do not read or write outside it; the
   `disks/` and `iso/*.iso` payloads are ignored by git and must not be
   modified.
4. **Standard library first.** `lib/` and `player/` ship standard-library code.
   `sounddevice` is an optional, lazily imported playback dependency; `pycdlib`
   is only for ISO extraction. New dependencies need a reason and belong in
   `pyproject.toml` (or a scratch directory for reverse-engineering tools).
5. **Clean code is a port, not a reimplementation.** `lib/` and `player/` are
   independent of `work/`; they must not import it. Container facts come from
   the format notes, not from guessing.

## Where things belong

| change | location |
|---|---|
| new format understanding | `docs/formats/` plus the matching `work/docs/` or `work/pxd/` note |
| player behaviour or a new format plugin | `player/` (see `player/AGENTS.md`) |
| standalone tool or codec | `lib/` (see `lib/AGENTS.md`) |
| browser decoder sync | `web/` only when explicitly requested (see `web/AGENTS.md`) |
| Python port / disassembly tooling | `work/src/` and `work/tools/` (see `work/AGENTS.md`) |

## Documentation discipline

* A behaviour change is incomplete without its documentation. Update the
  specific format note and any affected README.
* Use relative links between Markdown files; keep them working when a file
  moves.
* Do not restate the same table in several documents — link to the owner.
* Keep reverse-engineering addresses, confidence tags and worklog history
  intact. Correct a wrong statement in place and log the correction in the
  matching `-worklog.md` §2.

## Verification

Run from the repository root:

```sh
python -m player.test_mix_player      # player suite (synthetic fixtures)
python work/src/test_pxd32d5.py       # Python port suite
python work/src/test_pxd2wav.py       # WAV conversion
```

## Style

* 4 spaces, no tabs, about 79 columns, no trailing whitespace.
* `snake_case` functions/modules, `PascalCase` classes, `UPPER_CASE` constants.
* Google-style docstrings with `Args` / `Returns` / `Raises` where useful.
* `pathlib` for paths, f-strings for formatting
* no visual unicode in code with exception for `player/`
* No `__all__` in `player/`; explicit imports only.
