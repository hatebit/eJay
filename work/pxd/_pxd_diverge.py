import struct, os
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


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


path = os.path.join(HERE, "../../historical", "bo-test.pxd")
data_bytes, seed, stream = parse(path)
cur = seed
T1 = [0] * 256; T2 = [0] * 256
i = 0; n = len(stream)
first = None
count_over = 0
ops_at_div = None
while i < n:
    op = stream[i]; i += 1
    if op == 0:
        pass
    elif op == 0xF5:
        sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
        T1[sel] = v1; T2[sel] = v2
        cur = s16(cur + D[v1])
        if abs(cur) > 8192 and first is None:
            first = (i-4, op, sel, v1, v2, cur)
        cur = s16(cur + D[v2])
    else:
        cur = s16(cur + D[T1[op]])
        if abs(cur) > 8192 and first is None:
            first = (i-1, op, T1[op], T2[op], None, cur)
        cur = s16(cur + D[T2[op]])
    if abs(cur) > 8192:
        count_over += 1
print("stream len", n, "first over-8192:", first)
print("iterations where |cur|>8192:", count_over)

# look at the raw bytes at the first divergence
if first:
    idx = first[0]
    print("bytes around idx", idx, ":", stream[max(0,idx-6):idx+10].hex())

# how many distinct op values appear, and how many are trained
from collections import Counter
c = Counter()
i = 0
while i < n:
    op = stream[i]; i += 1
    if op == 0xF5:
        i += 3
        c["F5"] += 1
    else:
        c[op] += 1
print("top ops:", c.most_common(12))
