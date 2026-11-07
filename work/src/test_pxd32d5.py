"""Verification for the PInit / RWavToTemp / PClose port.

Run:  python test_pxd32d5.py
"""

import array
import os
import struct
import tempfile
import time

import pxd32d5
import pxdsink

# The fixtures live in <repo>/data; resolve them relative to this file so the
# suite can be started from anywhere.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def fixture(name):
    return os.path.join(DATA, name)


def make_wav(path, frames, rate=44100, channels=2, bits=16, left=None):
    """Write a plain PCM wav; left(i) gives the left channel sample."""
    if left is None:
        left = lambda i: (i * 137) % 4000 - 2000
    data = bytearray()
    for i in range(frames):
        v = left(i)
        if bits == 8:
            b = (v >> 8) + 128
            data.append(b)
            if channels == 2:
                data.append(255 - b % 256)
        else:
            data += struct.pack("<h", v)
            if channels == 2:
                data += struct.pack("<h", -v)
    align = channels * (bits // 8)
    header = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
              + struct.pack("<IHHIIHH", 16, 1, channels, rate,
                            rate * align, align, bits)
              + b"data" + struct.pack("<I", len(data)))
    with open(path, "wb") as fh:
        fh.write(header + data)
    return path


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


def new_engine():
    eg = pxd32d5.Engine()
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.RWaveParam(60, 32000)
    eg.output_kind = 4          # dword_10096CD8 == 4 -> write a RIFF header
    return eg


def test_stereo_conversion(tmp):
    src = make_wav(os.path.join(tmp, "st.wav"), 4410)
    out = os.path.join(tmp, "out_st.wav")
    eg = new_engine()
    assert eg.started is True
    rc = eg.RWavToTemp(src, out, 0, None, 0, 0, 0)
    assert rc == 0, rc
    w = read_wav(out)
    assert (w["tag"], w["channels"], w["rate"], w["bits"]) == (1, 1, 44100, 16)
    assert w["avg"] == 88200 and w["align"] == 2
    # AWaveDauer() returns the data chunk size for a plain 44.1k/16/stereo
    # file, /2 -> one 16 bit mono sample per input frame.
    assert w["size"] == 8820, w["size"]
    assert w["total"] == 44 + 8820
    expected = [(i * 137) % 4000 - 2000 for i in range(4410)]
    assert w["samples"] == expected


def test_mono_22050_upsampled(tmp):
    src = make_wav(os.path.join(tmp, "m22.wav"), 2205, rate=22050, channels=1)
    out = os.path.join(tmp, "out_m22.wav")
    eg = new_engine()
    assert eg.RWavToTemp(src, out, 0, None, 0, 0, 0) == 0
    w = read_wav(out)
    assert (w["channels"], w["rate"], w["bits"]) == (1, 44100, 16)
    assert w["size"] == 8820
    expected = []
    for i in range(2205):
        expected += [(i * 137) % 4000 - 2000] * 2
    assert w["samples"] == expected


def test_8bit_mono_11025(tmp):
    src = make_wav(os.path.join(tmp, "m8.wav"), 1103, rate=11025,
                   channels=1, bits=8,
                   left=lambda i: ((i * 137) % 4000 - 2000))
    out = os.path.join(tmp, "out_m8.wav")
    eg = new_engine()
    assert eg.RWavToTemp(src, out, 0, None, 0, 0, 0) == 0
    w = read_wav(out)
    assert w["size"] == 4 * 1103 * 2, w["size"]      # x4 rate, x2 8-bit
    expected = []
    for i in range(1103):
        v = ((((i * 137) % 4000 - 2000) >> 8) + 128 - 128) << 8
        expected += [v] * 4
    assert w["samples"] == expected


