import struct, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
K, K2 = 0.52, 0.00022
W = [0] * 0x81; v, r = 2.1, R0
for i in range(1, 0x80):
    W[i] = W[i-1] + 1 if i < 6 else int(W[i-1] + v - K); v *= r; r -= K2
D = [0] * 256
for i in range(1, 0x81): D[0x80-i] = -W[i]
for j in range(0x80): D[0x80+j] = W[j]


def parse(path):
    raw = open(path, "rb").read(); b = raw[4]; p = 4+b+2
    L = struct.unpack_from("<I", raw, p)[0]
    seed = struct.unpack_from("<h", raw, p+4)[0]
    return (L << 1) & 0xFFFFFFFF, seed, raw[p+6:]


def decode(stream, seed, mode):
    wrapbits, shift, sat = mode
    mask = (1 << wrapbits)-1; sb = 1 << (wrapbits-1)
    cur = seed; T1 = [0]*256; T2 = [0]*256; out = []; i = 0; n = len(stream)
    lim = sb-1
    def upd(x):
        if sat:
            return -lim if x < -lim else (lim if x > lim else x)
        x &= mask
        return x-(1 << wrapbits) if x >= sb else x
    while i < n:
        op = stream[i]; i += 1
        if op == 0:
            s = cur << shift
            out.extend([s]*5)
        elif op == 0xF5:
            sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
            T1[sel] = v1; T2[sel] = v2
            cur = upd(cur+D[v1]); out.append(cur << shift)
            cur = upd(cur+D[v2]); out.append(cur << shift)
        else:
            cur = upd(cur+D[T1[op]]); out.append(cur << shift)
            cur = upd(cur+D[T2[op]]); out.append(cur << shift)
    return np.array(out[: (len(stream)*2)], dtype=np.float64)


for name in ("bo-test.pxd", "hyper-test.pxd"):
    data_bytes, seed, stream = parse(os.path.join(HERE, "../../historical", name))
    print("===", name, "declared samples", data_bytes//2)
    for label, mode in [("wrap16<<2", (16,2,False)), ("sat8191<<2", (14,2,True)),
                        ("wrap14<<2", (14,2,False)), ("wrap16 no-shift", (16,0,False)),
                        ("wrap16<<1", (16,1,False))]:
        x = decode(stream, seed, mode)[: data_bytes//2]
        x = x - x.mean()
        if len(x) > 65536:
            x = x[len(x)//2-32768: len(x)//2+32768]
        n = 4096
        seg = x[:n]*np.hanning(n)
        sp = np.abs(np.fft.rfft(seg))**2
        fr = np.fft.rfftfreq(n, 1/44100)
        centroid = (sp*fr).sum()/sp.sum()
        hf = sp[fr > 6000].sum()/sp.sum()
        print("   %-16s centroid=%6.0f Hz  HF>6k=%.3f  maxabs=%d" % (label, centroid, hf, int(np.abs(x).max())))
