"""Verification for the mixplay CLI (Rave eJay .MIX playback).

Run:  python test_mixplay.py
"""

import array
import contextlib
import io
import os
import struct
import tempfile

import mixplay
import pxd32d5
import pxdsink

SAMPLE = [0, 2, 2, 4, 8]         # the synthetic tP stream below decodes to this


def make_mix(path, records, version="Rave eJay 1.01"):
    """Write a .MIX header + 16-word records + the 0x0A08 trailer."""
    blob = struct.pack("<H", mixplay.MIX_MAGIC)
    for record in records:
        assert len(record) == mixplay.RECORD_WORDS
        blob += struct.pack("<16H", *record)
    blob += struct.pack("<H", mixplay.MIX_TRAILER)
    blob += struct.pack("<H", 1)
    blob += struct.pack("<H", 16)
    blob += version.encode("latin-1")[:15] + b"\0"
    blob += bytes(20)
    with open(path, "wb") as fh:
        fh.write(blob)
    return path


def make_tp(path, frames=len(SAMPLE)):
    """One tP stream that plays five samples on the DPCM integrator."""
    payload = bytes([0xF5, 0x01, 0x80, 0x81, 0x01, 0xFF, 0x82, 0x01])
    hdr = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
           + struct.pack("<i", frames) + b"\0\0")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(hdr + payload + bytes(300))
    return path