def test_tail_fade_and_padding(tmp):
    src = make_wav(os.path.join(tmp, "fade.wav"), 4410)
    out = os.path.join(tmp, "out_fade.wav")
    eg = new_engine()
    assert eg.RWavToTemp(src, out, 0, None, 0, 0, 1) == 0
    w = read_wav(out)
    assert w["size"] == 9450, w["size"]               # 1 block of 2*4725
    s = w["samples"]
    assert s[-1] == 0                                 # last sample muted
    assert len(s) == 4725


def test_stream_handle_path(tmp):
    src = make_wav(os.path.join(tmp, "h.wav"), 4410)
    raw = open(src, "rb").read()
    out = os.path.join(tmp, "out_h.wav")
    eg = new_engine()
    fh = open(src, "rb")
    try:
        assert eg.RWavToTemp("", out, 0, fh, 0, len(raw), 0) == 0
    finally:
        fh.close()
    assert os.path.getsize(eg.temp_stream) == len(raw)
    w = read_wav(out)
    assert w["size"] == 8820


def test_tp_header_parse(tmp):
    assert pxd32d5._idiv(-7, 2) == -3          # C truncates toward zero
    assert pxd32d5._idiv(7, 2) == 3
    # shape verified against bo-test.pxd / hyper-test.pxd in this folder:
    #   "tPxD" + [len: h[4] bytes incl. the length itself at offset 4]
    #   + 2 + i32(frames) + 2 + data
    blob = (b"tPxD" + bytes([38]) + b"c" * 37 + b"\0\0"
            + struct.pack("<i", 117600) + b"\0\0" + bytes(300))
    sess = pxd32d5.Session(header=blob, stream_end=66761)
    pxd32d5.engine._parse_header(sess)
    assert sess.stream_type == 1
    assert sess.read_offset == 50
    assert sess.has_riff is False
    # AWaveDauer: 4 * 117600, i.e. 44.1 kHz stereo 16 bit bytes
    path = os.path.join(tmp, "tp.pxd")
    with open(path, "wb") as fh:
        fh.write(blob)
    assert pxd32d5.awave_dauer(path) == 470400


def test_pxd_comment(tmp):
    # "tPxD" + len (counts itself) + text + NUL, then 00 54 + i32 frames
    text = b"Peel off\r\n001\r\nRave eJay\r\n\r\nhyper\r\n58800"
    head = (b"tPxD" + bytes([len(text) + 2]) + text + b"\x00"
            + b"\x00\x54" + struct.pack("<i", 14700) + b"\x00\x00")
    comment = pxd32d5.parse_pxd_comment(head)
    assert comment.length == len(text) + 2 == 42
    assert comment.text == text.decode("ascii")
    assert comment.lines == ("Peel off", "001", "Rave eJay", "", "hyper",
                             "58800")

    src = fixture("hyper-test.pxd")
    if os.path.exists(src):
        with open(src, "rb") as fh:
            real = pxd32d5.parse_pxd_comment(fh.read())
        assert real == comment

    def fails(blob):
        try:
            pxd32d5.parse_pxd_comment(blob)
        except pxd32d5.PxdCommentError:
            return True
        return False

    assert fails(b"")                                  # too short
    assert fails(b"tPxD")                              # too short
    assert fails(b"RIFF" + bytes([4]) + b"ab")         # wrong magic
    assert fails(b"tPxD" + bytes([0]))                 # length too small
    assert fails(b"tPxD" + bytes([1]) + b"\x00")       # length too small
    assert fails(b"tPxD" + bytes([10]) + b"abc")       # truncated
    assert fails(b"tPxD" + bytes([5]) + b"abcX")       # no NUL
    assert fails(b"tPxD" + bytes([3]) + b"\xff\x00")   # not ASCII
    assert fails(b"tPxD" + bytes([5]) + b"a\x00b\x00")  # embedded NUL


def test_tp_delta_table(tmp):
    t = pxd32d5.DELTA_TABLE
    assert len(t) == 256
    assert t[128] == 0 and t[127] == -2 and t[129] == 2
    assert max(t) == 25266 and min(t) == -25266
    assert t[0] == 0                            # mirrors the never-written [256]
    assert t[1:128] == [-x for x in reversed(t[129:256])]


