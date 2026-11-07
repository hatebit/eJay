# Architecture

## 1. Goal

`player` separates *what a mix file means* from *how audio is rendered*.
Only three operations know about a container:

1. parse the mix,
2. collect the samples it references,
3. prepare positioned playback events.

Everything after that is shared. Adding a format must not add an `if format
== ...` branch to the mixer, the player, or the CLI.

```
                 format plugin                         common
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐
│  .MIX file   │─▶│ MixFormat.parse  │─▶│ MixDocument  │  │               │
└──────────────┘  └──────────────────┘  └──────┬───────┘  │               │
                                               │          │               │
                  ┌────────────────────────┐   │          │               │
                  │ MixFormat.collect_     │◀──┘          │               │
                  │ samples                │              │               │
                  └───────────┬────────────┘              │               │
                              │ SampleCollection          │               │
                              ▼                           │               │
                  ┌────────────────────────┐              │               │
                  │ SampleDecoder          │  (common)    │               │
                  └───────────┬────────────┘              │               │
                              │ SampleBank                │               │
                              ▼                           │               │
                  ┌────────────────────────┐              │               │
                  │ MixFormat.prepare_     │              │               │
                  │ events                 │              │               │
                  └───────────┬────────────┘              │               │
                              │ PlaybackPlan              │               │
                              ▼                           ▼               │
                  ┌──────────────────────────────────────────────────────┐│
                  │ MixPlayer -> Mixer -> AudioOutput                     ││
                  └──────────────────────────────────────────────────────┘│
```

## 2. Stages

| stage | owner | input | output | format-specific? |
|---|---|---|---|---|
| detect | `MixRegistry` | first 32 bytes | `MixFormat` | no |
| parse | `MixFormat.parse` | path, options | `MixDocument` | yes |
| collect | `MixFormat.collect_samples` | document, options | `SampleCollection` | yes |
| decode | `SampleDecoder` | collection | `SampleBank` (lazy streams) | no |
| prepare | `MixFormat.prepare_events` | document, bank, options | `PlaybackPlan` | yes |
| render | `Mixer` | plan, block range | int16 PCM | no |
| output | `AudioOutput` | PCM block | device | no |

`MixPlayer.load` runs detect, parse, collect, decode, and prepare, and returns
a `PlaybackSession`. `MixPlayer.play` renders the session; `MixPlayer.show`
prints it.

Decoding is lazy and incremental. The decode stage reads each sample header
to learn its declared frame count and hands out a `SampleStream`; while the
mix plays, the mixer asks the stream for block-sized windows, and the stream
decodes only those frames. Decoded frames are kept, so a long sample is
decoded once and every later window onto it is a slice of that cache; the
decoder and the sample's source bytes are released as soon as the whole
sample has been decoded. Loading and listing therefore never decode audio.

## 3. Data model

### `MixDocument`

The neutral parse result.

| field | meaning |
|---|---|
| `source` | file path |
| `format_name` | plugin name |
| `title` | stored title or file name |
| `tempo_bpm` | stored tempo, or `None` |
| `placements` | `Placement` list for listings and simple formats |
| `payload` | raw format-specific data for the event builder |
| `metadata` | small facts for listings and debugging |

`payload` is deliberately untyped at the common level. Rave stores a
`RaveGrid`; Dance stores a `DanceGrid`; Techno stores a `TechnoMixData`.
The format's own event builder casts it back.

### `Placement`

One sample cell as stored by the file: `track`, 1-based `bar`, `sample_id`,
optional `span` in bars, optional `layer`, and a `parameters` mapping. It is
not yet timed in output frames.

### `SampleRef`

Where a sample lives: a standalone `path`, or `archive` + `offset` + `size`.
It also carries `name`, `label`, `bars`, and format extras. The common decoder
understands both locations.

### `SampleCollection` / `SampleBank`

`SampleCollection` holds references plus non-fatal resolution errors.
`SampleBank` holds one `SampleStream` per usable reference, plus labels and
errors. A stream knows its declared frame count before it holds any PCM; the
mixer pulls decoded windows from it as playback advances. Both keep errors
so `--strict` can fail after the whole stage, while normal playback can skip
bad samples.

### `PlaybackEvent`

One audible placement already positioned in output frames.

| field | meaning |
|---|---|
| `start`, `end` | output frame range |
| `pcm` | decoded sample or a `SampleStream` |
| `left_gain`, `right_gain` | per-channel gain |
| `loop` | repeat PCM to fill the range |
| `label` | display name |
| `parameters` | format extras for listings |

`end` is the last frame the event may sound on. It is not always
`start + len(pcm)`: Rave cuts an earlier sample when the final record starts,
Dance cuts a ringing sample when the next sample starts on its track, and a
looping run ends before its PCM does.

### `PlaybackPlan`

The complete common input: events, `total_frames`, `channels` (1 or 2),
`format_name`, `title`, `sample_rate`, and `details`.

## 4. Class responsibilities

