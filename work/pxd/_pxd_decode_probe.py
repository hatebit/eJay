"""Probe: reimplement the pxd32d5_d4 'tPxD' -> WAV codec in pure Python.

Static analysis findings encoded here (see ongoing.md for the address trail):
  * loader  0x1000F115  - parses 'tPxD' header, sets data ptr / length / init
  * tables  0x1000FFD7  - builds the int16 delta ladder at 0x1004E2D0
  * decode  0x1000F825  - per-byte 2-sample loop, 0x00 = repeat x5, 0xF5 = teach
"""
import struct
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))

# --- read the two constants used by the ladder builder -----------------------
d = open(DLL, "rb").read()


def r2o(rva):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = pe + 24
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    sect = opt + optsz
    for i in range(nsec):
        o = sect + i * 40
        vsz, va, rsz, ra = struct.unpack_from("<IIII", d, o + 8)
        if va <= rva < va + max(vsz, rsz):
            return ra + (rva - va)
    return None


def rd_double(va):
    o = r2o(va - 0x10000000)
    return struct.unpack_from("<d", d, o)[0]


K = rd_double(0x100432E8)   # subtracted before truncation
K2 = rd_double(0x100432E0)  # decrement of the ratio
print("K =", repr(K), "K2 =", repr(K2))


def build_delta_table():
    """W[i] ladder, one int16 entry per opcode 0..255.

    entry[k] = -W[0x80-k]  for k <  0x80
    entry[0x80+j] = W[j]   for j >= 0
    """
    W = [0] * 0x81
    W[0] = 0
    v = 2.1
    r = 1.05684004  # placeholder; overwritten below from the DLL if present
    # the initial ratio is the double 0x3FF0E76C8B439581
    r = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
    for i in range(1, 0x80):
        if i < 6:
            W[i] = W[i - 1] + 1
        else:
            W[i] = int(W[i - 1] + v - K)
        v = v * r
        r = r - K2
    tbl = [0] * 256
    for i in range(1, 0x81):
        tbl[0x80 - i] = -W[i]
    for j in range(0, 0x80):
        tbl[0x80 + j] = W[j]
    return tbl, W


DELTA, W = build_delta_table()
print("W[0..16] =", W[:17])
print("W[0x7F] =", W[0x7F], " W[0x80] =", W[0x80])
print("delta[0x00..0x08] =", DELTA[0:9])
print("delta[0x7F..0x88] =", DELTA[0x7F:0x89])
print("delta[0xFF] =", DELTA[0xFF])


def parse_pxd(path):
    raw = open(path, "rb").read()
    if raw[0:4] != b"tPxD":
        raise ValueError("not a tPxD file")
    b = raw[4]
    p = 4 + b + 2
    length_field = struct.unpack_from("<I", raw, p)[0]
    out_bytes = (length_field << 1) & 0xFFFFFFFF
    p += 4
    init = struct.unpack_from("<h", raw, p)[0]
    p += 2
    stream = raw[p:]
    return dict(attr=b, out_bytes=out_bytes, init=init, stream=stream,
                data_off=p, filesize=len(raw))


def decode(pxd):
    stream = pxd["stream"]
    cur = pxd["init"]
    out = bytearray()
    T1 = [0] * 256
    T2 = [0] * 256
    i = 0
    n = len(stream)

    def emit(sample):
        # the DLL stores a 16-bit word: (cur<<2) truncated to 16 bits
        out.extend(struct.pack("<H", (sample << 2) & 0xFFFF))

    while i < n:
        b = stream[i]
        i += 1
        if b == 0x00:
            for _ in range(5):
                emit(cur)
        elif b == 0xF5:
            op = stream[i]; i += 1
            v1 = stream[i]; i += 1
            v2 = stream[i]; i += 1
            T1[op] = v1
            T2[op] = v2
            cur = (cur + DELTA[T1[op]]) & 0xFFFF
            cur = cur - 0x10000 if cur >= 0x8000 else cur
            emit(cur)
            cur = (cur + DELTA[T2[op]]) & 0xFFFF
            cur = cur - 0x10000 if cur >= 0x8000 else cur
            emit(cur)
        else:
            cur = (cur + DELTA[T1[b]]) & 0xFFFF
            cur = cur - 0x10000 if cur >= 0x8000 else cur
            emit(cur)
            cur = (cur + DELTA[T2[b]]) & 0xFFFF
            cur = cur - 0x10000 if cur >= 0x8000 else cur
            emit(cur)
    return bytes(out)


for name in ("bo-test.pxd", "hyper-test.pxd"):
    path = os.path.join(HERE, "../../historical", name)
    pxd = parse_pxd(path)
    dec = decode(pxd)
    print("---", name)
    print("  attr=%#x out_bytes=%d (%d samples) init=%d stream=%d filesize=%d" % (
        pxd["attr"], pxd["out_bytes"], pxd["out_bytes"] // 2, pxd["init"],
        len(pxd["stream"]), pxd["filesize"]))
    print("  decoded bytes=%d samples=%d  (declared samples=%d)" % (
        len(dec), len(dec) // 2, pxd["out_bytes"] // 2))
    smp = struct.unpack("<%dh" % min(16, len(dec) // 2), dec[:32])
    print("  first samples:", smp)
    # amplitude envelope
    import array
    a = array.array("h")
    a.frombytes(dec[: len(dec) // 2 * 2])
    print("  min=%d max=%d" % (min(a), max(a)))
