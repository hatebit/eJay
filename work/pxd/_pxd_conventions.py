"""Walk the PE export table, sweep every export and report calling-convention evidence.

Usage (Capstone kept out of the project environment):

    python -m pip install --target %TEMP%\\caplib capstone
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_conventions.py

Writes _pxd_detail.txt next to this file and prints one row per export.
All paths are resolved from this file, so the workspace can be moved.
"""
import struct
import re
import os
from capstone import *

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()

pe = struct.unpack_from("<I", d, 0x3C)[0]
mach, nsec, stamp, _, _, optsz, _ = struct.unpack_from("<HHIIIHH", d, pe + 4)
opt = pe + 24
magic = struct.unpack_from("<H", d, opt)[0]
imgbase = struct.unpack_from("<I", d, opt + 28)[0]
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
    return None


def cstr(rva, limit=512):
    o = r2o(rva)
    if o is None:
        return ""
    return d[o:o + limit].split(b"\0")[0].decode("latin1")


# ---- exports -------------------------------------------------------------
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
ridx = {r: k for k, (r, n) in enumerate(exports)}
exp_at = dict(exports)
exp_starts = set(ridx)

# ---- imports -------------------------------------------------------------
# iat_va -> "dll!name"; useful to resolve `call dword ptr [0x1004xxxx]`.
iat_names = {}
imp_rva, imp_sz = struct.unpack_from("<II", d, ddoff + 8)
if imp_rva:
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
                fn = cstr(v + 2)  # skip IMAGE_IMPORT_BY_NAME.Hint
            iat_names[imgbase + ft + 4 * i] = "%s!%s" % (dll, fn)
            i += 1
        o += 20

# ---- disassembly ---------------------------------------------------------
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True


def next_func_start(rva):
    k = ridx[rva]
    return exports[k + 1][0] if k + 1 < len(exports) else rva + 4096


def sweep(rva):
    """Linear sweep from the export start.

    Stop after a terminal instruction that is followed by alignment padding or a
    fresh prologue, or when the sweep reaches another export's entry point.  The
    export bodies are not contiguous, so the next export RVA is a hard stop but
    not the body length.
    """
    off = r2o(rva)
    insns = []
    for ins in md.disasm(d[off:off + 16384], imgbase + rva):
        cur = ins.address - imgbase
        if cur != rva and cur in exp_starts:
            break
        insns.append(ins)
        if ins.mnemonic.startswith("ret") or ins.mnemonic == "jmp":
            nxt = ins.address + ins.size - imgbase
            t = r2o(nxt)
            tail = d[t:t + 8] if t is not None else b""
            if tail[:3] == b"\x55\x8b\xec" or tail[:1] in (b"\xcc", b"\x90") or not tail:
                break
    return insns


def reg_consumed(insns, reg):
    for ins in insns:
        reads, writes = ins.regs_access()
        rn = {md.reg_name(r) for r in reads}
        wn = {md.reg_name(w) for w in writes}
        if reg in rn:
            return True
        if reg in wn:
            return False
        if ins.mnemonic in ("call", "jmp") or ins.mnemonic.startswith("j"):
            return False
    return False


OFF = re.compile(r"\[ebp ([+-]) (0x[0-9a-f]+|\d+)")
detail = open(os.path.join(HERE, "_pxd_detail.txt"), "w", encoding="utf-8")
rows = []
for rva, name in exports:
    insns = sweep(rva)
    rets = [x for x in insns if x.mnemonic.startswith("ret")]
    sb = 0
    for x in rets:
        if x.op_str:
            try:
                sb = max(sb, int(x.op_str, 0))
            except ValueError:
                pass
    pos, neg = set(), set()
    for ins in insns:
        for m in OFF.finditer(ins.op_str):
            v = int(m.group(2), 0)
            (pos if m.group(1) == "+" else neg).add(v)
    regs = [r for r in ("eax", "edx", "ecx") if reg_consumed(insns, r)]
    rows.append(dict(name=name, rva=rva, n=len(insns), sb=sb,
                     ret=sorted({(x.op_str or "0") for x in rets}),
                     pos=sorted(pos), neg=sorted(neg), regs=regs, insns=insns))
    detail.write("=" * 66 + "\n%s  RVA=%#x  insns=%d  ret=%s  ebp+%s  ebp-%d..  regs=%s\n" % (
        name, rva, len(insns), ",".join(sorted({(x.op_str or "0") for x in rets})),
        [hex(v) for v in sorted(pos)], max(neg) if neg else 0, ",".join(regs) or "-"))
    for ins in insns[:12]:
        extra = ""
        if ins.mnemonic in ("call", "jmp") and ins.operands and ins.operands[0].type == CS_OP_IMM:
            t = ins.operands[0].imm - imgbase
            extra = "  ; %s" % exp_at.get(t, "internal 0x%x" % t)
        elif ins.mnemonic == "call" and "dword ptr [" in ins.op_str:
            m = re.search(r"\[(0x[0-9a-f]+)\]", ins.op_str)
            if m and int(m.group(1), 16) in iat_names:
                extra = "  ; " + iat_names[int(m.group(1), 16)]
        detail.write("  %05x  %-20s %s%s\n" % (ins.address - imgbase, ins.mnemonic, ins.op_str, extra))
detail.close()

print("%-14s %-6s %-8s %-26s %-22s %s" %
      ("name", "insns", "ret", "ebp+args", "locals(neg)", "regs"))
for r in rows:
    print("%-14s %-6d %-8s %-26s %-22s %s" % (
        r["name"], r["n"], str(r["ret"]), str(r["pos"]),
        ("-%x" % max(r["neg"])) if r["neg"] else "-", ",".join(r["regs"]) or "-"))
