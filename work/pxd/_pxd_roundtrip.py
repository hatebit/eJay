"""Implement the encoder from 0x1000FB3E and round-trip a known signal through
my decoder.  If the model is right, encode->decode reproduces the input."""
import struct, os, math
import numpy as np

R0 = struct.unpack("<d", struct.pack("<Q", 0x3FF0E76C8B439581))[0]
K, K2 = 0.52, 0.00022

W = [0] * 0x81
v, r = 2.1, R0
for i in range(1, 0x80):
    W[i] = W[i - 1] + 1 if i < 6 else int(W[i - 1] + v - K)
    v *= r
    r -= K2
D = [0] * 256
for i in range(1, 0x81):
    D[0x80 - i] = -W[i]
for j in range(0x80):
    D[0x80 + j] = W[j]

# quant table: Q[diff] = nearest k in 1..0xFE over the SIGNED ladder D[k]
# (the builder's nearest pass reads word[obj + 2k], i.e. D[k], not W[k])
Q = {}
k = 1
Dv = D[k]
for delta in range(-0x3FFF, 0x4000):
    if abs(D[k + 1] - delta) < abs(Dv - delta):
        k += 1
        Dv = D[k]
        if k == 0xFE:
            break
    Q[delta] = k
# diffs above the sweep / below: defaults
for delta in range(0x4000, 0x8000):
    Q.setdefault(delta, 0xFE)
for delta in range(-0x8000, -0x3FFF):
    Q.setdefault(delta, 0xFE)


def f66a(s):
    x = s * 2
    if x > 0x7FFC:
        x = 0x7FFC
    elif x < -0x7FFC:
        x = -0x7FFC
    else:
        x += 3
    return x >> 2


def f5c0(prev, nxt):
    diff = nxt - prev
    idx = Q.get(diff, 0xFE)
    tmp = prev + D[idx]
    if abs(tmp) < 0x2000:
        return idx
    if idx >= 0xFF:
        return idx
    idx += 1
    tmp = prev + D[idx]
    if abs(tmp) < 0x2000:
        return idx
    idx -= 2
    return idx & 0xFF


def encode(samples):
    """samples: iterable of int16.  Returns (seed, ops, L)."""
    T1 = [0] * 256
    T2 = [0] * 256
    hash_ = {}
    counter = 0
    ops = bytearray()
    n = len(samples)
    seed = f66a(samples[0])
    prev = seed
    i = 0
    while i < n - 1:
        a = f66a(samples[i]); b = f66a(samples[i + 1])
        idx1 = f5c0(prev, a)
        idx2 = f5c0(prev + D[idx1], b)
        # run detection: neutral pair and the next three samples equal
        is_run = (idx1 == 0x80 and idx2 == 0x80 and i + 5 < n and
                  all(f66a(samples[i + t]) == a for t in (2, 3, 4)))
        if is_run:
            ops.append(0x00)
            i += 5
            continue
        key = (idx1 << 8) | idx2
        op = hash_.get(key, 0)
        if op == 0:
            counter += 1
            if counter >= 0xF4:
                counter = 1
            op = counter
            old = (T1[op] << 8) | T2[op]
            if old in hash_:
                del hash_[old]
            T1[op] = idx1; T2[op] = idx2
            hash_[key] = op
            ops += bytes([0xF5, op, idx1, idx2])
        else:
            ops.append(op)
        prev = ((prev + D[idx1] + D[idx2] + 0x8000) & 0xFFFF) - 0x8000
        i += 2
    return seed, bytes(ops), n * 2


# ---- test signal -----------------------------------------------------------
sr = 44100
t = np.arange(44100) / sr
sig = (0.8 * 32767 * np.sin(2 * math.pi * 220 * t)).astype(np.int16)
sig = (sig // 1).astype(np.int16)

seed, ops, L = encode(sig.tolist())
print("encoded: seed=%d ops=%d L=%d" % (seed, len(ops), L))

# header
hdr = bytearray()
hdr += b"tPxD"
text = b""                       # the attribute byte is the block's first byte
attr = 1 + len(text)
hdr.append(attr)                 # attr counts itself + the text
hdr += text
hdr += b"\x00\x00"
hdr += struct.pack("<I", L // 2)
hdr += struct.pack("<h", seed)
raw = bytes(hdr) + ops

# decode back
b = raw[4]
p = 4 + b + 2
Ll = struct.unpack_from("<I", raw, p)[0]
sd = struct.unpack_from("<h", raw, p + 4)[0]
stream = raw[p + 6:]


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x >= 0x8000 else x


cur = 0
t1 = [0] * 256; t2 = [0] * 256
out = []
i = 0; m = len(stream)
while i < m:
    op = stream[i]; i += 1
    if op == 0:
        out.extend([cur] * 5)
    elif op == 0xF5:
        sel = stream[i]; v1 = stream[i+1]; v2 = stream[i+2]; i += 3
        t1[sel] = v1; t2[sel] = v2
        cur = s16(cur + D[v1]); out.append(cur)
        cur = s16(cur + D[v2]); out.append(cur)
    else:
        cur = s16(cur + D[t1[op]]); out.append(cur)
        cur = s16(cur + D[t2[op]]); out.append(cur)

out = np.array(out[: len(sig)], dtype=np.int64)
# decoded PCM = cur<<2 ; but compare in the internal domain first: reconstruct orig = f66a(s) ~ s/2
target = np.array([f66a(int(x)) for x in sig[:len(out)]], dtype=np.int64)
err = np.abs(out - target)
print("internal-domain compare: mean|err|=%.3f max|err|=%d  (out[:8]=%s target[:8]=%s)" % (
    err.mean(), err.max(), out[:8].tolist(), target[:8].tolist()))