def test_tp_decode_synthetic(tmp):
    # payload: upload entry 1 = [T[0x80]=0, T[0x81]=2], play it, one 0xFF
    # step with T[0x82]=4, then play entry 1 again.
    # the integrator carries over, and gain = (512 * 0x10000) >> 8 = 131072
    # so every step is doubled: acc 0 -> 0, 2 -> 4, 2 -> 4, 4 -> 8, 8 -> 16
    payload = bytes([0xF5, 0x01, 0x80, 0x81,    # upload entry 1 = [0, 2]
                     0x01,                    # play entry 1  -> 0, 4
                     0xFF, 0x82,              # one T[0x82]=4 step -> 16
                     0x01])                   # (cut: only 5 samples fit)
    # header: magic, h[4]=len (counted from offset 4), len-1 comment bytes,
    # 2 bytes, i32 frames, 2 bytes -> data at 4 + len + 8 = 16
    hdr = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
           + struct.pack("<i", 5) + b"\0\0")
    src = os.path.join(tmp, "syn.pxd")
    with open(src, "wb") as fh:
        fh.write(hdr + payload + bytes(300))
    out = os.path.join(tmp, "syn.wav")
    eg = new_engine()
    assert eg.RWavToTemp(src, out, 0, None, 0, 0, 0) == 0
    w = read_wav(out)
    assert w["size"] == 10, w["size"]
    assert w["samples"] == [0, 4, 4, 8, 16], w["samples"]


def test_tp_real_files(tmp):
    # both files decode to exactly the frame count declared in their header
    # and consume the input to the last byte
    expected = {
        "bo-test.pxd": (117600, -14008, 14064, -299552, 1903315181888),
        "hyper-test.pxd": (14700, -12604, 12588, -2385408, 307018638208),
    }
    for name, (frames, lo, hi, total, sq) in expected.items():
        src = fixture(name)
        if not os.path.exists(src):
            continue
        out = os.path.join(tmp, name + ".wav")
        eg = new_engine()
        assert eg.RWavToTemp(src, out, 0, None, 0, 0, 0) == 0
        w = read_wav(out)
        s = w["samples"]
        assert w["size"] == 2 * frames, (name, w["size"])
        assert len(s) == frames
        assert eg.session.read_offset == eg.stream_size
        assert (min(s), max(s)) == (lo, hi), (name, min(s), max(s))
        assert (sum(s), sum(v * v for v in s)) == (total, sq), name


def test_pplay_queue(tmp):
    eg = new_engine()
    assert eg.magic == pxd32d5.INIT_MAGIC
    voice = eg.voices[3]
    assert voice.write_index == 0
    # a9/a10/a11 round down to 4-byte units; a2/a3 pair up; a6 = file mode
    assert eg.APlay(0x1234, 7, 0, 0x40, 0x80, pxd32d5.PLAY_MODE_FILE,
                    "song.pxd", 3, 0x1000000A, 0x50, 0x80, 0x2000) == 0
    slot = voice.slots[0]
    assert slot.marker == 0x1234
    assert slot.primary == 7 and slot.secondary == 7     # a3 == 0 -> a3 = a2
    assert slot.length == 0x40 and slot.offset == 0x80
    assert slot.source == pxd32d5.PLAY_MODE_FILE
    assert slot.name == "song.pxd"
    assert slot.flags == 0x10000008                      # 0x1000000A & ~3
    assert slot.start == 0x10000058                      # flags + (0x50 & ~3)
    assert slot.duration == 0x80
    assert slot.extra == 0x2000
    assert voice.write_index == 1

    # a start time of 0 (the mask clears the low bits) becomes the sentinel
    eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, "b.pxd",
             3, 0, 2, 0, 0)
    assert voice.slots[1].start == pxd32d5.PLAY_START_SENTINEL
    assert voice.write_index == 2

    # the 30-slot ring wraps and reuses the oldest entry
    for _ in range(pxd32d5.SLOTS_PER_VOICE):
        eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, "n.pxd",
                 3, 0, 4, 0, 0)
    assert voice.write_index == 2                        # (2 + 30) % 30
    assert voice.slots[2].name == "n.pxd"


