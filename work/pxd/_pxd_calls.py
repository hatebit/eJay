"""Call map for named exports.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_calls.py REffekt RDrum

Prints only `call` instructions (direct targets resolved to export names, IAT
calls resolved through the import table) plus `push`/`mov`/`cmp` operands that
refer to data in the 0x1004xxxx-0x1009xxxx range.  Useful for orienting inside
a long export where the full listing is unreadable; use `_pxd_dump.py` for the
instruction-by-instruction view.
"""
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])

DATA = re.compile(r"0x1004[0-9a-f]{4}|0x100[3-9][0-9a-f]{4}")

for want in sys.argv[1:]:
    rva = dict((n, r) for r, n in exports).get(want)
    if rva is None:
        print("no such export: %s" % want)
        continue
    insns = sweep(rva)
    print("=" * 30, want, "%#x" % rva, len(insns))
    for ins in insns:
        if ins.mnemonic == "call":
            if ins.operands and ins.operands[0].type == CS_OP_IMM:
                t = ins.operands[0].imm - imgbase
                print("  %06x call %s" % (ins.address - imgbase, exp_at.get(t, "int %#x" % t)))
            else:
                m = re.search(r"\[(0x[0-9a-f]+)\]", ins.op_str)
                slot = int(m.group(1), 16) if m else None
                print("  %06x call [%s] %s" % (
                    ins.address - imgbase, m.group(1) if m else ins.op_str,
                    iat_names.get(slot, "") if slot else ""))
        elif DATA.search(ins.op_str) and ins.mnemonic in ("push", "mov", "cmp"):
            print("  %06x %-6s %s" % (ins.address - imgbase, ins.mnemonic, ins.op_str))
