"""Verification for the pxd2wav CLI front end.

Run:  python test_pxd2wav.py
"""

import os
import struct
import tempfile

import pxd2wav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def fixture(name):
    return os.path.join(DATA, name)


def read_wav(path):
    with open(path, "rb") as fh:
        blob = fh.read()
    assert blob[0:4] == b"RIFF", blob[:4]
    assert blob[8:12] == b"WAVE"
    assert blob[12:16] == b"fmt "
    tag, ch, rate, avg, align, bits = struct.unpack("<HHIIHH", blob[20:36])
    assert blob[36:40] == b"data"
    size = struct.unpack("<I", blob[40:44])[0]
    return {
        "tag": tag, "channels": ch, "rate": rate, "avg": avg,
        "align": align, "bits": bits, "size": size,
        "samples": list(struct.unpack("<%dh" % (size // 2), blob[44:44 + size])),
        "total": len(blob),
    }


def test_hyper_cli_matches_reference(tmp):
    src = fixture("hyper-test.pxd")
    ref = fixture("hyper-test.wav")
    outdir = os.path.join(tmp, "out")
    assert pxd2wav.main([src, "-o", outdir, "-f"]) == 0
    dst = os.path.join(outdir, "hyper-test.wav")
    assert os.path.getsize(dst) == os.path.getsize(ref)
    assert open(dst, "rb").read() == open(ref, "rb").read()
    w = read_wav(dst)
    assert (w["tag"], w["channels"], w["rate"], w["bits"]) == (1, 1, 44100, 16)
    assert w["size"] == 29400 and w["total"] == 29444
    assert len(w["samples"]) == 14700
    assert (min(w["samples"]), max(w["samples"])) == (-12604, 12588)
    assert (sum(w["samples"]), sum(v * v for v in w["samples"])) == (
        -2385408, 307018638208)


def test_hyper_raw(tmp):
    src = fixture("hyper-test.pxd")
    ref = fixture("hyper-test.wav")
    outdir = os.path.join(tmp, "raw")
    assert pxd2wav.main([src, "-o", outdir, "--raw", "-f"]) == 0
    dst = os.path.join(outdir, "hyper-test.pcm")
    assert os.path.getsize(dst) == 29400
    assert open(dst, "rb").read() == open(ref, "rb").read()[44:]


def test_hyper_refuses_overwrite_without_force(tmp):
    src = fixture("hyper-test.pxd")
    outdir = os.path.join(tmp, "out")
    assert pxd2wav.main([src, "-o", outdir, "-f"]) == 0
    assert pxd2wav.main([src, "-o", outdir]) == 1


def test_hyper_missing_file(tmp):
    outdir = os.path.join(tmp, "out")
    assert pxd2wav.main([os.path.join(tmp, "nope.pxd"), "-o", outdir]) == 1


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(tmp)
                print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