def test_aply_guard(tmp):
    eg = pxd32d5.Engine()                                # magic == 0
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, "x.pxd",
                    0, 0, 0, 0, 0) == 0
    assert eg.voices[0].write_index == 0                 # nothing enqueued
    assert eg.voices[0].slots[0].name == ""
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, "x.pxd",
                    999, 0, 0, 0, 0) == 0                # bad voice: no crash
    assert eg.voices[0].write_index == 0


def test_pplay_wrapper(tmp):
    pxd32d5.PInit(1.0)
    assert pxd32d5.PPlay("wrap.pxd", 5, 1, 2, 3, 4) == 0
    slot = pxd32d5.engine.voices[5].slots[0]
    assert slot.name == "wrap.pxd"
    assert slot.source == pxd32d5.PLAY_MODE_FILE
    assert slot.flags == 0                               # a9 = 1 -> & ~3
    assert slot.start == pxd32d5.PLAY_START_SENTINEL     # a10 = 2 -> 0
    assert slot.duration == 0                            # a11 = 3 -> 0
    assert slot.extra == 4
    pxd32d5.PClose()


def test_astop_recovered(tmp):
    eg = new_engine()
    eg.dword_10082BEC = 5
    eg.dword_10096D88 = 2
    assert eg.AStop() == 1                               # returns 1, not status
    assert eg.dword_10082BEC == 0
    assert eg.dword_10096D88 == 1                        # "reset playback" cmd
    assert eg.dword_10093A7C == 0 and eg.dword_1008E63C == 0


def test_guards_and_teardown(tmp):
    eg = pxd32d5.Engine()
    assert eg.RWavToTemp("x.wav", "out.wav", 0, None, 0, 0, 0) == 0  # not started
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    assert eg.RWavToTemp(None, "out.wav", 0, None, 0, 0, 0) == 0
    assert eg.RWavToTemp("", "out.wav", 0, None, 0, 0, 0) == 0
    assert eg.RWavToTemp(os.path.join(tmp, "nope.wav"), "out.wav", 0,
                         None, 0, 0, 0) == 1
    assert eg.started is True
    eg.AStop()
    assert eg.AEnd() == eg.status
    assert eg.started is False


def test_cli(tmp):
    import pxd2wav
    outdir = os.path.join(tmp, "cli")
    src = make_wav(os.path.join(tmp, "cli.wav"), 4410)
    assert pxd2wav.main([src, "-o", outdir]) == 0
    dst = os.path.join(outdir, "cli.wav")
    w = read_wav(dst)
    assert w["size"] == 8820 and w["total"] == 8864
    assert pxd2wav.main([src, "-o", outdir]) == 1          # refuses overwrite
    assert pxd2wav.main([src, "-o", outdir, "-f"]) == 0
    assert pxd2wav.main([src, "-o", outdir, "--raw", "-f"]) == 0
    assert os.path.getsize(os.path.join(outdir, "cli.pcm")) == 8820
    assert pxd2wav.main([os.path.join(tmp, "nope.wav"), "-o", outdir]) == 1
    if os.path.exists(fixture("bo-test.pxd")):
        assert pxd2wav.main([fixture("bo-test.pxd"), "-o", outdir, "-f"]) == 0
        assert os.path.getsize(os.path.join(outdir, "bo-test.wav")) == 235244


