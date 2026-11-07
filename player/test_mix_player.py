"""Verification for the extensible mix player.

Run from the repository root::

    python -m player.test_mix_player
"""

from __future__ import annotations

import array
import contextlib
import io
import struct
import tempfile
import threading
import time
from pathlib import Path

from player import (
    AudioOutput,
    FormatError,
    MixDocument,
    MixError,
    MixFormat,
    MixPlayer,
    MixRegistry,
    Mixer,
    Placement,
    PlaybackEvent,
    PlaybackPlan,
    SampleCollection,
    SampleDecoder,
    SampleError,
)
from player.cli import main as cli_main
from player.event_printer import EventPrinter
from player.pxd.pxd_decoder import PxdDecoder
from player.pxd.pxd_stream_decoder import PxdStreamDecoder
from player.pxd.riff_decoder import RiffDecoder
from player.pxd.riff_stream_decoder import RiffStreamDecoder
from player.pxd.sample_ref import SampleRef
from player.pxd.stream_source import StreamSource

SAMPLE = [0, 2, 2, 4, 8]
RAVE_RECORD_WORDS = 16
TECHNO_MAGIC = 0x0889
DANCE_MAGIC = 0x0A06
DANCE_BLOCKS = 351
HIPHOP_MAGIC = 0x0A08
HIPHOP_BLOCKS = 351
HIPHOP_PAD = "zz\\pad.pxd"


def make_tp_bytes(frames: int = len(SAMPLE)) -> bytes:
    """Return the synthetic ``tPxd`` stream that decodes to ``SAMPLE``."""
    payload = bytes([0xF5, 0x01, 0x80, 0x81, 0x01, 0xFF, 0x82, 0x01])
    header = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
              + struct.pack("<i", frames) + b"\0\0")
    return header + payload + bytes(300)


def make_riff_bytes(samples, rate: int = 44100, channels: int = 1,
                    bits: int = 16) -> bytes:
    """Return a minimal PCM WAVE stream from interleaved integers."""
    if bits == 8:
        payload = bytes(value & 0xFF for value in samples)
    else:
        payload = struct.pack("<%dh" % len(samples), *samples)
    align = channels * (bits // 8)
    return (b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate,
                                    rate * align, align, bits)
            + b"data" + struct.pack("<I", len(payload)) + payload)


def make_rave_mix(path: Path, records, version="Rave eJay 1.01") -> Path:
    """Write a Rave grid, header, and trailer."""
    blob = struct.pack("<H", 0x0A07)
    for record in records:
        assert len(record) == RAVE_RECORD_WORDS
        blob += struct.pack("<16H", *record)
    blob += struct.pack("<H", 0x0A08)
    blob += struct.pack("<H", 1)
    blob += struct.pack("<H", 16)
    blob += version.encode("latin-1")[:15] + b"\0"
    blob += bytes(20)
    path.write_bytes(blob)
    return path


