"""Verification for the standalone .mix player (``sdmixplay.py``).

Run:  python test_sdmixplay.py
"""

import array
import contextlib
import io
import os
import struct
import sys
import tempfile

import sdmixplay

SAMPLE = [0, 2, 2, 4, 8]         # the synthetic tP stream below decodes to this
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, os.pardir, "data")


def make_mix(path, records, version="Rave eJay 1.01"):
    """Write a .MIX header + 16-word records + the 0x0A08 trailer."""
    blob = struct.pack("<H", sdmixplay.MIX_MAGIC)
    for record in records:
        assert len(record) == sdmixplay.RECORD_WORDS
        blob += struct.pack("<16H", *record)
    blob += struct.pack("<H", sdmixplay.MIX_TRAILER)
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


def make_res(tmp, rows=None, root=None):
    """A minimal ``_res``: one sample plus a six-line-per-record index."""
    res = root or os.path.join(tmp, "res")
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


def make_wav(path, samples, rate=44100, channels=1, bits=16):
    """A minimal PCM WAVE file from interleaved integer ``samples``."""
    if bits == 8:
        payload = bytes(v & 0xFF for v in samples)      # unsigned bytes
    else:
        payload = struct.pack("<%dh" % len(samples), *samples)
    align = channels * (bits // 8)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
           + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate,
                                   rate * align, align, bits)
           + b"data" + struct.pack("<I", len(payload)))
    with open(path, "wb") as fh:
        fh.write(hdr + payload)
    return path


def row(**cells):
    """A record from ``column=id`` keyword arguments (t1 = T1 A, b1 = T1 B)."""
    out = [0] * sdmixplay.RECORD_WORDS
    for key, value in cells.items():
        out[int(key[1:]) - 1 + (sdmixplay.TRACKS if key[0] == "b" else 0)] = \
            value
    return out


class Recorder:
    """Stand-in for a sounddevice stream: keeps the bytes it is given."""

    def __init__(self):
        self.data = bytearray()
        self.writes = 0

    def write(self, chunk):
        self.data += chunk
        self.writes += 1


def test_read_mix_and_events(tmp):
    mix = sdmixplay.read_mix(make_mix(
        os.path.join(tmp, "grid.mix"),
        [row(t1=731), row(t1=731), row(t2=732), row(b8=733)]))
    assert mix.header == sdmixplay.MIX_MAGIC
    assert len(mix.records) == 4
    assert mix.version == "Rave eJay 1.01"
    assert mix.used_records() == 4
    assert list(mix.cells())[:2] == [(0, "A", 1, 731), (1, "A", 1, 731)]
    events = sdmixplay.build_events(mix)
    assert [(e.record, e.span, e.track, e.lane, e.sample_id, e.end_record)
            for e in events] == [
        (0, 2, 1, "A", 731, 2),
        (2, 1, 2, "A", 732, 3),
        (3, 1, 8, "B", 733, 4),
    ]
    # two records at half a second each: end of the run is 1 s
    assert sdmixplay.event_frames(events[0], 0.5) == (0, 44100)


def test_padding_is_ignored(tmp):
    padding = [0] * sdmixplay.RECORD_WORDS
    for i, value in enumerate((5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6,
                               11)):
        padding[i] = value
    padding[6] = 0x0C
    padding[7] = 0x07
    mix = sdmixplay.read_mix(make_mix(
        os.path.join(tmp, "pad.mix"),
        [row(t1=731), row(), row(), padding, row()]))
    assert mix.used_records() == 1
    assert list(mix.cells()) == [(0, "A", 1, 731)]
    assert len(sdmixplay.build_events(mix)) == 1


def test_bad_mix(tmp):
    path = os.path.join(tmp, "notmix.mix")
    with open(path, "wb") as fh:
        fh.write(b"\x00\x00" + bytes(64))
    try:
        sdmixplay.read_mix(path)
    except sdmixplay.MixError:
        pass
    else:
        raise AssertionError("a bad header must be rejected")