def test_pxdplay_cli(tmp):
    # the playback demo is checked on its error paths only: the happy path
    # needs a device (see docs/PLAYBACK.md section 3).
    import pxdplay
    assert pxdplay.main([os.path.join(tmp, "nope.pxd")]) == 1
    bad = os.path.join(tmp, "bad.pxd")
    with open(bad, "wb") as fh:
        fh.write(b"junk" * 100)
    assert pxdplay.main([bad]) == 1
    try:
        pxdplay.main([])
    except SystemExit as exc:
        assert exc.code == 2, exc.code       # argparse: INPUT is required
    else:
        raise AssertionError("a missing INPUT must exit")


def test_exports(tmp):
    # module level wrappers use the process wide engine
    pxd32d5.PInit(1.0)
    assert pxd32d5.engine.started is True
    pxd32d5.PClose()
    assert pxd32d5.engine.started is False
    assert pxd32d5.engine.wave_param[60] == 32000


def _unity_decode(path):
    """Decode ``path`` with the playback gain (pan 256 => unchanged)."""
    src = open(path, "rb").read()
    sess = pxd32d5.Session()
    sess.src = src
    sess.header = src[:220]
    sess.stream_end = len(src)
    sess.read_offset = 0
    sess.volume = 0x10000
    sess.pan = 256
    eg = pxd32d5.Engine()
    eg._parse_header(sess)
    buf = bytearray(4 * 40000 + 4096)
    pos = 0
    while sess.read_offset < sess.stream_end:
        produced = eg._decode_block(sess, buf, pos, 18908)
        if not produced:
            break
        pos += produced
    samples = array.array("h")
    samples.frombytes(bytes(buf[:pos]))
    return list(samples[0::2])


def _play(tmp, name, pcm_name, start, end):
    """Queue one file on voice 0, run the pump, return the PCM bytes."""
    pcm = os.path.join(tmp, pcm_name)
    eg = pxd32d5.Engine()
    eg.autostart_thread = False
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.sink = pxdsink.FileSink(pcm)
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, name,
                    0, start, 0, end, 0) == 0
    eg.AStart()
    assert eg.wait_for_end(10) is True
    eg.sink.close()
    with open(pcm, "rb") as fh:
        data = fh.read()
    eg.AStop()
    eg.AEnd()
    return data


def test_playback_tp_fixture(tmp):
    src = fixture("hyper-test.pxd")
    if not os.path.exists(src):
        return
    data = _play(tmp, src, "play_hyper.raw", 0, 4 * 14700)
    assert len(data) == 4 * 14700, len(data)
    pcm = array.array("h")
    pcm.frombytes(data)
    left = list(pcm[0::2])
    right = list(pcm[1::2])
    assert left == right                      # sub_10016325 duplicated L->R
    ref = _unity_decode(src)                  # exact unity-gain decode
    # the decoder can stop one frame short of the declared count; the ring
    # tail is already zero, so playback is padded to the header count
    assert left[:len(ref)] == ref
    assert all(v == 0 for v in left[len(ref):])
    assert min(left) == -6302 and max(left) == 6294


def test_playback_synthetic_tp(tmp):
    payload = bytes([0xF5, 0x01, 0x80, 0x81, 0x01, 0xFF, 0x82, 0x01])
    hdr = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
           + struct.pack("<i", 5) + b"\0\0")
    src = os.path.join(tmp, "play_syn.pxd")
    with open(src, "wb") as fh:
        fh.write(hdr + payload + bytes(300))
    data = _play(tmp, src, "play_syn.raw", 0, 20)
    assert len(data) == 20, len(data)
    pcm = array.array("h")
    pcm.frombytes(data)
    # pan 256 -> unity, not RWavToTemp's pan 512 (which doubles)
    assert list(pcm[0::2]) == [0, 2, 2, 4, 8], list(pcm[0::2])
    assert list(pcm[1::2]) == [0, 2, 2, 4, 8]


