# Open issues: `player`

**Method and limits.** This review was done by reading the code. Nothing was
executed: no tests, no playback, no profiling. Each item says whether it is
*confirmed by reading* (the code plainly does it) or *needs measurement* (a
plausible cause that must be checked on a real run). Locations are given as
file and function because line numbers drift. The one test run recorded at the
end was made later, while fixing L2.

Severity: **High** = audible or wrong output, or it blocks the stated goal.
**Medium** = real defect or risk, not audible today. **Low** = cosmetic,
documentation, or hygiene.

---

## High

### H2. Mixing and output are strictly serial; no read-ahead
*Confirmed by reading.*
The loop in `MixPlayer.play` is `mix(block)` then a blocking `write(block)`.
Any block that takes longer than `block / rate` (46 ms at 2048 frames) is an
audible gap, and nothing absorbs the spike where many events start at once.
**Fix:** a producer thread mixing 0.5 to 1 s ahead into a bounded queue, with
the main loop only draining it (this is fix 3 in `SHUTTER_ISSUE.md`). Pause,
resume, Esc and `KeyboardInterrupt` must still be handled, and see M11 for
`SampleStream` thread safety.

### H3. The mixer is pure Python, per sample
*Confirmed by reading; headroom needs measurement.*
`Mixer._mix_mono` and `_mix_stereo` loop over every active event in Python, so
cost scales with the number of active events. `clamp16` is no longer called
per sample (H5 clips once per block), but the accumulation itself is still
per sample. `audioop` is gone in Python 3.13
(the project requires `>=3.13`), and the standard-library-only rule rules out
numpy without asking (see `TODO.md` item 2). Mixing ahead (H2) only helps if the
*average* cost per block is below real time.
**Fix:** first add timing instrumentation, for example a hidden `--profile`
that reports worst and mean block time per second of audio. Then decide between
algorithmic savings (skip silent events, cheaper inner loops) and an optional
accelerated path that is approved as a dependency.

### H4. Underruns are neither detected nor reportable; latency is fixed
*Confirmed by reading.*
`AudioOutput.write` ignores the value `sounddevice` returns (the underflow
flag), and `open()` does not pass a `latency`, so PortAudio's low-latency
default is used with a Python mixer behind it. A user cannot tell a slow mixer
from a device problem.
**Fix:** record underflows and print a count (or the first few with their
timestamps) in verbose mode; add a `--latency` option (`low`, `high` or
seconds) forwarded to `RawOutputStream`.

---

## Medium

### M2. `Any` is used but not imported in three format modules
*Confirmed by reading.*
`dance_mix_format.py`, `hiphop_mix_format.py` and `techno_mix_format.py` annotate
with `Mapping[str, Any]` but import only `Mapping`. It works at runtime only
because of `from __future__ import annotations`; `typing.get_type_hints` and any
linter fail.
**Fix:** `from typing import Any, Mapping`.

### M3. The RIFF "header only" length probe reads the whole file
*Confirmed by reading.*
`SampleDecoder.decode_length` reads `HEADER_BYTES` (4096), and
`RiffDecoder.length` raises "RIFF stream is truncated" whenever the data chunk
extends past those bytes. That is every WAV larger than about 4 KB, so the
decoder re-reads the entire file for each. Load therefore reads every WAV in
full, contrary to the "loading only reads each sample header" claim in the
README and `docs/architecture.md`.
**Fix:** give `RiffDecoder` a header-only length that uses the declared data
size without requiring the payload, and validate against the real size
separately when it is known (file size or `ref.size`).

### M5. There are two implementations of tPxd decoding
*Confirmed by reading.*
`PxdDecoder.decode` and `PxdStreamDecoder.read` must stay bit-identical. They
already differ at the edges: the standalone decoder has no bound check before
`s16(book, entry)` and can raise `struct.error` (not a `SampleError`) on a
malformed stream, while the streaming decoder stops at the end of the code
book. A new test checks equivalence for one synthetic stream only.
**Fix:** implement one in terms of the other (the standalone decoder as a loop
over the stream decoder), or share the core loop. Extend the equivalence test to
real fixtures when `data/hyper-test.pxd` is present.