def test_decode_tp(tmp):
    path = make_tp(os.path.join(tmp, "one.pxd"))
    assert list(sdmixplay.decode_sample(path)) == SAMPLE
    # the frame count in the header caps the output
    short = make_tp(os.path.join(tmp, "short.pxd"), frames=2)
    assert list(sdmixplay.decode_sample(short)) == SAMPLE[:2]
    empty = make_tp(os.path.join(tmp, "empty.pxd"), frames=0)
    assert len(sdmixplay.decode_sample(empty)) == 0


def test_decode_riff(tmp):
    mono = make_wav(os.path.join(tmp, "mono.wav"), [100, -100, 200])
    assert list(sdmixplay.decode_sample(mono)) == [100, -100, 200]

    stereo = make_wav(os.path.join(tmp, "stereo.wav"),
                      [100, -300, 200, -400], channels=2)
    assert list(sdmixplay.decode_sample(stereo)) == [100, 200]

    half = make_wav(os.path.join(tmp, "half.wav"), [100, 200], rate=22050)
    assert list(sdmixplay.decode_sample(half)) == [100, 100, 200, 200]

    # 8 bit is unsigned: 200 -> (200 - 128) << 8, 56 -> -18432
    eight = make_wav(os.path.join(tmp, "eight.wav"), [200, 56], rate=11025,
                     bits=8)
    values = list(sdmixplay.decode_sample(eight))
    assert values == [18432] * 4 + [-18432] * 4, values


def test_decode_rejects_unknown(tmp):
    path = os.path.join(tmp, "weird.bin")
    with open(path, "wb") as fh:
        fh.write(b"nope" * 20)
    try:
        sdmixplay.decode_sample(path)
    except sdmixplay.MixError:
        pass
    else:
        raise AssertionError("an unknown sample format must be rejected")


def test_decode_matches_engine(tmp):
    """The standalone decoder must agree with the ported one on a fixture."""
    fixture = os.path.join(DATA, "hyper-test.pxd")
    if not os.path.isfile(fixture):
        print("    (skipped: %s is absent)" % fixture)
        return
    import pxd32d5
    src = open(fixture, "rb").read()
    sess = pxd32d5.Session()
    sess.src = src
    sess.header = src[:220]
    sess.stream_end = len(src)
    sess.read_offset = 0
    sess.volume = 0x10000
    sess.pan = 256
    engine = pxd32d5.Engine()
    engine._parse_header(sess)
    buf = bytearray(4 * 40000 + 4096)
    pos = 0
    while sess.read_offset < sess.stream_end:
        produced = engine._decode_block(sess, buf, pos, 18908)
        if not produced:
            break
        pos += produced
    pcm = array.array("h")
    pcm.frombytes(bytes(buf[:pos]))
    reference = list(pcm[0::2])
    ours = list(sdmixplay.decode_sample(fixture))
    # The header declares 14700 frames but the bytecode ends one step short;
    # the converter's file is truncated to the declared length, so the
    # missing tail is one zero sample.
    assert len(ours) == 14700, len(ours)
    assert ours[:len(reference)] == reference, "decoders disagree"
    assert ours[len(reference):] == [0] * (len(ours) - len(reference))


def test_mixer_placement(tmp):
    samples = {731: array.array("h", SAMPLE)}
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731),
              sdmixplay.MixEvent(2, 1, 2, "A", 731)]
    frames = 100
    step = frames / float(sdmixplay.SAMPLE_RATE)
    mixer = sdmixplay.Mixer(events, samples, step)
    assert mixer.total == 3 * frames, mixer.total
    pcm = []
    for start in range(0, mixer.total, 64):
        pcm += list(mixer.mix(start, min(64, mixer.total - start)))
    assert len(pcm) == 3 * frames
    assert pcm[:5] == SAMPLE
    assert pcm[5:2 * frames] == [0] * (2 * frames - 5)
    assert pcm[2 * frames:2 * frames + 5] == SAMPLE