def test_playback_mixes_voices(tmp):
    payload = bytes([0xF5, 0x01, 0x80, 0x81, 0x01, 0xFF, 0x82, 0x01])
    hdr = (b"tPxD" + bytes([4]) + b"abc" + b"\0\0"
           + struct.pack("<i", 5) + b"\0\0")
    src = os.path.join(tmp, "mix.pxd")
    with open(src, "wb") as fh:
        fh.write(hdr + payload + bytes(300))
    pcm_path = os.path.join(tmp, "mix.raw")
    eg = pxd32d5.Engine()
    eg.autostart_thread = False
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.sink = pxdsink.FileSink(pcm_path)
    for voice in (0, 1):
        assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, src,
                        voice, 0, 0, 20, 0) == 0
    eg.AStart()
    assert eg.wait_for_end(10) is True
    eg.sink.close()
    pcm = array.array("h")
    pcm.frombytes(open(pcm_path, "rb").read())
    # two voices of [0, 2, 2, 4, 8] at unity gain
    assert list(pcm[0::2]) == [0, 4, 4, 8, 16], list(pcm[0::2])
    assert list(pcm[1::2]) == [0, 4, 4, 8, 16]
    eg.AStop()
    eg.AEnd()


def test_playback_pause_resume(tmp):
    src = fixture("bo-test.pxd")
    if not os.path.exists(src):
        return
    pcm_path = os.path.join(tmp, "pause.raw")
    eg = pxd32d5.Engine()
    eg.autostart_thread = False
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.sink = pxdsink.FileSink(pcm_path)
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, src,
                    0, 0, 0, 470400, 0) == 0
    eg.AStart()
    eg.pump(1)
    eg.sink.flush()
    first = os.path.getsize(pcm_path)
    assert first > 0
    assert eg.RWavePause1() == 1
    eg.pump(3)
    eg.sink.flush()
    assert os.path.getsize(pcm_path) == first
    assert eg.RWavePause2() == 1
    eg.pump(1)
    eg.sink.flush()
    assert os.path.getsize(pcm_path) > first
    eg.sink.close()
    eg.RWaveStop()
    assert eg.word_10096E04 == 0 and eg.word_10083528 == 0
    eg.AEnd()


def test_playback_thread(tmp):
    src = fixture("hyper-test.pxd")
    if not os.path.exists(src):
        return
    pcm_path = os.path.join(tmp, "thread.raw")
    eg = pxd32d5.Engine()                 # autostart_thread stays True
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.sink = pxdsink.FileSink(pcm_path)
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, src,
                    0, 0, 0, 58800, 0) == 0
    eg.AStart()
    deadline = time.monotonic() + 5.0
    while not eg.word_10083528 and time.monotonic() < deadline:
        time.sleep(0.01)
    eg.sink.close()
    assert eg.word_10083528 == 1
    assert os.path.getsize(pcm_path) == 58800
    eg.AStop()
    eg.AEnd()
    assert eg._thread is None


def test_playback_start_positions(tmp):
    # APlay's a9/a11 are ring positions: re-queueing mid-playback must write
    # into the live part of the ring, not replay from zero.
    src = fixture("hyper-test.pxd")
    if not os.path.exists(src):
        return
    pcm_path = os.path.join(tmp, "pos.raw")
    eg = pxd32d5.Engine()
    eg.autostart_thread = False
    eg.ADevice(0)
    eg.AInit(1.0, 0)
    eg.sink = pxdsink.FileSink(pcm_path)
    eg.AStart()
    eg.pump(1)
    pos = eg.dword_1008E414
    assert pos > 0
    assert eg.APlay(0, 0, 0, 0, 0, pxd32d5.PLAY_MODE_FILE, src,
                    0, pos, 0, pos + 58800, 0) == 0
    assert eg.wait_for_end(10) is True
    eg.sink.close()
    assert os.path.getsize(pcm_path) == pos + 58800
    eg.AStop()
    eg.AEnd()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn(tmp)
                print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
