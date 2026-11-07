# TODO list

2. Allow imports, but always ask (`AGENTS.md`)
   > 4. **Standard library first.** `lib/` and `player/` ship standard-library code.
   >    `sounddevice` is an optional, lazily imported playback dependency; `pycdlib`
   >    is only for ISO extraction. New dependencies need a reason and belong in
   >    `pyproject.toml` (or a scratch directory for reverse-engineering tools).
3. when is loop=true in sample
4. Review mix format, simplify player code
8. investigate end of rave MAGIC.MIX (there is a gap?)
9. Use textual