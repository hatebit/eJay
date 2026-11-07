"""Disassemble a VA range from the nearest prologue, with import/export annotation.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\opencode\\caplib"
    python _pxd_range.py 0x10010100 0x100104c6
Finds the last `55 8B EC` prologue at or before the start address, then linearly
disassembles to the end address, annotating calls.
"""
import struct
import re
import os
import sys
from capstone import *

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()

pe = struct.unpack_from("<I", d, 0x3C)[0]
mach, nsec, stamp, _, _, optsz, _ = struct.unpack_from("<HHIIIHH", d, pe + 4)
opt = pe + 24
imgbase = struct.unpack_from("<I", d, opt + 28)[0]
ddoff = opt + 96
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
    return None


def cstr(rva, limit=512):
    o = r2o(rva)
    if o is None:
        return ""
    return d[o:o + limit].split(b"\0")[0].decode("latin1")


exp_rva, exp_sz = struct.unpack_from("<II", d, ddoff)
o = r2o(exp_rva)
(_, _, _, _, nmrv, ordbase, nfuncs, nnames,
 addrfunc, addrnames, addrord) = struct.unpack_from("<IIHHIIIIIII", d, o)
no, oo, fo = r2o(addrnames), r2o(addrord), r2o(addrfunc)
named = {}
for i in range(nnames):
    nr = struct.unpack_from("<I", d, no + 4 * i)[0]
    named[struct.unpack_from("<H", d, oo + 2 * i)[0]] = cstr(nr)
exports = sorted(
    (struct.unpack_from("<I", d, fo + 4 * i)[0], named.get(i, "#" + str(ordbase + i)))
    for i in range(nfuncs)
)
exp_at = dict(exports)

iat_names = {}
imp_rva, imp_sz = struct.unpack_from("<II", d, ddoff + 8)
o = r2o(imp_rva)
while True:
    oft, ts, fc, name, ft = struct.unpack_from("<IIIII", d, o)
    if not any((oft, ts, fc, name, ft)):
        break
    dll = cstr(name)
    t = r2o(oft or ft)
    slot = r2o(ft) if ft else None
    i = 0
    while True:
        v = struct.unpack_from("<I", d, t + 4 * i)[0]
        if not v:
            break
        if v & 0x80000000:
            fn = "#" + str(v & 0xFFFF)
        else:
            fn = cstr(v + 2)
        iat_names[imgbase + ft + 4 * i] = "%s!%s" % (dll, fn)
        i += 1
    o += 20

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True


def annotate(ins):
    extra = ""
    if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == CS_OP_IMM:
        t = ins.operands[0].imm - imgbase
        extra = "   ; %s" % exp_at.get(t, "internal 0x%x" % t)
    elif "dword ptr [" in ins.op_str:
        m = re.search(r"\[(0x[0-9a-f]+)\]", ins.op_str)
        if m and int(m.group(1), 16) in iat_names:
            extra = "   ; " + iat_names[int(m.group(1), 16)]
    return extra


def find_prologue(lo):
    """RVA of the last `55 8B EC` at or before lo (within 0x1000)."""
    rva = lo
    while rva > lo - 0x1000:
        o = r2o(rva)
        if d[o:o + 3] == b"\x55\x8b\xec":
            return rva
        rva -= 1
    return lo


lo, hi = (int(a, 0) for a in sys.argv[1:3])
start = find_prologue(lo - imgbase)
o = r2o(start)
insns = list(md.disasm(d[o:o + (hi - imgbase - start)], imgbase + start))
print("prologue at RVA %#x (VA %#x)" % (start, imgbase + start))
for ins in insns:
    print("  %06x  %-22s %s%s" % (
        ins.address - imgbase, ins.mnemonic, ins.op_str, annotate(ins)))
