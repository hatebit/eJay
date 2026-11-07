import struct, os, array
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()


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


def r8(va):
    return d[r2o(va - 0x10000000)]


K = struct.unpack("<d", d[r2o(0x432E8):r2o(0x432E8) + 8])[0]
K2 = struct.unpack("<d", d[r2o(0x432E0):r2o(0x432E0) + 8])[0]
R0 = struct.unpack("<d", d[r2o(0x432D8):r2o(0x432D8) + 8])[0] if False else None
# find the r0 double: the code loads [ebp-8]=0x8b439581, [ebp-4]=0x3ff0e76c
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
print("K", K, "K2", K2, "R0", R0)


def build(variant):
    W = [0] * 0x81
    v, r = 2.1, struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
    for i in range(1, 0x80):
        if i < 6:
            W[i] = W[i - 1] + 1
        else:
            W[i] = int(W[i - 1] + v - K)
        v = v * r
        r = r - K2
    D = [0] * 256
    for i in range(1, 0x81):
        D[0x80 - i] = -W[i]
    for j in range(0x80):
        D[0x80 + j] = W[j]
    return D, W


def parse(path):
    raw = open(path, "rb").read()
    b = raw[4]
    p = 4 + b + 2
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p + 4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p + 6:]


D, W = build(0)
print("W[0x7F]", W[0x7F])


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


def decode(path, scale=2, swap=False, wrapbits=16):
    data_bytes, seed, stream = parse(path)
    cur = seed
    T1 = [0] * 256; T2 = [0] * 256
    out = []; i = 0; n = len(stream)
    maxcur = 0
    mask = (1 << wrapbits) - 1
    sign = 1 << (wrapbits - 1)
    def upd(x):
        x &= mask
        return x - (1 << wrapbits) if x >= sign else x
    while i < n:
        op = stream[i]; i += 1
        if op == 0:
            for _ in range(5):
                out.append((cur * (1 << scale)) & 0xFFFF)
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel] = v1; T2[sel] = v2
            a, bb = (v2, v1) if swap else (v1, v2)
            cur = upd(cur + D[a]); out.append((cur * (1 << scale)) & 0xFFFF)
            cur = upd(cur + D[bb]); out.append((cur * (1 << scale)) & 0xFFFF)
        else:
            a, bb = (T2[op], T1[op]) if swap else (T1[op], T2[op])
            cur = upd(cur + D[a]); out.append((cur * (1 << scale)) & 0xFFFF)
            cur = upd(cur + D[bb]); out.append((cur * (1 << scale)) & 0xFFFF)
        maxcur = max(maxcur, abs(cur))
    out = out[: data_bytes // 2]
    return out, maxcur


for scale in (2, 0):
    for swap in (False, True):
        out, maxcur = decode(os.path.join(HERE, "../../historical", "bo-test.pxd"), scale=scale, swap=swap)
        a = array.array("h", struct.pack("<%dH" % len(out), *[x & 0xFFFF for x in out]))
        diffs = sorted(abs(a[k+1]-a[k]) for k in range(len(a)-1))
        big = sum(1 for x in diffs if x > 4000)
        print("scale=%d swap=%s  max|cur|=%d  len=%d  mean|d|=%.1f  median|d|=%d  big(>4000)=%d (%.2f%%)" % (
            scale, swap, maxcur, len(out), sum(diffs)/len(diffs), diffs[len(diffs)//2], big, 100*big/len(diffs)))
