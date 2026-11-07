"""Annotated disassembly of named exports or address ranges.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_dump.py APlay AStart AInit
    python _pxd_dump.py 0x10017632-0x1001773e

Direct calls are resolved to export names (or to `internal 0x...`), and
`call dword ptr [IAT]` is resolved through the import table.  A range is given
as two absolute VAs separated by `-` and is useful for the unexported helpers
that sit between export entries.
"""
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])


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


def listing(title, insns):
    print("=" * 78)
    print("%s  insns=%d" % (title, len(insns)))
    for ins in insns:
        print("  %06x  %-20s %s%s" % (
            ins.address - imgbase, ins.mnemonic, ins.op_str, annotate(ins)))


want = set(a.lower() for a in sys.argv[1:] if "-" not in a)
for rva, name in exports:
    if name.lower() in want:
        insns = sweep(rva)
        listing("%s  RVA=%#x  end=%#x" % (
            name, rva, insns[-1].address + insns[-1].size if insns else rva), insns)

for arg in sys.argv[1:]:
    if "-" not in arg:
        continue
    lo_s, hi_s = arg.split("-", 1)
    lo, hi = int(lo_s, 0), int(hi_s, 0)
    o = r2o(lo - imgbase)
    insns = list(md.disasm(d[o:o + (hi - lo)], lo))
    listing("range %#x-%#x" % (lo, hi), insns)
