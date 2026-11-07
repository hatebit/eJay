"""Verification for the PXD32D4 port.

Run:  python test_pxd32d4.py

The fixtures are synthetic: a 44-byte RIFF/WAVE wrapper and a ``tP``
container built from the offset table in ``../docs/PXD32D4.md`` section
10.5.  Expected values are derived from the note, not from the binary.
"""

import os
import struct
import tempfile

import pxd32d4
import tp_codec


def _riff(payload, channels=1, bits=16, rate=44100):
    align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * align,
                      align, bits)
    body = b"WAVEfmt " + struct.pack("<I", 16) + fmt
    body += b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _tp(frames, code, length=4):
    comment = bytes(length - 1)
    return (b"tPxD" + bytes([length]) + comment + b"\x00\x00"
            + struct.pack("<I", frames) + b"\x00\x00" + code)


def _write(tmp, name, data):
    path = os.path.join(tmp, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def test_delta_table_is_the_d4_ladder(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    assert engine.delta_table == tp_codec.d4_delta_table()
    assert engine.delta_table[128] == 0
    assert (min(engine.delta_table), max(engine.delta_table)) == (
        -25266, 25266)


def test_awave_dauer_tp(tmp):
    path = _write(tmp, "a.pxd", _tp(1000, bytes(300)))
    assert pxd32d4.awave_dauer(path) == 4000


def test_awave_dauer_riff_variants(tmp):
    mono = _write(tmp, "m.wav", _riff(bytes(400)))
    assert pxd32d4.awave_dauer(mono) == 872
    eight = _write(tmp, "e.wav", _riff(bytes(400), bits=8, rate=22050))
    assert pxd32d4.awave_dauer(eight) == 3488
    stereo = _write(tmp, "s.wav", _riff(bytes(400), channels=2))
    assert pxd32d4.awave_dauer(stereo) == 436


def test_awave_dauer_rejects_short_files(tmp):
    path = _write(tmp, "short.wav", _riff(bytes(10)))
    assert pxd32d4.awave_dauer(path) == 0


def test_classify_tp_and_riff(tmp):
    info = pxd32d4.classify(_tp(7, b"\xff\x01"))
    assert (info.kind, info.offset, info.frames) == ("tp", 16, 7)
    riff = pxd32d4.classify(_riff(bytes(400)))
    assert (riff.kind, riff.offset, riff.size) == ("riff", 44, 400)
    assert (riff.channels, riff.rate, riff.bits) == (1, 44100, 16)
    assert pxd32d4.classify(b"NOPE" + bytes(20)).kind == "unknown"


def test_rwavtotemp_tp(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    src = _write(tmp, "a.pxd",
                 _tp(3, b"\xff\x05\xff\x03\xff\x02" + bytes(300)))
    dst = os.path.join(tmp, "a.wav")
    assert engine.RWavToTemp(src, dst) == 0
    with open(dst, "rb") as fh:
        data = fh.read()
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"
    assert struct.unpack_from("<I", data, 40)[0] == 6
    ladder = tp_codec.d4_delta_table()
    first = ladder[5]
    second = ((first + ladder[3] + 0x8000) & 0xFFFF) - 0x8000
    assert struct.unpack_from("<3h", data, 44) == (0, first, second)


def test_rwavtotemp_halves_riff_samples(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    payload = struct.pack("<3h", 100, -100, 32767) + bytes(394)
    src = _write(tmp, "m.wav", _riff(payload))
    dst = os.path.join(tmp, "m.wav.out")
    assert engine.RWavToTemp(src, dst) == 0
    with open(dst, "rb") as fh:
        data = fh.read()
    assert struct.unpack_from("<I", data, 40)[0] == 436
    assert struct.unpack_from("<3h", data, 44) == (50, -50, 16383)


def test_tail_ramps_and_pads(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    src = _write(tmp, "a.pxd",
                 _tp(3, b"\xff\x05\xff\x03\xff\x02" + bytes(300)))
    dst = os.path.join(tmp, "a.wav")
    assert engine.RWavToTemp(src, dst, a7=1) == 0
    with open(dst, "rb") as fh:
        data = fh.read()
    assert struct.unpack_from("<I", data, 40)[0] == 9450
    assert len(data) == 44 + 9450
    assert struct.unpack_from("<h", data, 44 + 9450 - 2)[0] == 0


def test_guard_requires_a_running_engine(tmp):
    engine = pxd32d4.Engine()
    src = _write(tmp, "a.pxd", _tp(3, b"\xff\x01"))
    assert engine.RWavToTemp(src, os.path.join(tmp, "x.wav")) == 0
    assert engine.RWaveLaden(src) == 0


def test_sound_path_is_not_ported(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    try:
        engine.RWavToTemp("", None, a3=1)
    except pxd32d4.UnsupportedFeature:
        return
    raise AssertionError("a3 > 0 must raise UnsupportedFeature")


def test_apay_slot_layout(tmp):
    engine = pxd32d4.Engine()
    assert engine.APlay(name="x") == 0
    engine.AInit()
    assert engine.APlay(1, 2, 3, 4, 5, 99, "song.pxd", 3,
                        10, 20, 30, 40) == 0
    slot = engine.voices[3].slots[0]
    assert slot.marker == 1
    assert slot.mode == 99
    assert (slot.a2, slot.a3, slot.a4, slot.a5) == (2, 3, 4, 5)
    assert slot.a12 == 40
    assert (slot.start, slot.time, slot.end) == (8, 20, 28)
    assert slot.name == "song.pxd"
    assert engine.voices[3].cursor == 1


def test_apay_cursor_wraps(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    for _ in range(pxd32d4.SLOT_RING):
        engine.APlay(name="x", a8=2)
    assert engine.voices[2].cursor == 0


def test_lifecycle_and_parameters(tmp):
    engine = pxd32d4.Engine()
    assert engine.ADevice() == 0
    assert engine.AInit() == 0
    assert engine.magic == pxd32d4.MAGIC
    assert len(engine.voices) == 16
    assert engine.AMemory(8_000_000) == 1
    assert engine.AMemory(32_000_000) == 0
    assert engine.RWaveParam(60, 32000) == 0
    assert engine.voices[0].gain == 143606
    assert engine.AMitte(0, 0x1234) == 1 and engine.voices[0].pan == 0x1234
    assert engine.AStart(1000) == 0 and engine.command == 2
    assert engine.AStop() == 1 and engine.command == 1
    assert engine.AExit() == 1
    engine.temp_path = _write(tmp, "t.wav", b"")
    assert engine.RWaveLaden(engine.temp_path, a2=0x7B) == 0
    assert engine.AEnd() == 0 and engine.magic == 0


def test_unknown_stream_raises(tmp):
    engine = pxd32d4.Engine()
    engine.AInit()
    src = _write(tmp, "u.bin", b"NOPE" + bytes(300))
    try:
        engine.RWavToTemp(src, os.path.join(tmp, "u.wav"))
    except pxd32d4.UnsupportedCodec:
        return
    raise AssertionError("unknown stream must raise UnsupportedCodec")


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as tmp:
                fn(tmp)
            print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
