"""Verification for the standalone .pxd player (``sdpxdplay.py``).

Run:  python test_sdpxdplay.py
"""

import array
import contextlib
import io
import os
import struct
import tempfile

import sdpxdplay

SAMPLE = [0, 2, 2, 4, 8]     # the synthetic tP stream below decodes to this


def make_tp(path, frames=len(SAMPLE)):
    """A tP stream of five DPCM-integrated samples."""
    payload = bytes([0xF5, 0x01, 0x80, 0x81, 0x01, 0xFF, 0x82, 0x01])
    hdr = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
           + struct.pack("<i", frames) + b"\0\0")
    with open(path, "wb") as fh:
        fh.write(hdr + payload + bytes(300))
    return path


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


class Recorder:
    """Stand-in for a sounddevice stream: keeps the bytes it is given."""

    def __init__(self):
        self.data = bytearray()
        self.writes = 0
        self.stopped = False
        self.closed = False

    def write(self, chunk):
        self.data += chunk
        self.writes += 1

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def parse(argv):
    return sdpxdplay.build_parser().parse_args(argv)


def pcm(stream):
    out = array.array("h")
    out.frombytes(bytes(stream.data))
    return list(out)


def test_play_tp(tmp):
    src = make_tp(os.path.join(tmp, "one.pxd"))
    stream = Recorder()
    assert sdpxdplay.play(parse([src, "-q"]), stream=stream) == 0
    assert pcm(stream) == SAMPLE, pcm(stream)
    assert stream.writes == 1, stream.writes
    # an injected stream belongs to the caller and is not stopped/closed
    assert stream.stopped is False and stream.closed is False


def test_play_blocks(tmp):
    src = make_tp(os.path.join(tmp, "blocks.pxd"))
    stream = Recorder()
    # min block is 64 frames, so a five-frame file is still one write; use a
    # larger synthetic stream to cross a block boundary.
    big = make_tp(os.path.join(tmp, "big.pxd"), frames=300)
    assert sdpxdplay.play(parse([big, "-q", "--block", "100"]),
                          stream=stream) == 0
    assert stream.writes == 3, stream.writes
    assert len(pcm(stream)) == 300
    assert sdpxdplay.play(parse([src, "-q"]), stream=Recorder()) == 0


def test_gain(tmp):
    src = make_tp(os.path.join(tmp, "gain.pxd"))
    stream = Recorder()
    assert sdpxdplay.play(parse([src, "-q", "-g", "0.5"]),
                          stream=stream) == 0
    assert pcm(stream) == [0, 1, 1, 2, 4], pcm(stream)

    # clipping matches the engine's saturating add-to-destination
    samples = array.array("h", [30000, -30000, 100])
    sdpxdplay.apply_gain(samples, 2.0)
    assert list(samples) == [32767, -32768, 200], list(samples)
    unchanged = array.array("h", SAMPLE)
    sdpxdplay.apply_gain(unchanged, 1.0)
    assert list(unchanged) == SAMPLE


def test_play_wav(tmp):
    src = make_wav(os.path.join(tmp, "mono.wav"), [100, -100, 200])
    stream = Recorder()
    assert sdpxdplay.play(parse([src, "-q"]), stream=stream) == 0
    assert pcm(stream) == [100, -100, 200], pcm(stream)


def test_bad_input(tmp):
    missing = os.path.join(tmp, "nope.pxd")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert sdpxdplay.play(parse([missing]), stream=Recorder()) == 1
    assert "no such file" in err.getvalue()

    bad = os.path.join(tmp, "bad.pxd")
    with open(bad, "wb") as fh:
        fh.write(b"nope" * 50)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert sdpxdplay.play(parse([bad]), stream=Recorder()) == 1
    assert "unknown sample format" in err.getvalue()

    empty = make_tp(os.path.join(tmp, "empty.pxd"), frames=0)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert sdpxdplay.play(parse([empty]), stream=Recorder()) == 1
    assert "no audio data" in err.getvalue()


def test_main_validation(tmp):
    for argv in ([], ["x", "-g", "0"], ["x", "--block", "0"]):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                sdpxdplay.main(argv)
            except SystemExit as exc:
                assert exc.code == 2, (argv, exc.code)
            else:
                raise AssertionError("expected SystemExit for %r" % (argv,))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(tmp)
                print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
