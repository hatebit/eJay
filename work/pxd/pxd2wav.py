#!/usr/bin/env python3
"""pxd2wav.py - decode an eJay 'tPxD' sample into a WAV file.

Pure-Python reimplementation of the PXD -> WAV path of Dance eJay3's
pxd32d5.dll (build D4).  See PXD32D5-D4-pxd2wav.md for the evidence trail.

The codec is validated by an encoder/decoder round-trip (_pxd_roundtrip.py).
Note: the two bundled `../*-test.pxd` files are NOT output of this DLL's
encoder (they use opcode 0xFF and leave 10-38%% of opcodes untaught), so this
decoder produces a random walk on them; see ongoing.md section 9.

Usage:
    python pxd2wav.py input.pxd output.wav
    python pxd2wav.py sample.pxd            # -> sample.wav next to the input
"""
import struct
import sys
import os

# --- constants lifted from the DLL's table builder (0x1000FFD7) -------------
K = 0.52                                    # double @ 0x100432E8
K2 = 0.00022                                # double @ 0x100432E0
V0 = 2.1                                    # double @ [ebp-0x20] = 0x400199999999999A
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]   # ~1.056840


def build_delta_table():
    """The int16 delta ladder D[256] at 0x1004E2D0."""
    W = [0] * 0x81
    v, r = V0, R0
    for i in range(1, 0x80):
        if i < 6:
            W[i] = W[i - 1] + 1
        else:
            W[i] = int(W[i - 1] + v - K)     # __ftol(W[i-1] + v - K)
        v = v * r
        r = r - K2
    D = [0] * 256
    for i in range(1, 0x81):
        D[0x80 - i] = -W[i]                  # negative half
    for j in range(0x80):
        D[0x80 + j] = W[j]                   # positive half (W[0x80] unused)
    return D


DELTA = build_delta_table()


def _s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def parse_tpxd(raw):
    """Split a tPxD file: returns (data_bytes, seed, op_stream)."""
    if raw[:4] != b"tPxD":
        raise ValueError("not a tPxD file (bad magic)")
    attr = raw[4]
    p = 4 + attr + 2
    length = struct.unpack_from("<I", raw, p)[0]
    data_bytes = (length << 1) & 0xFFFFFFFF      # WAV 'data' chunk size
    p += 4
    seed = struct.unpack_from("<h", raw, p)[0]   # first sample, stored directly
    p += 2
    return data_bytes, seed, raw[p:]


def decode(raw):
    """Decode a tPxD byte string to (pcm_bytes, data_bytes).

    pcm_bytes is exactly data_bytes long (mono, 16-bit, little-endian).  The
    first sample is the header seed; the op stream then appends 2 samples per
    opcode (5 for the 0x00 run opcode) over its whole length.  The DLL decodes
    the entire stream into a file mapping and only then writes `data_bytes + 44`
    bytes to disk, so the WAV data chunk is the first `data_bytes` bytes of the
    decoded stream (the tail, if any, is discarded).
    """
    data_bytes, seed, stream = parse_tpxd(raw)
    out = bytearray()
    out += struct.pack("<H", (seed << 2) & 0xFFFF)      # seed is sample 0
    cur = seed
    T1 = [0] * 256
    T2 = [0] * 256
    i = 0
    n = len(stream)

    def emit():
        out.append(((cur << 2) & 0xFFFF) & 0xFF)
        out.append((((cur << 2) & 0xFFFF) >> 8) & 0xFF)

    while i < n:
        op = stream[i]
        i += 1
        if op == 0x00:
            for _ in range(5):          # run opcode: five copies of the value
                emit()
        elif op == 0xF5:                # teach opcode: 0xF5 sel v1 v2
            sel = stream[i]
            v1 = stream[i + 1]
            v2 = stream[i + 2]
            i += 3
            T1[sel] = v1
            T2[sel] = v2
            cur = _s16(cur + DELTA[v1])
            emit()
            cur = _s16(cur + DELTA[v2])
            emit()
        else:                           # plain opcode: two samples of one frame pair
            cur = _s16(cur + DELTA[T1[op]])
            emit()
            cur = _s16(cur + DELTA[T2[op]])
            emit()

    return bytes(out[:data_bytes]), data_bytes


def wav_header(data_len):
    """The exact byte map pxd32d5.dll writes at 0x1000F825 (mono/16/44.1k).

    Standard RIFF/WAVE: the 4-byte fmt chunk size at 16 is 16, so the fmt
    fields begin at 20 (wFormatTag, nChannels), the rate at 24, the byte rate
    at 28, the block align at 32 and the bit depth at 34.
    """
    h = bytearray()
    h += b"RIFF"
    h += struct.pack("<I", data_len + 0x24)     # RIFF size = data + 36
    h += b"WAVE"
    h += b"fmt "
    h += struct.pack("<H", 0x10)                # fmt chunk size
    h += struct.pack("<H", 0x0000)              # (wFormatTag slot, written 0)
    h += struct.pack("<H", 0x0001)              # 20: format tag (PCM)  [read at +0x14]
    h += struct.pack("<H", 0x0001)              # 22: channels (mono)   [read at +0x16]
    h += struct.pack("<I", 44100)               # 24: sample rate       [read at +0x18]
    h += struct.pack("<I", 88200)               # 28: byte rate  (44100 * blockAlign)
    h += struct.pack("<H", 0x0002)              # 32: block align
    h += struct.pack("<H", 0x0010)              # 34: bits per sample   [read at +0x22]
    h += b"data"
    h += struct.pack("<I", data_len)            # data chunk size
    return bytes(h)


def pxd_to_wav(raw):
    pcm, data_len = decode(raw)
    return wav_header(data_len) + pcm


def main(argv):
    if not 1 <= len(argv) <= 2:
        print(__doc__)
        return 2
    src = argv[0]
    dst = argv[1] if len(argv) == 2 else os.path.splitext(src)[0] + ".wav"
    raw = open(src, "rb").read()
    open(dst, "wb").write(pxd_to_wav(raw))
    data_len, seed, stream = parse_tpxd(raw)
    print("%s -> %s  (%d bytes PCM, %.3f s mono 16-bit 44.1 kHz)" % (
        src, dst, data_len, data_len / 2 / 44100))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