def test_mixer_loops_long_runs(tmp):
    """A run longer than its sample repeats it, across block boundaries."""
    pcm = array.array("h", [1, 2, 3])
    events = [sdmixplay.MixEvent(0, 2, 1, "A", 731)]
    step = 3 / float(sdmixplay.SAMPLE_RATE)      # one record = 3 frames
    mixer = sdmixplay.Mixer(events, {731: pcm}, step)
    assert mixer.total == 6, mixer.total
    blocks = []
    for start in range(0, 6, 4):
        blocks += list(mixer.mix(start, min(4, 6 - start)))
    assert blocks == [1, 2, 3, 1, 2, 3], blocks


def test_one_shot_is_not_looped(tmp):
    """A sample shorter than one record plays once, then silence."""
    pcm = array.array("h", [7])
    events = [sdmixplay.MixEvent(0, 2, 1, "A", 731)]
    step = 10 / float(sdmixplay.SAMPLE_RATE)     # record 10 frames, run 20
    mixer = sdmixplay.Mixer(events, {731: pcm}, step)
    assert list(mixer.mix(0, 20)) == [7] + [0] * 19


def test_final_sample_rings_out(tmp):
    """At the end of the grid a sample plays its whole length, not one run."""
    pcm = array.array("h", [1, 2, 3, 4])
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731)]
    step = 2 / float(sdmixplay.SAMPLE_RATE)      # record 2 frames, run 2
    mixer = sdmixplay.Mixer(events, {731: pcm}, step)
    assert mixer.total == 4, mixer.total
    assert list(mixer.mix(0, 4)) == [1, 2, 3, 4]


def test_samples_ring_through_gaps(tmp):
    """A sample plays out through empty records, cut at the next takeover."""
    samples = {731: array.array("h", [1, 2, 3, 4]),
               732: array.array("h", [0, 0])}
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731),
              sdmixplay.MixEvent(3, 1, 1, "A", 732)]
    step = 2 / float(sdmixplay.SAMPLE_RATE)      # record 2 frames
    mixer = sdmixplay.Mixer(events, samples, step)
    assert mixer.total == 8, mixer.total
    assert list(mixer.mix(0, 6)) == [1, 2, 3, 4, 0, 0]


def test_only_final_record_rings_out(tmp):
    """An earlier long sample is cut at its run; the final record rings."""
    samples = {731: array.array("h", [1, 2, 3, 4]),
               732: array.array("h", [0, 0])}
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731),
              sdmixplay.MixEvent(1, 1, 2, "A", 732)]
    step = 2 / float(sdmixplay.SAMPLE_RATE)      # record 2 frames
    mixer = sdmixplay.Mixer(events, samples, step)
    assert mixer.total == 4, mixer.total
    assert list(mixer.mix(0, 2)) == [1, 2], "the first sample must be cut"
    assert list(mixer.mix(2, 2)) == [0, 0]


def test_same_track_samples_overlap(tmp):
    """A sample is not cut when another event starts on its track."""
    samples = {731: array.array("h", [1, 2, 3, 4]),
               732: array.array("h", [9, 9, 9, 9]),
               733: array.array("h", [0])}
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731),
              sdmixplay.MixEvent(1, 1, 1, "A", 732),
              sdmixplay.MixEvent(5, 1, 2, "A", 733)]
    step = 2 / float(sdmixplay.SAMPLE_RATE)
    mixer = sdmixplay.Mixer(events, samples, step)
    assert mixer.total == 12, mixer.total
    assert list(mixer.mix(0, 4)) == [1, 2, 12, 13], list(mixer.mix(0, 4))


def test_mixer_sums_and_clips(tmp):
    samples = {731: array.array("h", [30000, -30000]),
               732: array.array("h", [30000, -30000])}
    events = [sdmixplay.MixEvent(0, 1, 1, "A", 731),
              sdmixplay.MixEvent(0, 1, 2, "A", 732)]
    step = 2 / float(sdmixplay.SAMPLE_RATE)
    mixer = sdmixplay.Mixer(events, samples, step)
    assert list(mixer.mix(0, 4)) == [32767, -32768, 0, 0]