| class | responsibility |
|---|---|
| `MixRegistry` | ordered formats; header detection; lookup by `--format` |
| `MixFormat` | the three format-specific stages and optional CLI/listing hooks |
| `MixDocument` | neutral parse result |
| `Placement` | one stored sample cell |
| `SampleRef` | where one sample lives |
| `SampleCollection` | resolved references + errors |
| `SampleDecoder` | choose `PxdDecoder` or `RiffDecoder`; read headers; hand out lazy streams |
| `PxdDecoder` | `tPxd` header length and DPCM/code-book decoder |
| `RiffDecoder` | WAVE header length and PCM decoder with the engine's mono/rate rules |
| `SampleStream` | one mono sample decoded in playback windows |
| `StreamSource` | one reference's bytes, loaded once and read sequentially from memory |
| `PxdStreamDecoder` | incremental `tPxd` DPCM decoder |
| `RiffStreamDecoder` | incremental PCM WAVE decoder |
| `SampleBank` | sample streams + labels + errors |
| `PlaybackEvent` | one positioned, gain-adjusted sample |
| `PlaybackPlan` | complete render description |
| `PlaybackSession` | document + samples + plan + warnings |
| `Mixer` | block rendering, summing, clipping, looping |
| `AudioOutput` | lazy `sounddevice.RawOutputStream` wrapper |
| `MixPlayer` | orchestration, summaries, warnings, status codes |

## 5. Error model

```
MixError
├── FormatError     parse/detection failed
├── SampleError     collection or decoding failed
└── PlaybackError   device or write failed
```

Formats raise `FormatError` for a bad container and `SampleError` for an
unusable index or archive. The decoder raises `SampleError` for an unknown or
truncated sample stream. `MixPlayer` turns all of them into a message and a
non-zero status; library callers can catch `MixError`.

Non-fatal sample problems are collected as strings. Without `--strict`, they
are reported and the affected samples are skipped; with `--strict`,
`MixPlayer.load` raises `SampleError` when a sample's header is unusable. A
stream that only fails once it is decoded is reported during playback and
treated as silence.

## 6. Playback rules

The common mixer applies what the event builder decided:

* **Mono** (`channels == 1`) sums all events and clips the total to
  -32768..32767 once per output frame.
* **Stereo** (`channels == 2`) sums interleaved left/right values with the
  event's per-channel gains, then clips each channel once.
* Clipping happens after summation, not after every addition, so a mix of
  loud tracks does not depend on event order.
* **One-shot** (`loop == False`) plays `pcm` once; a frame range longer than
  the PCM stays silent after it ends.
* **Loop** (`loop == True`) repeats `pcm` until `end`.
* A `SampleStream` decodes the frames of each rendered block. Decoding
  therefore happens while the mix plays, not during load, and the stream
  keeps every frame it has decoded.
* One stream is shared by all events that play the same sample id, so
  windows arrive at unrelated positions. A window that moves backwards (a
  loop wrap, a repeated hit, the same loop on two tracks) is served from the
  cache and never restarts the decoder; only a window beyond the decoded
  prefix extends it. Loops stay sample-exact and cost one decode per sample.
* Blocks are rendered in increasing, contiguous ranges. `on_start` fires when
  an event enters the active set. `--verbose` passes that event to
  `EventPrinter.announce`, which formats the line and a worker thread writes
  it, so the loop never waits for the console between `mix()` and `write()`.
  Lines are drained before the final status is printed, so the output order is
  the playback order.
* During real playback, `Space` pauses or resumes between blocks and `Esc`
  stops before the next block. Key polling is limited to an interactive
  console, so library callers and tests are unaffected.
* The player times sample collection/header scanning and audio initialization
  and prints both unless `quiet` is set.

Rave-specific decisions (run collapse, repeat-to-fill, cut at the final
record, ring-out) live in `RaveEventBuilder`, not in the mixer. Dance-specific
decisions (per-track run collapse, repeat-to-fill, cut at the next track start,
ring-out) live in `DanceEventBuilder`. Techno-specific decisions (one-shot
placement, per-track pan) live in `TechnoEventBuilder`.

## 7. Options flow

`MixPlayer` accepts a plain mapping:

```python
{
    "format": "rave",          # optional; detection when absent
    "pxd": "...",              # folder holding the samples or the archive
    "index": None,             # explicit sample index file
    "bpm": 180.0,              # common tempo override
    "list": False,
    "strict": False,
    "device": None,
    "block": 2048,
    "gain": 1.0,
    "quiet": False,
    "verbose": False,
    "formats": {
        "rave": {"beats": 8, "step": None},
    },
}
```

`pxd`, `index` and `bpm` are common keys at the top level because every
format resolves samples the same way. `MixFormat.format_options` returns the
plugin's own slice. The CLI builds the same mapping from argparse namespaces,
so library and command-line behaviour cannot drift.

## 8. Extension points

* **New container** — subclass `MixFormat`, implement `matches`, `parse`,
  `collect_samples`, `prepare_events`, optionally `add_arguments`, `options`,
  and `describe`; register it in a `MixRegistry`.
* **New sample codec** — add a decoder and teach `SampleDecoder.decode_bytes`
  the magic. Mix formats do not change.
* **New output** — pass any object with `write(samples)` to `MixPlayer.play`.
* **New CLI flag** — add it in the format's `add_arguments` and return it from
  `options`. Common flags stay in `cli.build_parser`.

The common files must stay free of format names. If a change needs a format
check in `Mixer`, `MixPlayer`, or `MixRegistry`, the rule belongs in that
format's event builder instead.
