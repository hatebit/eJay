import struct, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
K, K2 = 0.52, 0.00022
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
W = [0] * 0x81
v, r = 2.1, R0
for i in range(1, 0x80):
    W[i] = W[i-1] + 1 if i < 6 else int(W[i-1] + v - K)
    v *= r; r -= K2
D = [0] * 256
for i in range(1, 0x81):
    D[0x80 - i] = -W[i]
for j in range(0x80):
    D[0x80 + j] = W[j]


def parse(path):
    raw = open(path, "rb").read()
    b = raw[4]; p = 4 + b + 2
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p + 4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p + 6:]


def decode(stream, seed, wrapbits=14, shift=2, sat=False):
    mask = (1 << wrapbits) - 1; sb = 1 << (wrapbits - 1)
    cur = seed; T1 = [0]*256; T2 = [0]*256; out = []; i = 0; n = len(stream)
    lim = sb - 1
    def upd(x):
        if sat:
            return -lim if x < -lim else (lim if x > lim else x)
        x &= mask
        return x - (1 << wrapbits) if x >= sb else x
    while i < n:
        op = stream[i]; i += 1
        if op == 0:
            s = cur << shift
            for _ in range(5): out.append(s)
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel] = v1; T2[sel] = v2
            cur = upd(cur + D[v1]); out.append(cur << shift)
            cur = upd(cur + D[v2]); out.append(cur << shift)
        else:
            cur = upd(cur + D[T1[op]]); out.append(cur << shift)
            cur = upd(cur + D[T2[op]]); out.append(cur << shift)
    return out


def spectrum_stats(sig, sr=44100):
    N = 8192
    a = sig[len(sig)//2: len(sig)//2 + N]
    if len(a) < N: return None
    a = [x - sum(a)/len(a) for x in a]          # remove DC
    win = [0.5 - 0.5*math.cos(2*math.pi*k/(N-1)) for k in range(N)]
    a = [a[k]*win[k] for k in range(N)]
    tot = 0.0; hi = 0.0; zc = 0
    for k in range(1, N//2):
        re = im = 0.0
        for n_ in range(0, N, 2):               # decimate for speed
            ang = -2*math.pi*k*n_/N
            re += a[n_]*math.cos(ang); im += a[n_]*math.sin(ang)
        p = re*re + im*im
        tot += p
        if k*sr/N > 6000: hi += p
    for k in range(1, N):
        if (a[k] >= 0) != (a[k-1] >= 0): zc += 1
    return hi/tot, zc/N


for name in ("bo-test.pxd", "hyper-test.pxd"):
    data_bytes, seed, stream = parse(os.path.join(HERE, "../../historical", name))
    for label, mode in [("wrap14 shift2", (14,2,False)), ("wrap14 shift2 sat", (14,2,True)),
                        ("wrap16 shift1", (16,1,False)), ("wrap13 shift2", (13,2,False))]:
        out = decode(stream, seed, *mode)[:data_bytes//2]
        st = spectrum_stats(out)
        if st: print("%-14s %-16s HF>6k=%.3f  ZCR=%.3f" % (name, label, st[0], st[1]))
    # stereo hypothesis: split even/odd
    out = decode(stream, seed, 14, 2, False)[:data_bytes//2]
    Lch = out[0::2]; Rch = out[1::2]
    d_mono = sum(abs(out[k+1]-out[k]) for k in range(0, min(len(out)-1, 40000)))
    d_L = sum(abs(Lch[k+1]-Lch[k]) for k in range(0, min(len(Lch)-1, 20000)))
    d_R = sum(abs(Rch[k+1]-Rch[k]) for k in range(0, min(len(Rch)-1, 20000)))
    print("   %-14s mono-consec=%.0f  withinL=%.0f  withinR=%.0f" % (name, d_mono/40000, d_L/20000, d_R/20000))
