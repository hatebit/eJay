import struct, os
HERE = os.path.dirname(os.path.abspath(__file__))
R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
K, K2 = 0.52, 0.00022
W = [0]*0x81; v, r = 2.1, R0
for i in range(1, 0x80):
    W[i] = W[i-1]+1 if i < 6 else int(W[i-1]+v-K); v *= r; r -= K2
D = [0]*256
for i in range(1, 0x81): D[0x80-i] = -W[i]
for j in range(0x80): D[0x80+j] = W[j]


def trial(st, start, teach_len, zero_len):
    T1 = [0]*256; T2 = [0]*256; i = start; n = len(st)
    trained = [False]*256
    plains = 0; untrained_after = 0; taught = 0; mx = 0; cur = 0
    def s16(x):
        x &= 0xFFFF
        return x-0x10000 if x >= 0x8000 else x
    while i < n:
        op = st[i]; i += 1
        if op == 0x00:
            i += zero_len
        elif op == 0xF5:
            if i + teach_len > n: break
            sel = st[i]; v1 = st[i+1]; v2 = st[i+2]
            i += teach_len
            T1[sel] = v1; T2[sel] = v2; trained[sel] = True
            cur = s16(cur+D[v1]); cur = s16(cur+D[v2]); taught += 1
        else:
            plains += 1
            if taught > 0 and not trained[op]:
                untrained_after += 1
            cur = s16(cur+D[T1[op]]); cur = s16(cur+D[T2[op]])
        mx = max(mx, abs(cur))
    frac = (untrained_after/plains) if plains else 0
    return frac, mx, taught, plains


for name in ("bo-test.pxd", "hyper-test.pxd"):
    raw = open(os.path.join(HERE, "../../historical", name), "rb").read()
    b = raw[4]; p = 4+b+2
    st = raw[p+6:]
    print("===", name)
    for start in range(0, 4):
        for tl in (3, 4):
            for zl in (0, 1):
                fr, mx, taught, plains = trial(st, start, tl, zl)
                tag = "OK " if fr < 0.02 else "   "
                print("   %sstart=%d teach_len=%d zero_len=%d  untrained_frac=%.4f  taught=%d plains=%d max|cur|=%d" % (
                    tag, start, tl, zl, fr, taught, plains, mx))
