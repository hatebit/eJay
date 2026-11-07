"""Cross-check declared arity against in-image call sites.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_xref.py

Each export is swept once from its entry point (the same sweep used by
`_pxd_conventions.py`, so the instruction stream stays aligned), and every
direct `call` to another export is recorded together with the number of
immediately preceding `push` instructions.  That push count is compared with
the callee's own `ret N / 4`.

Calls made from unexported internal functions are not visible to this pass;
`_pxd_dump.py <lo>-<hi>` shows those bodies, and the push counts there were
read by hand where a document cites them.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])

calls = {}
for rva, caller in exports:
    insns = sweep(rva)
    for i, ins in enumerate(insns):
        if ins.mnemonic != "call" or not ins.operands or ins.operands[0].type != CS_OP_IMM:
            continue
        target = ins.operands[0].imm - imgbase
        if target not in exp_starts:
            continue
        pushes = 0
        j = i - 1
        # Arguments are pushed one at a time with `mov reg, [ebp+N]` in between,
        # so allow mov/lea while walking back, and stop at anything else.
        while j >= 0 and insns[j].mnemonic in ("push", "mov", "lea"):
            if insns[j].mnemonic == "push":
                if (insns[j].op_str == "ebp" and j + 1 < len(insns)
                        and insns[j + 1].mnemonic == "mov"
                        and insns[j + 1].op_str.replace(" ", "") == "ebp,esp"):
                    break          # function prologue, not an argument
                pushes += 1
            j -= 1
        calls.setdefault(target, []).append((ins.address - imgbase, pushes, caller))

print("%-14s %-4s %-5s %s" % ("export", "args", "sites", "push counts (caller)"))
mismatch = 0
for rva, name in exports:
    insns = sweep(rva)
    rets = [x for x in insns if x.mnemonic.startswith("ret")]
    sb = max([int(x.op_str, 0) for x in rets if x.op_str] or [0])
    sites = calls.get(rva, [])
    counts = sorted({p for _, p, _ in sites})
    flag = ""
    bad = [(a, p, c) for a, p, c in sites if p != sb // 4]
    if bad:
        mismatch += 1
        flag = "  <-- differs: " + ", ".join(
            "%#x in %s pushed %d" % (a, c, p) for a, p, c in bad)
    print("%-14s %-4d %-5d %s%s" % (name, sb // 4, len(sites), counts, flag))
print("%d exports with a push-count mismatch" % mismatch)
