import struct, os
from collections import Counter
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


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


for name in ("bo-test.pxd", "hyper-test.pxd"):
    raw = open(os.path.join(HERE, "../../historical", name), "rb").read()
    print("===", name)
    for start in range(44, 60):
        stream = raw[start:]
        cur = 0
        T1 = [0] * 256; T2 = [0] * 256
        i = 0; n = len(stream); mx = 0; maxop = 0; bad = 0
        ok = True
        while i < n:
            op = stream[i]; i += 1
            if op == 0:
                pass
            elif op == 0xF5:
                if i + 3 > n:
                    break
                sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
                T1[sel] = v1; T2[sel] = v2
                cur = s16(cur + D[v1]); cur = s16(cur + D[v2])
            else:
                maxop = max(maxop, op)
                if op > 0xF3:
                    bad += 1
                cur = s16(cur + D[T1[op]]); cur = s16(cur + D[T2[op]])
            mx = max(mx, abs(cur))
        tag = "OK " if mx <= 9000 else "   "
        print("  %sstart=%d seed=%d  max|cur|=%5d  maxop=%3d  ops>0xF3=%d" % (
            tag, start, struct.unpack_from("<h", raw, start - 2)[0] if start >= 2 else -1, mx, maxop, bad))