### M6. Docs and AGENTS claim Techno's long-entry bytes are preserved; the code drops them
*Confirmed by reading.*
`techno_mix_format._read_events` stores only `parameters={"long": <bool>}`. The
10 extra bytes, the flag byte and the second `i16` are discarded. `AGENTS.md`
("preserved, not interpreted") and `docs/formats.md` ("preserved as
`parameters["long"]`") say otherwise.
**Fix:** either keep the raw bytes in `parameters` (they are small) or correct
the docs. Keeping them is the safer path for later reverse engineering.

### M7. Dance and Hiphop are copy-paste duplicates; `resolve_sample` exists three times
*Confirmed by reading.*
`DanceEventBuilder` and `HiphopEventBuilder`, `DanceGrid` and `HiphopGrid`, and
most of the two mix-format classes are the same code (differences: names, magic,
default BPM). `resolve_sample` is implemented in Rave, Dance and (as
`_resolve_sample`) Hiphop. Each call lists a directory at every path component
with no caching, so load does repeated `iterdir()` calls per sample, which is
slow on a CD or ISO mount. Related: `TODO.md` item 4.
**Fix:** a shared grid event builder parameterised by format name and default
BPM, and one case-insensitive resolver with a per-directory listing cache,
placed under `formats/` (not in the format-agnostic core).

### M8. `--device` errors give a traceback, and devices cannot be listed
*Confirmed by reading; behaviour assumes current `sounddevice`.*
`AudioOutput.open` converts only `sd.PortAudioError`. An unknown device name or
index makes `sounddevice` raise `ValueError`, which escapes as a traceback.
There is also no way to list devices from the CLI.
**Fix:** catch `ValueError` and `OSError` as `PlaybackError`; add
`--list-devices`.

### M10. Catalog and INF readers misalign silently on bad input
*Confirmed by reading.*
`HiphopSampleIndex.read` and `_quoted_lines` (Dance) keep only lines that start
and end with `"`; one malformed or unquoted line shifts every later record, so
every following id resolves to the wrong file with no error. `TechnoSampleIndex`
skips a bad record with `continue` and keeps stepping by 12, so one bad record
can mis-parse the rest. The Dance legacy reader instead fails the whole mix on
one out-of-range key.
**Fix:** validate record shape (expected line count, quote pairs) and report the
first bad record number; decide one policy (fail, or skip with a warning) and
use it across readers.

### M11. `SampleStream` keeps all decoded frames and is not thread-safe
*Confirmed by reading.*
After the streaming fix, decoded frames stay resident until `close()` (about
2 bytes per frame; a 2.5 s loop is about 220 KB). This is fine for the shipped
mixes but is unbounded for very long samples. The class has no locking, so the
producer thread proposed in H2 must be the only thread that touches streams.
**Fix:** document it. Optionally add a size cap that releases the cache of
non-looping events after they end.

### M12. Only `MixError` is handled; other exceptions become tracebacks
*Confirmed by reading.*
`MixPlayer.play` and `show` catch `MixError`. A `struct.error`, `ValueError`
(for example a bad `--bpm`) or `OSError` raised in a parser or resolver, or in
M5's standalone decoder, escapes as a traceback instead of a message and exit
status 1.
**Fix:** catch `Exception` at the CLI boundary, print the message (and the
traceback only with `-v`), return 1.

---

## Low

### L1. `format_time` can print `0:60.00`
*Confirmed by reading.* `"%d:%05.2f"` rounds 59.996 s up to `60.00`. Round to
hundredths first, then split into minutes and seconds.

### L3. Test suite gaps and runner behaviour
*Confirmed by reading.*
- `main()` stops at the first failing test, so one failure hides the rest.
- A skipped test (`test_tp_fixture`) is counted in "N tests passed", which
  `AGENTS.md` says not to imply.
- Not covered: pause/resume and Esc through `MixPlayer.play`, `AudioOutput.open`
  and its error paths, `--quiet`, a stream that fails during playback, stereo
  events backed by streams, `format_time` rounding, any timing or underrun
  regression, and any real Hiphop mix.

### L4. Style and code hygiene
*Confirmed by reading.*
- `sugar.py` logo lines far exceed 79 columns; imports are not grouped
  (`sys` then `re`).
- `SampleStream.window` has a redundant duplicate `take = min(take, remaining)`.
- `SampleStream.decode` docstring says it returns an empty array on failure; it
  returns silence of the declared length.
- `playback_keys.available()` runs `isatty()` and an import on every block, and
  `read()` calls it again.

### L5. `Mixer.mix` silently misrenders non-contiguous calls
*Confirmed by reading.* Events are consumed through `_next`, so calling
`mix(start, ...)` out of order (for example seeking, or replaying on the same
instance) drops events with no error. The docs say ranges are contiguous, but
the code does not enforce it. Raise `PlaybackError` on a gap or rewind, or
support seeking explicitly.

### L6. Playback controls are Windows-only
*Confirmed by reading.* `playback_keys` uses `msvcrt`; elsewhere Space and Esc do
nothing. This is documented as "a Windows console", so only worth acting on if
non-Windows use matters.

### L7. Format-detection edge cases
*Confirmed by reading; likelihood low.*
- Rave `parse` finds the trailer by scanning for `0x0A08` at record-aligned
  offsets; a grid cell in the first word of a record holding id 2568 would be
  taken for the trailer and truncate the arrangement.
- Techno `_read_events` uses the first `>?~>` found anywhere in the file.

---

## Resolved

### H1. `-v` prints to the console inside the real-time loop
Fixed. `MixPlayer.play` no longer prints from the render loop. Every verbose
line, pause/resume notice, and `slow block` report goes to
`player/event_printer.py`, whose worker thread performs the console write;
`EventPrinter.announce` builds the event line itself.
`EventPrinter.close()` drains the queue before the player prints `done` or
`stopped`, so the order is unchanged and the loop never waits for the console.
`test_event_printer_moves_console_writes_off_the_caller` holds the stream
closed until `announce` has returned, and
`test_verbose_playback_announces_every_event` checks the full ordered output.
The worst block time still needs a measurement on `VIBE.MIX` (H2 to H4).

### H5. Clipping is applied after every addition, so the result depends on event order
Fixed. `Mixer.mix` sums every event into a 64-bit `array('q')` accumulator
and clips once per output frame when the block is converted to int16. The
result is order-independent: `+30000, +30000, -30000` renders as `30000`.
A block that stays in range is converted in one C-level array copy; only an
over-range block takes the per-frame `clamp16` path.
`test_mixer_sums_before_clipping` covers three overlapping mono events in
both orders plus stereo summation and clipping. This also removes the
per-sample `clamp16` call from the inner loops (H3).

### L8. Techno pan law — unity-centre, verified against the engine and applied
Answered from the binary, not from the docs. The engine `TECHNO.EXE` drives is
`disks/Techno_eJay/EJAY/EJAY/PXD32R4.DLL` (87 exports; `TECHNO.EXE` names
`pxd32r4.dll` at file offset `0x19DEC`), which is a different binary from the
Dance engine analysed in `work/pxd/`. Three findings (addresses in `work/docs/PXD32R4.md`, conclusion in
`MIX_FORMAT_TECHNO.md` §13):

- **Not constant-power.** Gain is `(voice[0x7C] * voice[0x44]) >> 8`, applied as
  `(sample * gain) >> 16`, with unity `0x10000 * 0x100`; there is no `fsqrt` and
  no pan table anywhere in `.text`.
- **Pan is a channel selector, not a curve.** The pan word is only compared
  against 0/2/3; `== 2` moves the output word cursor by 2 bytes, i.e. one slot.
- **The `.MIX` stores no pan.** Track blocks are `u8 track, u32 count`; the
  stereo image comes from paired `...L`/`...R` samples on separate tracks
  (track 4 `dj 1L` vs track 5 `dj 1R`, tracks 13/14 `thunder L`/`R`).

So L8's premise was inverted: no 0.5 gain exists in the engine, hard-panned
tracks are at the reference level, and it was the player's `0.5/0.5` centre that
sat 6 dB low. Fixed: `TechnoEventBuilder` now uses `track_gains` and returns
`(1.0, 1.0)` for a centred track, `(1.0, 0.0)` left and `(0.0, 1.0)` right.
`test_techno_pipeline` asserts the centred sample renders as `[1000, 1000]`
instead of `[500, 500]`.

Measured on `WAMBAM.MIX` (171 events: 129 centred, 21 left, 21 right; 113.1 s),
the whole arrangement mixed with both laws:

| law | peak L / R | RMS L / R | clipped frames |
|---|---|---|---|
| old `0.5/0.5` | 17078 / 15449 | 2372.6 / 2397.6 | 0 of 4 989 600 |
| new `1.0/1.0` | 26692 / 25332 | 4394.0 / 4407.7 | 0 of 4 989 600 |

That is +5.35 dB left and +5.29 dB right in RMS, +3.9 / +4.3 dB in peak, with
the peak still 1.8 dB below full scale: nothing clips on this mix. No other
mix was measured, and `--gain` remains the escape hatch if one does.

Still open: whether the engine writes a centre voice to both channels in one
pass (`work/docs/PXD32R4.md` §7).

### L2. Documentation is stale or wrong in places
Fixed in the docs; no behaviour changed. Each item was checked against the
tree first:

- **Package name.** The library examples in `README.md` and `mix_player.md`
  import `from player import MixPlayer`; the argparse `prog`, the
  `MixPlayer._error` prefix, `__main__.py`'s docstring,
  `player/docs/architecture.md` and every `:class:`~mix_player.*`` docstring
  cross-reference now say `player`, and the manual's title follows. The names
  that stay are artefacts rather than stale API: the manual file
  `mix_player.md`, the frozen executable `mix_player.exe`, and
  `sugar.mix_player_logo`.
- **Hiphop missing.** `player/README.md` (intro, supported-format table,
  package layout, docs list, test description), `player/AGENTS.md` (intro,
  read-first list, format-note list, file map, definition of done) and
  `mix_player.md` now include Hiphop.
- **`player/docs/adding-a-format.md`.** The skeleton imports `PlaybackEvent`,
  and the `MixRegistry.default()` example lists all four shipped formats in
  detection order ahead of the new one.
- **Path.** `player/AGENTS.md` points at `../docs/formats/MIX_FORMAT_*.md` in
  both places.
- **Header size.** `MixFormat.matches` now says the registry supplies 32
  bytes, matching `MixRegistry.detect` and the checklist.
- **Hiphop version.** Not a defect: Dance, Hiphop, Rave and Techno are all at
  `2.0.0`, so Hiphop follows the same MAJOR bump. The "a new format starts at
  `1.0.0`" rule still applies to future formats.

Still open from L2's neighbourhood: the manual still ships as
`mix_player.md` and the frozen build as `mix_player.exe`, which is deliberate
but worth renaming together if the product name ever changes again.

### M9. CLI startup output and entry-point issues
Fixed. `main()` now parses the arguments before printing anything, so `--help`,
usage errors and `--list` output carry no decoration; the logo, version and
format list are printed only when stdout is an interactive terminal and
neither `-q` nor `--list` is set. `sugar.py` picks between three banners: the
colour logo when the terminal understands ANSI codes, the same glyphs without
colour codes when it can encode them, and an ASCII box when the code page
cannot. The old fallback was the fancy logo with only the escape codes
stripped, so a cp1252 console still raised `UnicodeEncodeError`; that is what
`python -m player --help > help.txt` hit. ANSI is now emitted only for an
interactive terminal (and not with `NO_COLOR` set), and on Windows only for
hosts that enable VT processing, because the legacy console prints the codes
as text. The `sugar` import moved below the `if __package__ in (None, "")`
path fix, so `python player/cli.py` runs too.

Verified: `--help` and `--list` redirected to a file contain no escape code
and no banner; the banner renders as the ASCII box for a cp1252 stream and
without colour codes for a UTF-8 stream that is a terminal but has no
Windows terminal host.

### M1. The Hiphop plugin is half-integrated
Fixed. `formats/hiphop/__init__.py` now mirrors the Dance package and imports
`HiphopEventBuilder`, `HiphopGrid`, `HiphopMixFormat`,
`HiphopSampleCollector`, `HiphopSampleEntry`, and `HiphopSampleIndex`.
`HiphopMixFormat` is exported from both `formats/__init__.py` and
`player/__init__.py`, beside the other shipped formats. `HiphopSampleEntry`
moved to `hiphop_sample_entry.py`; `hiphop_sample_index.py` gained a module
docstring and now holds only `HiphopSampleIndex`. The package layout table in
`player/README.md` follows the split.

### M4. `RiffStreamDecoder` has the same per-frame Python cost the tPxd path just lost
Fixed. `read()` indexes the already-loaded `StreamSource.data` directly
instead of calling `source.read` and maintaining a deque for every output
frame. At 44.1 kHz it copies the requested range with one slice, including a
single `array.frombytes` for 16-bit mono; only resampling still loops per
output frame, using the same `int(index * rate / 44100)` mapping and
last-frame clamp as `RiffDecoder.decode`. The input frame count follows
`RiffDecoder.length`'s 8-bit ceiling rule, so an odd-sized 8-bit stereo
stream now returns the final partial frame that `RiffDecoder` already
returned. `test_riff_stream_decoder_matches_full_decoder` compares both
decoders across mono/stereo, 8/16-bit, native, lower and higher rates, with
uneven read sizes and a reset. On a 2,000,000-frame 16-bit mono 44.1 kHz WAV
read in 2048-frame blocks, the old decoder took 2.530 s (0.79 Mframes/s) and
the new one 0.018 s (108.32 Mframes/s), about 140x faster on that run.

---

## Tracked elsewhere / housekeeping

- `TODO.md` item 5 (failing Dance mixes `DRUMSYNT`, `RAPSVOIC`, `SOFTVOX`,
  `SPACE`, `START_RE`, `THEFLOW`, `X_PERM`): still open, not analysed in this
  review. Worth rerunning with `-v` after the streaming change, since stream
  decode errors are only reported at the end of playback (`_report_decode_errors`).
- `TODO.md` item 7 ("use stream in player instead of load and convert PXD files
  at start"): done in the current tree; remove it.
- `TODO.md` item 4 ("review mix format, simplify player code"): overlaps M7.

## Verification status (from the streaming change)

Per `AGENTS.md` "Definition of done":

- [x] `python -m player.test_mix_player` passes (36 tests, one skipped while
      `data/hyper-test.pxd` is absent), run while fixing L2.
- [ ] `--list` works on a real Rave, Dance, Hiphop and Techno mix.
- [ ] Replay `VIBE.MIX` with and without `-v`, with the timing snippet from
      `SHUTTER_ISSUE.md`, and record the worst block time.
- [ ] `VERSION` bumped to `1.1.1` if the streaming fix is released.
