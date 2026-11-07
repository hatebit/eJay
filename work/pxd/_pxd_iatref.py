"""Find the call sites of an import slot or any literal dword in the code.

Usage:
    python _pxd_iatref.py 0x10043268 0x10043258

For each address, prints every `FF 15 <addr>` (call dword ptr) and
`FF 25 <addr>` (jmp dword ptr) site in `.text`, plus the export whose body
contains it, or `internal` when the site sits between export bodies.  Handy for
"which export uses this import?" without sweeping the whole section by hand.
"""
import struct
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])

text = [s for s in secs if s[0] == ".text"][0]
_, tva, tvsz, tra, trsz = text
buf = d[tra:tra + min(tvsz, trsz)]
# Body extent per export, from the same sweep the other scripts use: a site past
# an export's own `ret` belongs to an unexported helper, not to that export.
extent = {}
for rva, name in exports:
    insns = sweep(rva)
    extent[rva] = insns[-1].address + insns[-1].size - imgbase if insns else rva
starts = sorted(ridx)

for arg in sys.argv[1:]:
    target = int(arg, 0)
    print("%#x" % target)
    hits = 0
    for i in range(len(buf) - 6):
        if buf[i] in (0xFF,) and buf[i + 1] in (0x15, 0x25):
            if struct.unpack_from("<I", buf, i + 2)[0] == target:
                va = imgbase + tva + i
                rva = va - imgbase
                owner = "internal"
                for s in reversed(starts):
                    if s <= rva:
                        n = exp_at.get(s, "#%#x" % s)
                        owner = n if rva < extent[s] else "internal after " + n
                        break
                print("  %#010x  %s  in %s" % (va, "call" if buf[i + 1] == 0x15 else "jmp", owner))
                hits += 1
    if not hits:
        print("  (no reference)")
