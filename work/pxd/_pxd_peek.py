"""Hex/ASCII peek at absolute VAs, resolved through the same section table.

Usage:
    python _pxd_peek.py 0x1004B304 0x1004B4EC

Prints the 32 bytes at each address with printable ASCII substitutions.  Useful
for deciding whether a literal pushed by the code is a string, a float or code.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])

for a in sys.argv[1:]:
    va = int(a, 0)
    o = r2o(va - imgbase)
    chunk = d[o:o + 32]
    txt = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
    print("%#010x  %-64s  %s" % (va, chunk.hex(" "), txt))
