"""Printable-string inventory with absolute VAs.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_strings.py [min_length] [lo_va] [hi_va]

Prints every run of printable ASCII (plus Latin-1 letters) at least
`min_length` bytes long, as `VA  "text"`, and writes the same listing to
`_pxd_strings.txt` (UTF-8).  Defaults: min length 4, whole image.
Nothing is loaded or executed.
"""
import sys
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()

pe = struct.unpack_from("<I", d, 0x3C)[0]
nsec, optsz = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
opt = pe + 24
imgbase = struct.unpack_from("<I", d, opt + 28)[0]
sect = opt + optsz
secs = []
for i in range(nsec):
    o = sect + i * 40
    vsz, va, rsz, ra = struct.unpack_from("<IIII", d, o + 8)
    secs.append((d[o:o + 8].rstrip(b"\0").decode("latin1"), va, vsz, ra, rsz))

minlen = int(sys.argv[1]) if len(sys.argv) > 1 else 4
lo = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3], 0) if len(sys.argv) > 3 else 1 << 32

OK = set(range(0x20, 0x7F))
out = []
for name, va, vsz, ra, rsz in secs:
    if name not in (".data", ".rdata"):
        continue
    buf = d[ra:ra + rsz]
    start = None
    for i, b in enumerate(buf + b"\0"):
        good = b in OK
        if good and start is None:
            start = i
        elif not good and start is not None:
            if i - start >= minlen:
                s = buf[start:i].decode("latin1")
                a = imgbase + va + start
                if lo <= a < hi:
                    out.append("%08x  %r" % (a, s))
            start = None
print("\n".join(out))
open(os.path.join(HERE, "_pxd_strings.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
