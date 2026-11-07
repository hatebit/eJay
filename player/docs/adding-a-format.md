# Adding a mix format

A new format is a `MixFormat` subclass plus a small package under
`player/formats/`. It implements three stages and registers itself. The
mixer, the player, and the common CLI stay untouched.

## 1. Create the format package

Keep the one-file-per-class rule used by the rest of the package:

```
player/formats/myformat/
├── __init__.py
├── my_mix_format.py        MyMixFormat
├── my_mix_data.py          MyMixData        (optional raw parse result)
├── my_sample_collector.py  MySampleCollector
└── my_event_builder.py     MyEventBuilder
```

## 2. Implement the three stages

```python
from pathlib import Path
from typing import Any, Mapping

from ...mix_document import MixDocument
from ...mix_format import MixFormat
from ...placement import Placement
from ...playback_event import PlaybackEvent
from ...playback_plan import PlaybackPlan
from ...pxd.sample_bank import SampleBank
from ...pxd.sample_collection import SampleCollection
from ...pxd.sample_ref import SampleRef


class MyMixFormat(MixFormat):
    name = "myformat"

    def matches(self, header: bytes) -> bool:
        return header.startswith(b"MYMX")

    def parse(self, path: Path,
              options: Mapping[str, Any]) -> MixDocument:
        data = path.read_bytes()
        placements = [
            Placement(track=track, bar=bar, sample_id=sample_id)
            for track, bar, sample_id in read_my_table(data)
        ]
        return MixDocument(
            source=path,
            format_name=self.name,
            title=path.name,
            placements=placements,
            payload=data,
        )

    def collect_samples(self, document: MixDocument,
                        options: Mapping[str, Any]) -> SampleCollection:
        collection = SampleCollection()
        index = read_my_index(options.get("index"))
        for placement in document.placements:
            ref = index.get(placement.sample_id)
            if ref is None:
                collection.errors.append(
                    f"sample {placement.sample_id}: not found")
            else:
                collection.add(ref)
        return collection

    def prepare_events(self, document: MixDocument, samples: SampleBank,
                       options: Mapping[str, Any]) -> PlaybackPlan:
        bpm = float(options.get("bpm") or document.tempo_bpm or 120.0)
        frames_per_bar = 60.0 / bpm * 4.0 * 44100
        events = []
        for placement in document.placements:
            pcm = samples.get(placement.sample_id)
            if not pcm:
                continue
            start = int(round((placement.bar - 1.0) * frames_per_bar))
            events.append(PlaybackEvent(
                start=start,
                end=start + len(pcm),
                pcm=pcm,
                sample_id=placement.sample_id,
                track=placement.track,
                label=samples.label_for(placement.sample_id),
            ))
        total = max((event.end for event in events), default=0)
        return PlaybackPlan(
            events=events,
            total_frames=total,
            channels=2,
            format_name=self.name,
            title=document.title,
            details={"bpm": bpm},
        )
```

`parse` should raise `FormatError` for a bad container. `collect_samples`
should raise `SampleError` when the index or archive itself is unusable, and
record per-sample problems in `collection.errors` so `--strict` and normal
skip-and-continue both work.

## 3. Reuse the common decoder

Do not write a sample decoder in a format. Point a `SampleRef` at either a
standalone file or an archive slice:

```python
SampleRef(sample_id=7, label="kick", path=Path("samples/kick.pxd"))
SampleRef(sample_id=8, label="snare",
          archive=Path("BANK"), offset=0x120, size=4096)
```

`SampleDecoder` chooses `PxdDecoder` or `RiffDecoder` by magic, reads the
header to learn the declared length, and returns a `SampleStream`. Keep that
stream in the event: `len(pcm)` works before the PCM is decoded, and the
mixer pulls block-sized windows from it while the event plays. A genuinely new codec is a new decoder plus
one branch in `SampleDecoder.decode_bytes` and one in `length_bytes`; the
format still does not change.

## 4. Contribute CLI options

Common flags (`--pxd`, `--index`, `--bpm`, `--list`, `--strict`, `--device`,
`--block`, `--gain`, `--quiet`, `--verbose`, `--format`) already exist. Read
`options["pxd"]` for the folder holding the sample data and
`options["index"]` for the index file; both live at the top level, like
`bpm`.

Add only format-specific flags, with names that do not collide with another
format:

```python
def add_arguments(self, parser):
    parser.add_argument("--my-unit", type=float, default=1.0,
                        help="timing unit")

def options(self, namespace):
    return {"unit": namespace.my_unit}
```

`MixPlayer` stores the result under `options["formats"]["myformat"]`.
`self.format_options(options)` retrieves it. A format with no extra flags can
leave both methods out entirely.

Optionally override `describe` to control the `--list` table.

## 5. Register the format

For a third-party format, register it explicitly:

```python
from player import MixPlayer, MixRegistry
from myformat.my_mix_format import MyMixFormat

registry = MixRegistry()
registry.register(MyMixFormat())
player = MixPlayer(registry)
```

To ship it with the player, add it to `MixRegistry.default()` in
`player/mix_registry.py`:

```python
from .formats.dance.dance_mix_format import DanceMixFormat
from .formats.hiphop.hiphop_mix_format import HiphopMixFormat
from .formats.myformat.my_mix_format import MyMixFormat
from .formats.rave.rave_mix_format import RaveMixFormat
from .formats.techno.techno_mix_format import TechnoMixFormat

registry = cls()
registry.register(DanceMixFormat())
registry.register(HiphopMixFormat())
registry.register(RaveMixFormat())
registry.register(TechnoMixFormat())
registry.register(MyMixFormat())
```

Registration order is detection order. Put the most specific `matches`
implementation first.

## 6. Test the plugin

Add tests to `test_mix_player.py` or a sibling test module. Cover at least:

* detection of the magic and rejection of a bad header;
* parsing a synthetic container, including both entry variants if it has any;
* sample collection from the format's real index shape, plus a missing id;
* event timing at a deliberately small bar/record length, so the test stays
  fast;
* channel count and pan/gain values;
* `--list` output;
* `--strict` behaviour for a missing sample.

Use a fake output object instead of a device:

```python
class Recorder:
    def __init__(self):
        self.samples = []
    def write(self, samples):
        self.samples.extend(samples)
    def close(self):
        pass
```

## 7. Checklist

- [ ] `name` is short, stable, and unique.
- [ ] `version` follows semantic versioning: `1.0.0` for a new format, a
      MAJOR bump when callers of the format must change (options it reads,
      its CLI flags, its payload type), MINOR for a newly supported mix or
      sample variant, PATCH for a fix that keeps both.
- [ ] `matches` reads only the bytes the registry provides (32).
- [ ] `parse` raises `FormatError`, never a bare `Exception`.
- [ ] `parse` fills `placements` for listings and `payload` for the builder.
- [ ] `collect_samples` uses `SampleRef`, not format-specific decoding.
- [ ] `collect_samples` records per-sample errors instead of failing the run.
- [ ] `prepare_events` decides looping, cutting, and panning; the mixer does
      not know the format.
- [ ] `channels` is 1 or 2.
- [ ] `total_frames` includes ring-out and run length, not just the last
      event's PCM end.
- [ ] CLI flags do not collide with existing formats.
- [ ] The format is registered and tested.
- [ ] `python -m player.test_mix_player` passes.
- [ ] Format notes are added under [`../../docs/formats/`](../../docs/formats/)
      if the container was newly
      reverse-engineered.