def make_rave_res(tmp: Path, rows=None, sample=None) -> Path:
    """Build a minimal Rave resource folder with one sample and an index."""
    res = tmp / "rave_res"
    sample_path = res / "bq" / "r1bs001.pxd"
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_bytes(sample if sample is not None
                            else make_tp_bytes())
    (res / "EJAY").mkdir(parents=True, exist_ok=True)

    if rows is None:
        rows = [("bq\\r1bs001.pxd", "bass", "2", "just walking", "1")]
    lines = []
    for relative, category, number, name, second in rows:
        lines += [f'"{relative}"', '""', f'"{category}"', f'"{number}"',
                  f'"{name}"', f'"{second}"']
    (res / "EJAY" / "PXD").write_bytes(
        ("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return res


def row(**cells) -> list[int]:
    """Build a Rave record from ``t1=id`` / ``b1=id`` keyword arguments."""
    out = [0] * RAVE_RECORD_WORDS
    for key, value in cells.items():
        offset = RAVE_RECORD_WORDS // 2 if key[0] == "b" else 0
        out[int(key[1:]) - 1 + offset] = value
    return out


def dance_block(bar1=(), bar2=()) -> list[int]:
    """Build a Dance block from two lists of ``(track, id)`` pairs."""
    out = [0] * 16
    for track, sample_id in bar1:
        out[track - 1] = sample_id
    for track, sample_id in bar2:
        out[8 + track - 1] = sample_id
    return out


def make_dance_mix(path: Path, blocks) -> Path:
    """Write a Dance grid with zeroed trailing blocks."""
    assert len(blocks) <= DANCE_BLOCKS
    blob = struct.pack("<H", DANCE_MAGIC)
    for block in blocks:
        assert len(block) == 16
        blob += struct.pack("<16H", *block)
    blob += bytes(32 * (DANCE_BLOCKS - len(blocks)))
    path.write_bytes(blob)
    return path


def make_dance_res(tmp: Path, entries) -> Path:
    """Build a minimal Dance resource folder and its two text indexes."""
    res = tmp / "dance_res"
    dm = res / "DMACHINE"
    dm.mkdir(parents=True, exist_ok=True)

    samples = []
    for index, entry in enumerate(entries):
        sample = {"path_index": index, **entry}
        samples.append(sample)
        relative = sample["relative"].replace("\\", "/")
        sample_path = res / relative
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(make_tp_bytes(sample.get("frames", 5)))

    path_count = max(item["path_index"] for item in samples) + 1
    paths = ['""'] * path_count
    by_id = {item["id"]: item for item in samples}
    for item in samples:
        paths[item["path_index"]] = f'"{item["relative"]}"'

    count = max(by_id) - 731 + 1
    records = []
    for position in range(count):
        item = by_id.get(731 + position)
        if item is None:
            records += ['"3"', '"1"', '""', '""']
        else:
            records += [f'"{3 + item["path_index"]}"',
                        f'"{item.get("bars", 1)}"',
                        f'"{item.get("name", "")}"',
                        f'"{item.get("part", "")}"']
    header = ['"0"'] + ['"0"'] * 17
    (dm / "PXD.TXT").write_bytes(
        ("\r\n".join(header + records) + "\r\n").encode("latin-1"))
    (dm / "MAX.TXT").write_bytes(
        ("\r\n".join(paths) + "\r\n").encode("latin-1"))
    return res


DANCE_BANK_LAYOUT = (
    (3400, 1352, 423),
    (3900, 1775, 520),
    (4500, 2295, 550),
)


def make_dance_new_res(tmp: Path, entries, bank_samples=None) -> Path:
    """Build a ``DANCE`` folder with ``EJAY/PXDDANCE`` and a raw ``MAX``."""
    res = tmp / "dance_new"
    ejay = res / "EJAY"
    ejay.mkdir(parents=True, exist_ok=True)

    by_id = {}
    for index, entry in enumerate(entries):
        sample = {"id": 731 + index, "bars": 1, **entry}
        sample_path = res / sample["relative"].replace("\\", "/")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(make_tp_bytes(sample.get("frames", 5)))
        by_id[sample["id"]] = sample

    paths: dict[int, str] = {}
    for sample_id, relative in (bank_samples or {}).items():
        for base, start, count in DANCE_BANK_LAYOUT:
            if base <= sample_id < base + count:
                paths[start + sample_id - base] = relative
                break
        else:
            raise AssertionError(f"{sample_id} is not in a high-ID bank")
        sample_path = res / relative.replace("\\", "/")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(make_tp_bytes())

    path_count = max(paths) + 1 if paths else 1
    path_lines = ["unused\\pad.pxd"] * path_count
    for path_index, relative in paths.items():
        path_lines[path_index] = relative

    count = max(by_id) - 731 + 1
    records = []
    for position in range(count):
        sample = by_id.get(731 + position, entries[0] | {"name": ""})
        records += [
            f'"{sample["relative"]}"',
            '""',
            '"loop"',
            f'"{sample.get("bars", 1)}"',
            f'"{sample.get("name", "")}"',
            f'"{sample.get("part", "")}"',
        ]
    (ejay / "PXDDANCE").write_bytes(
        ("\r\n".join(records) + "\r\n").encode("latin-1"))
    (ejay / "MAX").write_bytes(
        ("\r\n".join(path_lines) + "\r\n").encode("latin-1"))
    return res


def make_techno_mix(path: Path, entries, bpm: int = 140,
                    title: str = "Test Mix") -> Path:
    """Write a Techno header, text block, event table, and footer."""
    blob = struct.pack("<8H", TECHNO_MAGIC, 0, 0, 0, bpm, 0, 0, 0)
    blob += title.encode("latin-1") + b"\0"
    blob += b"#SKKENNUNG#:0000000\0"
    blob += b"\x01" + struct.pack("<H", 0) + b"\0"
    blob += b"\x01\x00\x00"
    blob += bytes(2)                      # compact grid placeholder
    blob += b">?~>" + b"\x38\x05\x00\x00"

    for track in range(1, 18):
        track_entries = entries.get(track, [])
        blob += struct.pack("<BI", track, len(track_entries))
        for bar, sample_id, long_form in track_entries:
            units = int(round((bar - 1.0) * 128.0))
            if long_form:
                blob += struct.pack("<BhhH", 0, units, 0, sample_id)
                blob += bytes(10)
            else:
                blob += struct.pack("<BhhH", 0, -(units + 1), -1, sample_id)
    blob += b"\xa9\x7a\x8a\x01"
    path.write_bytes(blob)
    return path


def make_techno_res(tmp: Path, samples) -> Path:
    """Build ``RAVE20.INF`` and a ``RAVE20`` archive from sample streams."""
    res = tmp / "techno_res"
    res.mkdir(parents=True, exist_ok=True)
    archive = bytearray()
    lines = ["[SAMPLES]"]
    for sample_id, name, stream, bars in samples:
        offset = len(archive)
        archive += stream
        lines += [
            str(sample_id),
            "0",
            f'"{name}"',
            str(offset),
            str(len(stream)),
            '"test"',
            '"part"',
            "0",
            str(bars),
            "0",
            "0",
            "0",
        ]
    inf_path = res / "RAVE20.INF"
    inf_path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    archive_path = res / "RAVE20"
    archive_path.write_bytes(bytes(archive))
    return res


DANCE2_MAGIC = 0x0A19
DANCE2_FOOTER = b"\xa9\x7a\x8a\x01"


def make_dance2_mix(path: Path, *, title: str = "MC Test",
                    description: str = "Test Mix", settings=None,
                    sample_events=(), text_events=(), bpm: int = 140
                    ) -> Path:
    """Write a Dance eJay 2.0 container.

    ``sample_events`` rows are ``(track, units, sample_id, long_form)``;
    ``text_events`` rows are ``(units, name, value)``.
    """
    blob = struct.pack("<8H", DANCE2_MAGIC, 0, 0, 0, bpm, 140, 0, 0)
    blob += title.encode("latin-1") + b"\0"
    blob += b"#SKKENNUNG#:0000000\0"
    desc = description.encode("latin-1") + b"\0\1"
    blob += b"\1" + struct.pack("<H", len(desc)) + desc
    pairs = settings or [(0, 32767)] * 16
    assert len(pairs) == 16
    for pan, volume in pairs:
        blob += struct.pack("<2H", pan, volume)
    blob += bytes(8)

    catalog = b"Dance eJay 2.0\0\1"
    blob += struct.pack("<H", 0)
    blob += struct.pack("<H", len(catalog)) + catalog
    blob += struct.pack("<HII", 9, 2000, 3399)
    kits = [(b"Test Kit\0\1", 3400, 3499)]
    kits += [(b"\0\1", 0, 0)] * 8
    for name, first, last in kits:
        blob += struct.pack("<H", len(name)) + name
        blob += struct.pack("<II", first, last)

    blob += struct.pack("<I", 0x01000002)
    entry = b"kick\0\1"
    blob += struct.pack("<IHH", 0x01000002, 1, len(entry)) + entry
    blob += struct.pack("<II", 0, 0)
    blob += bytes(range(22))

    for track in range(1, 17):
        rows = [row for row in sample_events if row[0] == track]
        blob += struct.pack("<BI", track, len(rows))
        for _, units, sample_id, long_form in rows:
            if long_form:
                blob += struct.pack("<BhhH", 0, units, 0, sample_id)
                blob += bytes(10)
            else:
                blob += struct.pack("<BhhH", 0, -(units + 1), -1, sample_id)
    blob += struct.pack("<BI", 17, len(text_events))
    for units, name, value in text_events:
        blob += struct.pack("<Bhh", 2, -(units + 1), -1) + bytes(22)
        name_bytes = name.encode("latin-1") + b"\0\1"
        value_bytes = value.encode("latin-1") + b"\0\1"
        blob += struct.pack("<H", len(name_bytes)) + name_bytes
        blob += struct.pack("<H", len(value_bytes)) + value_bytes
    blob += DANCE2_FOOTER
    path.write_bytes(blob)
    return path


def make_dance2_res(tmp: Path, samples, add_ons=None) -> Path:
    """Build ``DANCE20.INF``/``DANCE20`` plus optional add-on kits."""
    res = tmp / "dance2_res"
    res.mkdir(parents=True, exist_ok=True)
    _write_dance2_archive(res, "DANCE20", samples)
    for stem, rows in (add_ons or {}).items():
        _write_dance2_archive(res, stem, rows)
    return res


def _write_dance2_archive(root: Path, stem: str, samples) -> None:
    """Write one ``stem.INF`` index and its ``stem`` archive."""
    archive = bytearray()
    lines = ["[SAMPLES]"]
    for sample_id, name, stream, bars in samples:
        offset = len(archive)
        archive += stream
        lines += [
            str(sample_id),
            "0",
            f'"{name}"',
            str(offset),
            str(len(stream)),
            '"test"',
            '"part"',
            "0",
            str(bars),
            "0",
            "0",
            "0",
        ]
    (root / f"{stem}.INF").write_text(
        "\n".join(lines) + "\n", encoding="latin-1")
    (root / stem).write_bytes(bytes(archive))


def rave_options(res: Path, **extra):
    return {"pxd": str(res), "formats": {"rave": extra}}


def techno_options(res: Path, **extra):
    return {
        "bpm": extra.pop("bpm", None),
        "pxd": str(res),
        "formats": {"techno": extra},
    }


def dance_options(res: Path, **extra):
    return {
        "bpm": extra.pop("bpm", None),
        "pxd": str(res),
        "formats": {"dance": extra},
    }


def hiphop_block(bar1=(), bar2=()) -> list[int]:
    """Build a Hiphop block from two lists of ``(track, id)`` pairs."""
    out = [0] * 16
    for track, sample_id in bar1:
        out[track - 1] = sample_id
    for track, sample_id in bar2:
        out[8 + track - 1] = sample_id
    return out


def make_hiphop_mix(path: Path, blocks) -> Path:
    """Write a Hiphop grid, metadata block, and trailer."""
    assert len(blocks) <= HIPHOP_BLOCKS
    blob = struct.pack("<H", HIPHOP_MAGIC)
    for block in blocks:
        assert len(block) == 16
        blob += struct.pack("<16H", *block)
    blob += bytes(32 * (HIPHOP_BLOCKS - len(blocks)))
    blob += struct.pack("<HHH", HIPHOP_MAGIC, 1, 18)
    blob += b"HipHop eJay 1.01\x00\x01"
    blob += bytes(400)
    path.write_bytes(blob)
    return path


def make_hiphop_res(tmp: Path, entries) -> Path:
    """Build a ``HIPHOP`` folder with ``EJAY/PXD`` and sample files."""
    res = tmp / "HIPHOP"
    ejay = res / "EJAY"
    ejay.mkdir(parents=True, exist_ok=True)

    by_id = {}
    for index, entry in enumerate(entries):
        sample = {"id": 731 + index, **entry}
        disk = sample.get("disk", sample["relative"])
        sample_path = res / disk.replace("\\", "/")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(make_tp_bytes(sample.get("frames", 5)))
        by_id[sample["id"]] = sample

    pad = res / HIPHOP_PAD.replace("\\", "/")
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_bytes(make_tp_bytes())

    count = max(by_id) - 731 + 1
    records = []
    for position in range(count):
        sample = by_id.get(731 + position, {})
        relative = sample.get("relative", HIPHOP_PAD)
        bars = str(sample.get("bars", 1))
        name = sample.get("name", "")
        part = sample.get("part", "")
        records += [
            f'"{relative}"',
            '""',
            '"loop"',
            f'"{bars}"',
            f'"{name}"',
            f'"{part}"',
        ]
    (ejay / "PXD").write_bytes(
        ("\r\n".join(records) + "\r\n").encode("latin-1"))
    return res


def hiphop_options(res: Path, **extra):
    return {
        "bpm": extra.pop("bpm", None),
        "pxd": str(res),
        "formats": {"hiphop": extra},
    }


class FakeStream:
    """Minimal ``sounddevice`` stream double for pause/resume tests."""

    def __init__(self) -> None:
        self.started = False
        self.stops = 0
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False
        self.stops += 1

    def close(self) -> None:
        self.closed = True


class BlockingStream:
    """Text stream whose writes stall until the test releases them."""

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.writing = threading.Event()
        self.release = threading.Event()

    def write(self, text: str) -> int:
        self.chunks.append(text)
        self.writing.set()
        self.release.wait(2.0)
        return len(text)

    def flush(self) -> None:
        pass


class Recorder:
    """Stand-in output that keeps every sample it is given."""

    def __init__(self) -> None:
        self.samples: list[int] = []
        self.writes = 0

    def write(self, samples) -> None:
        self.samples.extend(samples)
        self.writes += 1

    def close(self) -> None:
        pass


class DummyFormat(MixFormat):
    """A minimal third-party format used to prove the extension point."""

    name = "dummy"

    def matches(self, header: bytes) -> bool:
        return header.startswith(b"DUMM")

    def parse(self, path: Path, options) -> MixDocument:
        return MixDocument(
            source=path,
            format_name=self.name,
            title="Dummy",
            placements=[Placement(track=1, bar=1.0, sample_id=1)],
        )

    def collect_samples(self, document, options) -> SampleCollection:
        return SampleCollection()

    def prepare_events(self, document, samples, options) -> PlaybackPlan:
        return PlaybackPlan(
            events=[], total_frames=0, channels=1, format_name=self.name)


class CountingDecoder(SampleDecoder):
    """A decoder that counts how many streams it opens."""

    def __init__(self) -> None:
        super().__init__()
        self.opened = 0

    def open_stream(self, ref, frames):
        self.opened += 1
        return super().open_stream(ref, frames)


def test_registry_detects_builtin_formats(tmp: Path):
    rave = make_rave_mix(tmp / "one.mix", [row(t1=731)])
    techno = make_techno_mix(tmp / "two.mix", {1: [(1.0, 100, False)]})
    dance = make_dance_mix(
        tmp / "three.mix", [dance_block(bar1=[(1, 731)])])
    dance2 = make_dance2_mix(
        tmp / "four.mix", sample_events=[(1, 0, 1, False)])
    registry = MixRegistry.default()
    assert registry.detect(rave).name == "rave"
    assert registry.detect(techno).name == "techno"
    assert registry.detect(dance).name == "dance"
    assert registry.detect(dance2).name == "dance2"
    unknown = tmp / "unknown.mix"
    unknown.write_bytes(b"nope" * 16)
    try:
        registry.detect(unknown)
    except FormatError:
        pass
    else:
        raise AssertionError("an unknown header must be rejected")


def test_rave_pipeline(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "grid.mix",
                        [row(t1=731), row(t1=731), row(t2=731)])
    player = MixPlayer()
    session = player.load(mix, rave_options(res, step=3 / 44100.0))
    assert session.mix_format.name == "rave"
    assert session.document.duration_bars == 6.0
    assert session.plan.channels == 1
    assert len(session.plan.events) == 2
    assert session.plan.events[0].start == 0
    assert session.plan.events[0].end == 6
    assert session.plan.events[0].loop is True
    # the first run loops for six frames; the last sample rings out to eleven
    assert session.plan.total_frames == 11
    assert session.sample_seconds >= 0.0
    assert session.load_seconds >= session.sample_seconds


def test_rave_playback_mono(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "play.mix",
                        [row(t1=731), row(), row(t2=731)])
    output = Recorder()
    status = MixPlayer().play(
        mix, {**rave_options(res, step=30 / 44100.0), "quiet": True,
              "block": 64},
        output=output)
    assert status == 0
    assert output.writes > 1
    assert output.samples[:5] == SAMPLE
    assert output.samples[5:60] == [0] * 55
    assert output.samples[60:65] == SAMPLE


def test_rave_one_shot_and_final_ring_out(tmp: Path):
    res = make_rave_res(tmp)

    one_shot = make_rave_mix(tmp / "shot.mix", [row(t1=731)])
    output = Recorder()
    assert MixPlayer().play(
        one_shot, {**rave_options(res, step=10 / 44100.0), "quiet": True},
        output=output) == 0
    assert output.samples[:5] == SAMPLE
    assert output.samples[5:] == [0] * 5

    final = make_rave_mix(tmp / "final.mix", [row(t1=731)])
    output = Recorder()
    assert MixPlayer().play(
        final, {**rave_options(res, step=2 / 44100.0), "quiet": True},
        output=output) == 0
    assert output.samples == SAMPLE


def test_rave_missing_sample_strict(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "missing.mix", [row(t1=999)])
    session = MixPlayer().load(mix, rave_options(res))
    assert session.warnings
    assert session.plan.events == []
    try:
        MixPlayer().load(mix, {**rave_options(res), "strict": True})
    except SampleError:
        pass
    else:
        raise AssertionError("--strict must fail on a missing sample")


def test_rave_list(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "list.mix", [row(t1=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = MixPlayer().play(mix, {**rave_options(res, step=0.01),
                                        "list": True})
    assert status == 0
    text = out.getvalue()
    assert "Rave eJay 1.01" in text
    assert "T1 A" in text
    assert "just walking" in text
    assert "loaded 1 samples in" in text


def test_samples_decode_on_demand(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "lazy.mix", [row(t1=731)])
    player = MixPlayer()
    session = player.load(mix, rave_options(res, step=10 / 44100.0))

    stream = session.samples.get(731)
    assert stream is not None
    assert not stream.decoded
    assert stream.decoded_frames == 0
    assert len(stream) == len(SAMPLE)

    mixer = Mixer(session.plan)
    mixer.mix(0, len(SAMPLE))
    assert stream.decoded
    assert stream.decoded_frames == len(SAMPLE)
    assert list(stream) == SAMPLE
    stream.close()
    replay = Mixer(session.plan).mix(0, len(SAMPLE))
    assert list(replay) == SAMPLE


def test_sample_stream_decodes_in_windows(tmp: Path):
    values = [index % 100 for index in range(6000)]
    res = make_rave_res(tmp, sample=make_riff_bytes(values))
    mix = make_rave_mix(tmp / "window.mix", [row(t1=731)])
    session = MixPlayer().load(
        mix, rave_options(res, step=6000 / 44100.0))

    stream = session.samples.get(731)
    assert stream is not None
    assert stream.decoded_frames == 0

    mixer = Mixer(session.plan)
    mixer.mix(0, 2048)
    assert stream.decoded_frames == 2048
    mixer.mix(2048, 2048)
    assert stream.decoded_frames == 4096
    assert list(stream) == values
    stream.close()


def test_stream_source_reads_slice_in_memory(tmp: Path):
    archive = tmp / "pack.bin"
    archive.write_bytes(b"xx" + b"abcdef" + b"yy")
    source = StreamSource(
        SampleRef(sample_id=1, archive=archive, offset=2, size=6))
    assert source.data == b"abcdef"
    assert source.read(2) == b"ab"
    assert source.read_byte() == ord("c")
    source.seek(5)
    assert source.read(10) == b"f"
    assert source.read(1) == b""
    assert source.read_byte() is None
    source.reset()
    assert source.position == 0
    assert source.read(3) == b"abc"
    source.close()
    assert source.read(2) == b"ab"

    missing = StreamSource(SampleRef(sample_id=2, path=tmp / "nope.pxd"))
    try:
        missing.read(1)
    except SampleError:
        pass
    else:
        raise AssertionError("an unreadable reference must be rejected")


def test_pxd_stream_decoder_matches_full_decoder(tmp: Path):
    data = make_tp_bytes(1000)
    expected = PxdDecoder().decode(data)
    assert list(expected[:5]) == SAMPLE
    path = tmp / "stream.pxd"
    path.write_bytes(data)
    decoder = PxdStreamDecoder(
        StreamSource(SampleRef(sample_id=1, path=path)), 1000)

    for _ in range(2):
        out = array.array("h")
        sizes = (1, 3, 7, 64)
        turn = 0
        while True:
            chunk = decoder.read(sizes[turn % len(sizes)])
            turn += 1
            if not chunk:
                break
            out.extend(chunk)
        assert out == expected
        decoder.reset()


def test_riff_stream_decoder_matches_full_decoder(tmp: Path):
    """The streaming RIFF decoder must match the standalone one exactly."""
    cases = (
        ([index % 200 - 100 for index in range(6000)], 44100, 1, 16),
        ([-32768, -1, 0, 1, 32767], 44100, 2, 16),
        ([100, 200], 22050, 1, 16),
        ([100, 200, 300, 400], 48000, 1, 16),
        ([0, 1, 127, 128, 200, 255], 44100, 2, 8),
        ([0, 128, 255], 44100, 2, 8),
        ([0, 1, 127, 128, 200, 255], 22050, 1, 8),
    )
    sizes = (1, 3, 7, 64, 1024)
    for index, (values, rate, channels, bits) in enumerate(cases):
        data = make_riff_bytes(values, rate=rate, channels=channels,
                               bits=bits)
        full = RiffDecoder()
        expected = full.decode(data)
        frames = full.length(data)
        assert frames == len(expected), (index, frames, len(expected))

        path = tmp / f"riff-stream-{index}.wav"
        path.write_bytes(data)
        decoder = RiffStreamDecoder(
            StreamSource(SampleRef(sample_id=index, path=path)), frames)
        for _ in range(2):
            out = array.array("h")
            turn = 0
            while True:
                chunk = decoder.read(sizes[turn % len(sizes)])
                turn += 1
                if not chunk:
                    break
                out.extend(chunk)
            assert out == expected, (index, len(out), len(expected))
            decoder.reset()
        decoder.close()


def test_sample_stream_serves_backward_windows_from_cache(tmp: Path):
    values = [index % 100 for index in range(6000)]
    res = make_rave_res(tmp, sample=make_riff_bytes(values))
    mix = make_rave_mix(tmp / "back.mix", [row(t1=731)])
    decoder = CountingDecoder()
    session = MixPlayer(decoder=decoder).load(
        mix, rave_options(res, step=6000 / 44100.0))

    stream = session.samples.get(731)
    assert stream is not None
    assert list(stream.window(3000, 100)) == values[3000:3100]
    assert stream.decoded_frames == 3100
    assert list(stream.window(0, 100)) == values[0:100]
    assert stream.decoded_frames == 3100
    assert list(stream.window(5950, 100, True)) == (
        values[5950:] + values[:50])
    assert stream.decoded_frames == 6000
    assert list(stream.window(10, 20, True)) == values[10:30]
    assert decoder.opened == 1
    stream.close()


def test_dance_pipeline_and_key_resolution(tmp: Path):
    res = make_dance_res(tmp, [
        {"id": 731, "path_index": 1, "relative": "AA\\ONE.PXD",
         "name": "one", "bars": 2, "frames": 240},
        {"id": 732, "path_index": 0, "relative": "AB\\TWO.PXD",
         "name": "two", "bars": 1, "frames": 480},
    ])
    mix = make_dance_mix(tmp / "dance.mix", [
        dance_block(bar1=[(1, 731)], bar2=[(1, 731)]),
    ])
    player = MixPlayer()
    session = player.load(mix, dance_options(res, bpm=44100.0))

    assert session.mix_format.name == "dance"
    assert session.document.duration_bars == 2.0
    assert session.plan.channels == 1
    assert len(session.plan.events) == 1
    event = session.plan.events[0]
    assert event.start == 0
    assert event.end == 480
    assert event.loop is True
    assert event.label == "one"
    assert session.plan.total_frames == 480
    assert session.plan.details["bar_frames"] == 240.0
    # The reversed MAX.TXT order proves the key, not the id, picks the file.
    assert len(session.samples.get(731)) == 240

    output = Recorder()
    assert player.play(
        mix, {**dance_options(res, bpm=44100.0), "quiet": True,
              "block": 64},
        output=output) == 0
    assert len(output.samples) == 480
    assert output.samples[:5] == SAMPLE
    assert output.samples[240:245] == SAMPLE


def test_dance_cut_at_next_track_start(tmp: Path):
    res = make_dance_res(tmp, [
        {"id": 731, "relative": "AA\\ONE.PXD", "name": "one",
         "bars": 1, "frames": 240},
        {"id": 732, "relative": "AB\\TWO.PXD", "name": "two",
         "bars": 2, "frames": 480},
    ])
    mix = make_dance_mix(tmp / "cut.mix", [
        dance_block(bar1=[(1, 732)], bar2=[(1, 731)]),
    ])
    session = MixPlayer().load(mix, dance_options(res, bpm=44100.0))

    first, second = session.plan.events
    assert first.sample_id == 732
    assert (first.start, first.end) == (0, 240)
    assert second.sample_id == 731
    assert (second.start, second.end) == (240, 480)
    assert session.plan.total_frames == 480


def test_dance_missing_sample_strict(tmp: Path):
    res = make_dance_res(tmp, [
        {"id": 731, "relative": "AA\\ONE.PXD", "name": "one"},
    ])
    mix = make_dance_mix(tmp / "missing.mix", [
        dance_block(bar1=[(1, 999)]),
    ])
    session = MixPlayer().load(mix, dance_options(res, bpm=44100.0))
    assert session.warnings
    assert session.plan.events == []
    try:
        MixPlayer().load(
            mix, {**dance_options(res, bpm=44100.0), "strict": True})
    except SampleError:
        pass
    else:
        raise AssertionError("--strict must fail on a missing sample")


def test_dance_list_and_cli(tmp: Path):
    res = make_dance_res(tmp, [
        {"id": 731, "relative": "AA\\ONE.PXD", "name": "one"},
    ])
    mix = make_dance_mix(tmp / "list.mix", [
        dance_block(bar1=[(1, 731)]),
    ])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([
            str(mix), "--pxd", str(res), "--list",
            "--bpm", "44100", "--format", "dance",
        ])
    assert status == 0
    text = out.getvalue()
    assert "dance" in text
    assert "351 blocks" in text
    assert "one" in text
    assert "T1" in text


def test_dance_new_catalog_resolution(tmp: Path):
    res = make_dance_new_res(tmp, [
        {"relative": "AA\\ONE.PXD", "name": "one", "bars": 2, "frames": 240},
        {"relative": "AB\\TWO.PXD", "name": "two", "bars": 1, "frames": 480},
    ])
    mix = make_dance_mix(tmp / "new.mix", [
        dance_block(bar1=[(1, 732)]),
    ])
    session = MixPlayer().load(mix, dance_options(res, bpm=44100.0))

    assert session.mix_format.version == "2.0.0"
    assert len(session.plan.events) == 1
    event = session.plan.events[0]
    assert event.sample_id == 732
    assert event.label == "two"
    assert len(session.samples.get(732)) == 480


def test_dance_new_high_id_banks(tmp: Path):
    res = make_dance_new_res(
        tmp,
        [{"relative": "AA\\ONE.PXD", "name": "one"}],
        bank_samples={
            3400: "dm\\rap301.pxd",
            3900: "dm\\bass301.pxd",
            4500: "dm\\d4sp001l.pxd",
        },
    )
    mix = make_dance_mix(tmp / "banks.mix", [
        dance_block(bar1=[(1, 3400), (2, 3900), (3, 4500)]),
    ])
    session = MixPlayer().load(mix, dance_options(res, bpm=44100.0))

    labels = {event.sample_id: event.label for event in session.plan.events}
    assert labels == {
        3400: "rap301",
        3900: "bass301",
        4500: "d4sp001l",
    }
    assert all(event.end - event.start == len(SAMPLE)
               for event in session.plan.events)


def test_dance_metadata_trailer_and_short_file(tmp: Path):
    res = make_dance_new_res(tmp, [
        {"relative": "AA\\ONE.PXD", "name": "one"},
    ])
    mix = make_dance_mix(tmp / "trailer.mix", [
        dance_block(bar1=[(1, 731)]),
    ])
    mix.write_bytes(mix.read_bytes() + bytes(43))
    session = MixPlayer().load(mix, dance_options(res, bpm=44100.0))
    assert session.plan.events[0].label == "one"

    short = tmp / "short.mix"
    short.write_bytes(mix.read_bytes()[:11233])
    try:
        MixPlayer().load(short, dance_options(res, bpm=44100.0))
    except FormatError:
        pass
    else:
        raise AssertionError("a truncated grid must be rejected")


def test_dance_catalog_auto_discovery(tmp: Path):
    res = make_dance_new_res(tmp, [
        {"relative": "AA\\ONE.PXD", "name": "one"},
    ])
    res.rename(tmp / "DANCE")
    mix_dir = tmp / "MIX"
    mix_dir.mkdir()
    mix = make_dance_mix(mix_dir / "auto.mix", [
        dance_block(bar1=[(1, 731)]),
    ])
    session = MixPlayer().load(mix, {"bpm": 44100.0})
    assert session.plan.events[0].label == "one"


def test_hiphop_pipeline_and_run_collapse(tmp: Path):
    res = make_hiphop_res(tmp, [
        {"relative": "AA\\H1BS001.PXD", "disk": "aa/h1bs001.pxd",
         "name": "dirty slurpy", "part": "the one", "bars": 2,
         "frames": 240},
    ])
    mix = make_hiphop_mix(tmp / "hiphop.mix", [
        hiphop_block(bar1=[(1, 731)], bar2=[(1, 731)]),
    ])
    player = MixPlayer()
    session = player.load(mix, hiphop_options(res, bpm=44100.0))

    assert session.mix_format.name == "hiphop"
    assert session.document.duration_bars == 2.0
    assert session.plan.channels == 1
    assert len(session.plan.events) == 1
    event = session.plan.events[0]
    assert (event.start, event.end) == (0, 480)
    assert event.loop is True
    assert event.label == "dirty slurpy the one"
    assert session.plan.details["bar_frames"] == 240.0

    # The shipped default is 96 BPM: the catalog's bar field and the decoded
    # sample lengths are exact multiples of 110,250 frames.
    defaulted = player.load(mix, hiphop_options(res))
    assert defaulted.plan.details["bar_frames"] == 110250.0

    output = Recorder()
    assert player.play(
        mix, {**hiphop_options(res, bpm=44100.0), "quiet": True,
              "block": 64},
        output=output) == 0
    assert len(output.samples) == 480
    assert output.samples[:5] == SAMPLE
    assert output.samples[240:245] == SAMPLE


def test_hiphop_resource_root_and_auto_discovery(tmp: Path):
    res = make_hiphop_res(tmp, [
        {"relative": "AA\\ONE.PXD", "disk": "aa/one.pxd", "name": "one",
         "frames": 240},
    ])
    assert res.name == "HIPHOP"
    mix_dir = tmp / "MIX"
    mix_dir.mkdir()
    mix = make_hiphop_mix(mix_dir / "auto.mix", [
        hiphop_block(bar1=[(1, 731)]),
    ])

    # Without the option the player looks for HIPHOP beside the mix folder.
    session = MixPlayer().load(mix, {"bpm": 44100.0})
    assert session.plan.events[0].label == "one"

    # The disc folder above HIPHOP is accepted as well as HIPHOP itself.
    session = MixPlayer().load(mix, hiphop_options(tmp, bpm=44100.0))
    assert session.plan.events[0].label == "one"
    assert session.plan.events[0].end == 240


def test_hiphop_ignores_sub_ids_and_rejects_short_file(tmp: Path):
    res = make_hiphop_res(tmp, [
        {"relative": "AA\\ONE.PXD", "disk": "aa/one.pxd", "name": "one",
         "frames": 240},
    ])
    mix = make_hiphop_mix(tmp / "meta.mix", [
        hiphop_block(bar1=[(1, 731), (2, 8), (3, 15)]),
    ])
    session = MixPlayer().load(mix, hiphop_options(res, bpm=44100.0))
    assert [event.sample_id for event in session.plan.events] == [731]

    short = tmp / "short.mix"
    short.write_bytes(mix.read_bytes()[:11233])
    try:
        MixPlayer().load(short, hiphop_options(res, bpm=44100.0))
    except FormatError:
        pass
    else:
        raise AssertionError("a truncated grid must be rejected")


def test_hiphop_list_and_cli(tmp: Path):
    res = make_hiphop_res(tmp, [
        {"relative": "AA\\ONE.PXD", "disk": "aa/one.pxd", "name": "one",
         "frames": 240},
    ])
    mix = make_hiphop_mix(tmp / "list.mix", [
        hiphop_block(bar1=[(1, 731)]),
    ])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([
            str(mix), "--pxd", str(res), "--list",
            "--bpm", "44100", "--format", "hiphop",
        ])
    assert status == 0
    text = out.getvalue()
    assert "hiphop" in text
    assert "351 blocks" in text
    assert "one" in text
    assert "T1" in text


def test_hiphop_missing_sample_strict(tmp: Path):
    res = make_hiphop_res(tmp, [
        {"relative": "AA\\ONE.PXD", "disk": "aa/one.pxd", "name": "one"},
    ])
    mix = make_hiphop_mix(tmp / "missing.mix", [
        hiphop_block(bar1=[(1, 1300)]),
    ])
    session = MixPlayer().load(mix, hiphop_options(res, bpm=44100.0))
    assert session.warnings
    assert session.plan.events == []
    try:
        MixPlayer().load(
            mix, {**hiphop_options(res, bpm=44100.0), "strict": True})
    except SampleError:
        pass
    else:
        raise AssertionError("--strict must fail on a missing sample")


def test_riff_decode_and_gain(tmp: Path):
    decoder = SampleDecoder()
    stereo = decoder.decode_bytes(make_riff_bytes(
        [100, -300, 200, -400], channels=2))
    assert list(stereo) == [100, 200]
    half = decoder.decode_bytes(make_riff_bytes(
        [100, 200], rate=22050))
    assert list(half) == [100, 100, 200, 200]

    try:
        decoder.decode_bytes(b"nope" * 20)
    except SampleError:
        pass
    else:
        raise AssertionError("an unknown sample stream must be rejected")


def test_audio_output_pause_and_close(tmp: Path):
    output = AudioOutput()
    stream = FakeStream()
    output._stream = stream
    stream.start()

    output.pause()
    assert stream.started is False
    output.resume()
    assert stream.started is True
    output.pause()
    output.close()

    assert stream.closed is True
    assert stream.stops == 2


def test_mixer_loops_and_clips(tmp: Path):
    pcm = array.array("h", [1, 2, 3])
    event = PlaybackEvent(start=0, end=6, pcm=pcm, sample_id=1, loop=True)
    plan = PlaybackPlan([event], total_frames=6, channels=1,
                        format_name="test")
    assert list(Mixer(plan).mix(0, 6)) == [1, 2, 3, 1, 2, 3]

    loud = array.array("h", [30000, -30000])
    events = [
        PlaybackEvent(start=0, end=2, pcm=loud, sample_id=1),
        PlaybackEvent(start=0, end=2, pcm=loud, sample_id=2),
    ]
    plan = PlaybackPlan(events, total_frames=2, channels=1,
                        format_name="test")
    assert list(Mixer(plan).mix(0, 2)) == [32767, -32768]


def test_event_printer_moves_console_writes_off_the_caller(tmp: Path):
    stream = BlockingStream()
    printer = EventPrinter(44100.0, stream=stream)
    event = PlaybackEvent(start=44100, end=88200, pcm=array.array("h"),
                          sample_id=0x2DB, track=1, label="just walking")
    printer.announce(event)
    assert stream.writing.wait(1.0), "the worker did not start"
    started = time.perf_counter()
    printer.note("second")
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"note waited {elapsed:.2f} s for the console"
    stream.release.set()
    printer.close()
    printer.close()
    first, second = "".join(stream.chunks).splitlines()
    assert first.split() == ["0:01.00", "T1", "02DB", "just", "walking"]
    assert second == "second"
    try:
        printer.note("late")
    except RuntimeError:
        pass
    else:
        raise AssertionError("a closed printer must reject new lines")


def test_verbose_playback_announces_every_event(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "verbose.mix",
                        [row(t1=731), row(), row(t2=731)])
    output = Recorder()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = MixPlayer().play(
            mix, {**rave_options(res, step=30 / 44100.0), "verbose": True,
                  "block": 64},
            output=output)
    assert status == 0
    lines = out.getvalue().splitlines()
    announced = [line for line in lines
                 if "  T1  " in line or "  T2  " in line]
    assert len(announced) == 2, announced
    assert announced[0].strip().startswith("0:00.00")
    assert "just walking" in announced[0]
    assert lines[-1] == "done"


def test_mixer_sums_before_clipping(tmp: Path):
    loud = array.array("h", [30000])
    quiet = array.array("h", [-30000])
    events = [
        PlaybackEvent(start=0, end=1, pcm=loud, sample_id=1),
        PlaybackEvent(start=0, end=1, pcm=loud, sample_id=2),
        PlaybackEvent(start=0, end=1, pcm=quiet, sample_id=3),
    ]
    for ordering in (events, list(reversed(events))):
        plan = PlaybackPlan(ordering, total_frames=1, channels=1,
                            format_name="test")
        assert list(Mixer(plan).mix(0, 1)) == [30000]

    left = PlaybackEvent(start=0, end=1, pcm=loud, sample_id=1,
                         left_gain=1.0, right_gain=0.0)
    right = PlaybackEvent(start=0, end=1, pcm=loud, sample_id=2,
                          left_gain=0.0, right_gain=1.0)
    plan = PlaybackPlan([left, right, PlaybackEvent(
        start=0, end=1, pcm=quiet, sample_id=3)], total_frames=1,
        channels=2, format_name="test")
    assert list(Mixer(plan).mix(0, 1)) == [0, 0]

    plan = PlaybackPlan([left, PlaybackEvent(
        start=0, end=1, pcm=loud, sample_id=2,
        left_gain=1.0, right_gain=0.0)], total_frames=1,
        channels=2, format_name="test")
    assert list(Mixer(plan).mix(0, 1)) == [32767, 0]


def test_techno_pipeline(tmp: Path):
    stream = make_riff_bytes([1000])
    res = make_techno_res(tmp, [(100, "hit", stream, 1)])
    mix = make_techno_mix(tmp / "techno.mix", {
        1: [(1.0, 100, False)],
        4: [(2.0, 100, True)],
        5: [(3.0, 100, False)],
    })
    player = MixPlayer()
    session = player.load(mix, techno_options(res, bpm=44100.0))
    assert session.mix_format.name == "techno"
    assert session.plan.channels == 2
    assert len(session.plan.events) == 3
    assert session.plan.total_frames == 481
    assert session.plan.events[1].parameters["long"] is True

    output = Recorder()
    assert player.play(
        mix, {**techno_options(res, bpm=44100.0), "quiet": True},
        output=output) == 0
    # track 1 is centred (full scale in both channels), track 4 left-only,
    # track 5 right-only
    assert output.samples[0:2] == [1000, 1000]
    assert output.samples[480:482] == [1000, 0]
    assert output.samples[960:962] == [0, 1000]


def test_techno_list(tmp: Path):
    res = make_techno_res(
        tmp, [(100, "hit", make_riff_bytes([1000]), 1)])
    mix = make_techno_mix(tmp / "techno.mix", {1: [(1.0, 100, False)]})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = MixPlayer().play(
            mix, {**techno_options(res, bpm=44100.0), "list": True})
    assert status == 0
    text = out.getvalue()
    assert "Test Mix" in text
    assert "T1" in text
    assert "test part" in text


def test_dance2_pipeline_and_cut(tmp: Path):
    res = make_dance2_res(tmp, [
        (1, "one", make_riff_bytes([1000]), 1),
        (2, "two", make_riff_bytes([2000]), 1),
        (3, "three", make_riff_bytes([3000]), 1),
        (4, "four", make_riff_bytes([4000]), 1),
    ])
    settings = [(0, 32767)] * 16
    settings[1] = (1, 32767)
    settings[2] = (2, 16384)
    mix = make_dance2_mix(
        tmp / "dance2.mix",
        settings=settings,
        sample_events=[
            (1, 0, 1, False),
            (1, 128, 2, False),
            (2, 0, 3, False),
            (3, 256, 4, False),
        ],
        text_events=[(0, "hello", "1")],
    )
    session = MixPlayer().load(mix, {"pxd": str(res)})
    assert session.mix_format.name == "dance2"
    assert session.document.title == "MC Test - Test Mix"
    assert session.plan.channels == 2
    assert session.document.metadata["text_events"] == 1
    assert session.document.payload.text_events[0].name == "hello"

    events = session.plan.events
    assert len(events) == 4
    assert events[0].start == 0 and events[0].end == 1
    assert events[0].left_gain == 1.0 and events[0].right_gain == 1.0
    assert events[1].track == 2 and events[1].left_gain == 1.0
    assert events[1].right_gain == 0.0
    assert events[2].start == 75600 and events[2].end == 75601
    assert events[3].start == 151200 and events[3].left_gain == 0.0
    assert abs(events[3].right_gain - 0.5) < 0.001
    assert session.plan.total_frames == 151201


def test_dance2_long_form_and_addon(tmp: Path):
    res = make_dance2_res(
        tmp,
        [(1, "base", make_riff_bytes([1000]), 1)],
        {"DANCESK4": [(5100, "addon", make_riff_bytes([2000]), 1)]},
    )
    mix = make_dance2_mix(
        tmp / "addon.mix",
        sample_events=[(1, 0, 1, False), (2, 0, 5100, True)],
    )
    session = MixPlayer().load(mix, {"pxd": str(res), "strict": True})
    assert len(session.plan.events) == 2
    long_event = session.plan.events[1]
    assert long_event.parameters["long"] is True
    assert long_event.label == "test part"
    payload = session.document.payload
    assert payload.sample_events[1].extension == bytes(10)
    assert payload.sample_events[1].flag == 0

    # One explicit index is enough: its folder supplies the add-on index too.
    explicit = MixPlayer().load(
        mix, {"index": str(res / "DANCE20.INF"), "strict": True})
    assert len(explicit.plan.events) == 2


def test_dance2_missing_sample_strict(tmp: Path):
    res = make_dance2_res(
        tmp, [(1, "one", make_riff_bytes([1000]), 1)])
    mix = make_dance2_mix(
        tmp / "missing.mix",
        sample_events=[(1, 0, 1, False), (2, 0, 99, False)],
    )
    session = MixPlayer().load(mix, {"pxd": str(res)})
    assert len(session.plan.events) == 1
    assert any("id 99" in warning for warning in session.warnings)
    try:
        MixPlayer().load(mix, {"pxd": str(res), "strict": True})
    except SampleError as exc:
        assert "id 99" in str(exc)
    else:
        raise AssertionError("strict must reject a missing sample")


def test_dance2_list_and_cli(tmp: Path):
    res = make_dance2_res(
        tmp, [(1, "one", make_riff_bytes([1000]), 1)])
    mix = make_dance2_mix(
        tmp / "list.mix",
        sample_events=[(1, 0, 1, False)],
        text_events=[(0, "hello", "1")],
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([str(mix), "--pxd", str(res), "--list"])
    assert status == 0
    text = out.getvalue()
    assert "MC Test - Test Mix" in text
    assert "dance2" in text
    assert "1 text events" in text
    assert "test part" in text
    assert "hello" not in text


def test_cli_integration(tmp: Path):
    res = make_rave_res(tmp)
    mix = make_rave_mix(tmp / "cli.mix", [row(t1=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([str(mix), "--pxd", str(res), "--list",
                           "--step", "0.01", "--format", "rave"])
    assert status == 0
    text = out.getvalue()
    assert "Rave eJay 1.01" in text
    assert "just walking" in text


def test_explicit_index_finds_samples(tmp: Path):
    rave_res = make_rave_res(tmp)
    rave_mix = make_rave_mix(tmp / "index.mix", [row(t1=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([
            str(rave_mix), "--index", str(rave_res / "EJAY" / "PXD"),
            "--list", "--step", "0.01", "--format", "rave",
        ])
    assert status == 0
    assert "just walking" in out.getvalue()

    techno_res = make_techno_res(
        tmp, [(100, "hit", make_riff_bytes([1000]), 1)])
    techno_mix = make_techno_mix(
        tmp / "index-techno.mix", {1: [(1.0, 100, False)]})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = cli_main([
            str(techno_mix), "--index",
            str(techno_res / "RAVE20.INF"), "--list", "--format", "techno",
        ])
    assert status == 0
    assert "test part" in out.getvalue()

    dance_res = make_dance_res(tmp, [
        {"id": 731, "relative": "AA\\ONE.PXD", "name": "one"},
    ])
    dance_mix = make_dance_mix(tmp / "index-dance.mix", [
        dance_block(bar1=[(1, 731)]),
    ])
    session = MixPlayer().load(dance_mix, {
        "index": str(dance_res / "DMACHINE" / "PXD.TXT"),
        "bpm": 44100.0,
    })
    assert [event.label for event in session.plan.events] == ["one"]


def test_custom_format_registration(tmp: Path):
    registry = MixRegistry()
    registry.register(DummyFormat())
    path = tmp / "dummy.mix"
    path.write_bytes(b"DUMM" + bytes(28))
    assert registry.detect(path).name == "dummy"
    session = MixPlayer(registry).load(path, {})
    assert session.document.title == "Dummy"
    assert session.plan.format_name == "dummy"
    assert session.plan.is_empty


def test_tp_fixture(tmp: Path):
    fixture = (Path(__file__).resolve().parent.parent
               / "data" / "hyper-test.pxd")
    if not fixture.is_file():
        print(f"    (skipped: {fixture} is absent)")
        return
    samples = SampleDecoder().decode_file(fixture)
    assert len(samples) == 14700, len(samples)


def main() -> int:
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
