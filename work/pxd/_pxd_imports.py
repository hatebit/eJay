"""Import inventory, resolved through the import descriptor.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_imports.py

Prints one line per DLL with its import count, then every function as
`IAT_VA  dll!name`, and writes the same listing to `_pxd_imports.txt`
(UTF-8, so the file survives a diff and does not depend on the shell's
redirection encoding).  The IAT VA is what a disassembly shows inside
`call dword ptr [0x1004xxxx]`; naming an import from that slot number alone is
never safe, so always resolve it here (or via `_pxd_dump.py`).
"""
import struct
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()

pe = struct.unpack_from("<I", d, 0x3C)[0]
nsec, optsz = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
opt = pe + 24
imgbase = struct.unpack_from("<I", d, opt + 28)[0]
magic = struct.unpack_from("<H", d, opt)[0]
ddoff = opt + (112 if magic == 0x20B else 96)
sect = opt + optsz
secs = []
for i in range(nsec):
    o = sect + i * 40
    vsz, va, rsz, ra = struct.unpack_from("<IIII", d, o + 8)
    secs.append((d[o:o + 8].rstrip(b"\0").decode("latin1"), va, vsz, ra, rsz))


def r2o(rva):
    for n, va, vsz, ra, rsz in secs:
        if va <= rva < va + max(vsz, rsz):
            return ra + (rva - va)


def cstr(rva):
    o = r2o(rva)
    return d[o:o + 256].split(b"\0")[0].decode("latin1") if o is not None else ""


imp_rva = struct.unpack_from("<I", d, ddoff + 8)[0]
o = r2o(imp_rva)
total = 0
dlls = 0
out = []
for dll_index in range(64):
    oft, ts, fc, name, ft = struct.unpack_from("<IIIII", d, o)
    if not any((oft, ts, fc, name, ft)):
        break
    dll = cstr(name)
    funcs = []
    i = 0
    while True:
        v = struct.unpack_from("<I", d, r2o(oft or ft) + 4 * i)[0]
        if not v:
            break
        fn = "#%d" % (v & 0xFFFF) if v & 0x80000000 else cstr(v + 2)
        funcs.append((imgbase + ft + 4 * i, fn))
        i += 1
    out.append("%-12s %3d imports" % (dll, len(funcs)))
    for va, fn in funcs:
        out.append("  %08x  %s!%s" % (va, dll, fn))
    total += len(funcs)
    dlls += 1
    o += 20
out.append("total %d imports in %d DLLs" % (total, dlls))
print("\n".join(out))
open(os.path.join(HERE, "_pxd_imports.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