def make_res(tmp, rows=None):
    """A minimal ``_res``: one sample plus a six-line-per-record index."""
    res = os.path.join(tmp, "res")
    make_tp(os.path.join(res, "bq", "r1bs001.pxd"))
    os.makedirs(os.path.join(res, "EJAY"), exist_ok=True)
    if rows is None:
        rows = [("bq\\r1bs001.pxd", "bass", "2", "just walking", "1")]
    lines = []
    for rel, category, number, name, second in rows:
        lines += ['"%s"' % rel, '""', '"%s"' % category, '"%s"' % number,
                  '"%s"' % name, '"%s"' % second]
    with open(os.path.join(res, "EJAY", "PXD"), "wb") as fh:
        fh.write(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return res


def row(**cells):
    """A record from ``column=id`` keyword arguments (T1A = column 1)."""
    out = [0] * mixplay.RECORD_WORDS
    for key, value in cells.items():
        out[int(key[1:]) - 1 + (mixplay.TRACKS if key[0] == "b" else 0)] = value
    return out


def test_read_mix_and_events(tmp):
    mix = mixplay.read_mix(make_mix(
        os.path.join(tmp, "grid.mix"),
        [row(t1=731), row(t1=731), row(t2=732), row(b8=733)]))
    assert mix.header == mixplay.MIX_MAGIC
    assert len(mix.records) == 4
    assert mix.version == "Rave eJay 1.01"
    assert mix.used_records() == 4
    cells = list(mix.cells())
    assert cells[:2] == [(0, "A", 1, 731), (1, "A", 1, 731)]
    assert cells[-1] == (3, "B", 8, 733)
    events = mixplay.build_events(mix)
    assert [(e.record, e.span, e.track, e.lane, e.sample_id, e.end_record)
            for e in events] == [
        (0, 2, 1, "A", 731, 2),
        (2, 1, 2, "A", 732, 3),
        (3, 1, 8, "B", 733, 4),
    ]
    # a run of one ID is one sounding, not one hit per record
    assert mixplay.event_range(events[0], 0.5) == (
        0, mixplay.BYTES_PER_FRAME * int(0.5 * mixplay.SAMPLE_RATE) * 2)


def test_padding_is_ignored(tmp):
    """Stray bytes in the unused grid are not cells (MIX_FORMAT section 7)."""
    padding = [0] * mixplay.RECORD_WORDS
    # the (5*n) mod 16 counter the notes found at offsets 7,660-7,948
    for i, value in enumerate((5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6,
                               11)):
        padding[i] = value
    padding[6] = 0x0C               # the stray bytes at offsets 6,638/6,640
    padding[7] = 0x07
    mix = mixplay.read_mix(make_mix(
        os.path.join(tmp, "pad.mix"),
        [row(t1=731), row(), row(), padding, row()]))
    assert len(mix.records) == 5
    assert mix.used_records() == 1
    assert list(mix.cells()) == [(0, "A", 1, 731)]
    assert [(e.record, e.track, e.lane, e.sample_id)
            for e in mixplay.build_events(mix)] == [(0, 1, "A", 731)]
    # and the player does not report them as missing samples
    res = make_res(tmp)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        assert mixplay.main([mix.path, "-r", res, "--list"]) == 0
    assert "missing" not in err.getvalue(), err.getvalue()
    assert " 1 records " in out.getvalue(), out.getvalue()


def test_bad_header(tmp):
    path = os.path.join(tmp, "notmix.mix")
    with open(path, "wb") as fh:
        fh.write(b"\x00\x00" + bytes(64))
    try:
        mixplay.read_mix(path)
    except mixplay.MixError:
        pass
    else:
        raise AssertionError("a bad header must be rejected")
    assert mixplay.main([path]) == 1


def test_index_and_resolution(tmp):
    res = make_res(tmp)
    index = mixplay.read_index(os.path.join(res, "EJAY", "PXD"))
    assert len(index) == 1
    entry = mixplay.sample_for(731, index)
    assert entry is not None
    assert (entry.category, entry.name) == ("bass", "just walking 1")
    assert mixplay.sample_for(730, index) is None
    assert mixplay.sample_for(732, index) is None
    path = mixplay.resolve_sample(res, entry.path)
    assert path is not None and os.path.basename(path).lower() == "r1bs001.pxd"
    # the index names folders in lower case; the install may not
    upper = os.path.join(tmp, "upper")
    os.makedirs(os.path.join(upper, "BQ"))
    make_tp(os.path.join(upper, "BQ", "R1BS001.PXD"))
    found = mixplay.resolve_sample(upper, "bq\\r1bs001.pxd")
    assert found == os.path.join(upper, "BQ", "R1BS001.PXD"), found
    assert mixplay.resolve_sample(upper, "nope\\x.pxd") is None


def test_list_mode(tmp):
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "list.mix"),
                   [row(t1=731), row(), row(t2=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert mixplay.main([mix, "-r", res, "--list", "--step", "0.01"]) == 0
    text = out.getvalue()
    assert "Rave eJay 1.01" in text
    assert "T1 A" in text and "T2 A" in text
    assert "r1bs001.pxd" in text
    assert "0:00.00" in text


def test_step_from_bpm(tmp):
    args = mixplay.build_parser().parse_args(["-"])
    # 180 bpm, 8 beats: one record is two bars, 117 600 frames
    assert abs(mixplay.step_seconds(args) - 8.0 / 3.0) < 1e-9
    assert int(round(mixplay.step_seconds(args) * mixplay.SAMPLE_RATE)) == 117600
    args = mixplay.build_parser().parse_args(["-", "--bpm", "60"])
    assert mixplay.step_seconds(args) == 8.0
    args = mixplay.build_parser().parse_args(["-", "--bpm", "60", "--step",
                                              "0.25"])
    assert mixplay.step_seconds(args) == 0.25


def test_playback_file_sink(tmp):
    res = make_res(tmp)
    # one sample on T1 at record 0, a gap, then the same sample on T2
    mix = make_mix(os.path.join(tmp, "play.mix"),
                   [row(t1=731), row(), row(t2=731)])
    pcm_path = os.path.join(tmp, "play.raw")
    frames = 200                                   # frames per record
    args = mixplay.build_parser().parse_args(
        [mix, "-r", res, "--step", str(frames / float(mixplay.SAMPLE_RATE)),
         "-q"])
    sink = pxdsink.FileSink(pcm_path)
    assert mixplay.play(args, sink=sink) == 0
    pcm = array.array("h")
    pcm.frombytes(open(pcm_path, "rb").read())
    left = list(pcm[0::2])
    right = list(pcm[1::2])
    assert len(left) == 3 * frames, len(left)
    assert left[:5] == SAMPLE, left[:5]
    assert right[:5] == SAMPLE          # sub_10016325 duplicates left to right
    # The 300 zero bytes after the fixture's payload are stream data, so the
    # decoder holds its last value to the request's end and the entry overrun
    # can run ~64 frames in; the rest of the empty record is silence.
    assert left[2 * frames - 100:2 * frames] == [0] * 100
    # T2 starts at record 2
    assert left[2 * frames:2 * frames + 5] == SAMPLE, \
        left[2 * frames:2 * frames + 5]


def test_decode_failure_skips_sample(tmp):
    """A stream the decoder cannot render must not stop the arrangement."""
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "broken.mix"),
                   [row(t1=731), row(), row(t2=731)])
    frames = 200
    args = mixplay.build_parser().parse_args(
        [mix, "-r", res, "--step", str(frames / float(mixplay.SAMPLE_RATE)),
         "-q"])
    original = pxd32d5.Engine._decode_block
    calls = {"n": 0}

    def fail_once(engine, sess, dest, offset, want):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("bad stream")
        return original(engine, sess, dest, offset, want)

    err = io.StringIO()
    pcm_path = os.path.join(tmp, "broken.raw")
    pxd32d5.Engine._decode_block = fail_once
    try:
        with contextlib.redirect_stderr(err):
            assert mixplay.play(args, sink=pxdsink.FileSink(pcm_path)) == 0
    finally:
        pxd32d5.Engine._decode_block = original
    assert calls["n"] > 1, calls            # the later events still decoded
    assert "bad stream" in err.getvalue(), err.getvalue()
    pcm = array.array("h")
    pcm.frombytes(open(pcm_path, "rb").read())
    left = list(pcm[0::2])
    assert len(left) == 3 * frames, len(left)
    assert left[2 * frames:2 * frames + 5] == SAMPLE, \
        left[2 * frames:2 * frames + 5]


def test_missing_sample(tmp):
    res = make_res(tmp, rows=[("bq\\r1bs001.pxd", "bass", "2", "one", "1")])
    # 0x400 is beyond the one-record index
    mix = make_mix(os.path.join(tmp, "missing.mix"), [row(t1=0x400)])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert mixplay.main([mix, "-r", res, "--list"]) == 1
    assert "nothing to play" in err.getvalue()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert mixplay.main([mix, "-r", res, "--list", "--strict"]) == 1
    assert "not found" in err.getvalue()


def test_missing_index(tmp):
    mix = make_mix(os.path.join(tmp, "noindex.mix"), [row(t1=731)])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert mixplay.main([mix, "--res", os.path.join(tmp, "nowhere"),
                             "--list"]) == 1
    assert "sample index" in err.getvalue()


def test_skip_missing_sample(tmp):
    res = make_res(tmp, rows=[("bq\\r1bs001.pxd", "bass", "2", "one", "1")])
    mix = make_mix(os.path.join(tmp, "skip.mix"),
                   [row(t1=731), row(t1=0x400)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert mixplay.main([mix, "-r", res, "--list"]) == 0
    # the unresolvable cell is dropped, the real one is still listed
    assert "T1 A" in out.getvalue()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(tmp)
                print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
