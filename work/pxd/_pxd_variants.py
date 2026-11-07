import struct, os, math, cmath
HERE = os.path.dirname(os.path.abspath(__file__))
K, K2 = 0.52, 0.00022
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
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


def parse(path):
    raw = open(path, "rb").read()
    b = raw[4]
    p = 4 + b + 2
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p + 4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p + 6:]


def decode(stream, seed, mode):
    # mode: (wrapbits, shift, saturate)
    wrapbits, shift, sat = mode
    mask = (1 << wrapbits) - 1
    sb = 1 << (wrapbits - 1)
    cur = seed
    T1 = [0] * 256; T2 = [0] * 256
    out = []; i = 0; n = len(stream)

    def upd(x):
        if sat:
            lim = sb - 1
            return -lim if x < -lim else (lim if x > lim else x)
        x &= mask
        return x - (1 << wrapbits) if x >= sb else x

    while i < n:
        op = stream[i]; i += 1
        if op == 0:
            s = (cur << shift)
            for _ in range(5):
                out.append(s)
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel] = v1; T2[sel] = v2
            cur = upd(cur + D[v1]); out.append(cur << shift)
            cur = upd(cur + D[v2]); out.append(cur << shift)
        else:
            cur = upd(cur + D[T1[op]]); out.append(cur << shift)
            cur = upd(cur + D[T2[op]]); out.append(cur << shift)
    return out


def flatness(sig):
    # spectral flatness over a 4096 window near the middle, on an int16 view
    N = 4096
    a = sig[len(sig)//2 - N//2: len(sig)//2 + N//2]
    if len(a) < N:
        return float("nan")
    ps = []
    for k in range(0, N, 4):
        re = 0.0; im = 0.0
        for n_, x in enumerate(a):
            ang = -2*math.pi*k*n_/N
            re += x*math.cos(ang); im += x*math.sin(ang)
        ps.append(re*re + im*im + 1e-9)
    gm = math.exp(sum(math.log(p) for p in ps)/len(ps))
    am = sum(ps)/len(ps)
    return gm/am


for name in ("bo-test.pxd", "hyper-test.pxd"):
    data_bytes, seed, stream = parse(os.path.join(HERE, "../../historical", name))
    print("===", name)
    for mode in [(16, 2, False), (16, 2, True), (14, 2, False), (15, 2, False),
                 (16, 1, False), (16, 1, True), (14, 2, True), (13, 2, False)]:
        out = decode(stream, seed, mode)
        out = out[:data_bytes//2]
        clip = sum(1 for x in out if x <= -32768 or x > 32767)
        mx = max(abs(x) for x in out)
        fl = flatness(out)
        print("   mode(wrap,shift,sat)=%s  max=%6d clip=%5d  flatness=%.4f" % (mode, mx, clip, fl))