def test_play_through_stream(tmp):
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "play.mix"),
                   [row(t1=731), row(), row(t2=731)])
    frames = 200
    args = sdmixplay.build_parser().parse_args(
        [mix, "-r", res, "--step", str(frames / float(sdmixplay.SAMPLE_RATE)),
         "-q", "--block", "64"])
    stream = Recorder()
    assert sdmixplay.play(args, stream=stream) == 0
    assert stream.writes > 1, stream.writes
    pcm = array.array("h")
    pcm.frombytes(bytes(stream.data))
    left = list(pcm)
    assert len(left) == 3 * frames, len(left)
    assert left[:5] == SAMPLE, left[:5]
    assert left[5:2 * frames] == [0] * (2 * frames - 5)
    assert left[2 * frames:2 * frames + 5] == SAMPLE, \
        left[2 * frames:2 * frames + 5]


def test_gain(tmp):
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "gain.mix"), [row(t1=731)])
    frames = 5
    step = frames / float(sdmixplay.SAMPLE_RATE)
    args = sdmixplay.build_parser().parse_args(
        [mix, "-r", res, "--step", str(step), "-q", "-g", "0.5"])
    stream = Recorder()
    assert sdmixplay.play(args, stream=stream) == 0
    pcm = array.array("h")
    pcm.frombytes(bytes(stream.data))
    assert list(pcm)[:5] == [0, 1, 1, 2, 4], list(pcm)


def test_list_mode(tmp):
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "list.mix"),
                   [row(t1=731), row(), row(t2=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert sdmixplay.main([mix, "-r", res, "--list", "--step", "0.01"]) == 0
    text = out.getvalue()
    assert "Rave eJay 1.01" in text
    assert "T1 A" in text and "T2 A" in text
    assert "r1bs001.pxd" in text


def test_step_from_bpm(tmp):
    """One record is two bars: 117 600 frames, 2.667 s at 44.1 kHz."""
    args = sdmixplay.build_parser().parse_args(["-"])
    step = sdmixplay.step_seconds(args)
    assert abs(step - 8.0 / 3.0) < 1e-9, step
    assert int(round(step * sdmixplay.SAMPLE_RATE)) == sdmixplay.RECORD_FRAMES
    assert sdmixplay.RECORD_FRAMES == 117600        # 2 x 58 800, one bar each
    args = sdmixplay.build_parser().parse_args(["-", "--bpm", "60"])
    assert sdmixplay.step_seconds(args) == 8.0
    args = sdmixplay.build_parser().parse_args(["-", "--step", "0.5"])
    assert sdmixplay.step_seconds(args) == 0.5


def test_default_record_length(tmp):
    """A 3-record grid plays for 3 x 117 600 frames with no --step given."""
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "tempo.mix"),
                   [row(t1=731), row(), row(t1=731)])
    args = sdmixplay.build_parser().parse_args([mix, "-r", res, "-q"])
    stream = Recorder()
    assert sdmixplay.play(args, stream=stream) == 0
    assert len(stream.data) // 2 == 3 * sdmixplay.RECORD_FRAMES, \
        len(stream.data) // 2


def test_missing_index(tmp):
    mix = make_mix(os.path.join(tmp, "noindex.mix"), [row(t1=731)])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert sdmixplay.main([mix, "--res", os.path.join(tmp, "nowhere"),
                               "--list"]) == 1
    assert "sample index" in err.getvalue()


def test_missing_and_bad_samples(tmp):
    res = make_res(tmp)
    mix = make_mix(os.path.join(tmp, "missing.mix"),
                   [row(t1=0x400), row(t2=731)])
    out = io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()) as err:
        assert sdmixplay.main([mix, "-r", res, "--list"]) == 0
    assert "T2 A" in out.getvalue()
    assert "skipping" in err.getvalue()

    # the same arrangement, but the sample itself is not decodable
    bad = os.path.join(tmp, "badres")
    make_res(tmp, root=bad)
    with open(os.path.join(bad, "bq", "r1bs001.pxd"), "wb") as fh:
        fh.write(b"nope" * 50)
    stream = Recorder()
    args = sdmixplay.build_parser().parse_args([mix, "-r", bad, "-q"])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert sdmixplay.play(args, stream=stream) == 1
    assert "no playable samples" in err.getvalue()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(tmp)
                print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
