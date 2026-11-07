import struct, os
HERE = os.path.dirname(os.path.abspath(__file__))

K = 0.52
K2 = 0.00022
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]


def ladder():
    W = [0] * 0x81
    v, r = 2.1, R0
    for i in range(1, 0x80):
        W[i] = W[i-1] + 1 if i < 6 else int(W[i-1] + v - K)
        v *= r
        r -= K2
    D = [0] * 256
    for i in range(1, 0x81):
        D[0x80 - i] = -W[i]
    for j in range(0x80):
        D[0x80 + j] = W[j]
    return D


def parse(path, off_bias=0):
    raw = open(path, "rb").read()
    b = raw[4]
    p = 4 + b + 2 + off_bias
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p + 4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p + 6:]


def run(stream, seed, D, wrapbits, sign, swap, seedscale, stopbits):
    mask = (1 << wrapbits) - 1
    sign_bit = 1 << (wrapbits - 1)
    def upd(x):
        x &= mask
        return x - (1 << wrapbits) if x >= sign_bit else x
    cur = seed * seedscale
    T1 = [0] * 256; T2 = [0] * 256
    i = 0; n = len(stream); mx = 0
    while i < n:
        op = stream[i]; i += 1
        if op == 0x00:
            pass
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel] = v1; T2[sel] = v2
            a, b2 = (v2, v1) if swap else (v1, v2)
            cur = upd(cur + sign * D[a]); cur = upd(cur + sign * D[b2])
        else:
            a, b2 = (T2[op], T1[op]) if swap else (T1[op], T2[op])
            cur = upd(cur + sign * D[a]); cur = upd(cur + sign * D[b2])
        if abs(cur) > mx:
            mx = abs(cur)
    return mx


base = ladder()
for name in ("bo-test.pxd", "hyper-test.pxd"):
    path = os.path.join(HERE, "../../historical", name)
    print("===", name)
    for wrap in (16, 14, 13):
        for sign in (1, -1):
            for swap in (False, True):
                mx = run(parse(path)[2], parse(path)[1], base, wrap, sign, swap, 1, 1)
                tag = "OK " if mx <= 9000 else "   "
                print("  %swrap=%2d sign=%+d swap=%d  max|cur|=%d" % (tag, wrap, sign, swap, mx))
