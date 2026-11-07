"""Tiny PE reader / disassembler for the Rave eJay host application.

The application ships on the Rave eJay CD as
``disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE`` (777 728-byte VB6 PE, image base
``0x400000``); older notes call it ``Raveejay.application``. Override the path
with the ``RAVE_APP`` environment variable.

Usage:
  python disapp.py 0x40D398 40        # 40 instructions from a VA
  python disapp.py find 85448          # find file offset, print VA
  python disapp.py xref 0x41A624       # find code refs to a VA/data addr
"""
import os, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "disks", "Rave_eJay", "RAVE", "EJAY",
                        "RAVEEJAY.EXE")
PATH = os.environ.get("RAVE_APP", os.path.normpath(_DEFAULT))


class Pe:
    def __init__(self, path=PATH):
        self.blob = open(path, "rb").read()
        e_lfanew = struct.unpack_from("<I", self.blob, 0x3C)[0]
        assert self.blob[e_lfanew:e_lfanew + 4] == b"PE\0\0"
        coff = e_lfanew + 4
        self.nsec, = struct.unpack_from("<H", self.blob, coff + 2)
        self.optsize, = struct.unpack_from("<H", self.blob, coff + 16)
        opt = coff + 20
        self.base, = struct.unpack_from("<I", self.blob, opt + 28)
        self.entry, = struct.unpack_from("<I", self.blob, opt + 16)
        self.sections = []
        s = opt + self.optsize
        for i in range(self.nsec):
            name = self.blob[s + 40 * i:s + 40 * i + 8].rstrip(b"\0").decode(
                "ascii", errors="replace")
            vsize, vaddr, rsize, raddr = struct.unpack_from(
                "<IIII", self.blob, s + 40 * i + 8)
            self.sections.append((name, vaddr, vsize, raddr, rsize))

    def off(self, va):
        rva = va - self.base
        for name, vaddr, vsize, raddr, rsize in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        raise ValueError("VA %08x not mapped" % va)

    def va(self, fo):
        for name, vaddr, vsize, raddr, rsize in self.sections:
            if raddr <= fo < raddr + rsize:
                return self.base + vaddr + (fo - raddr)
        return None

    def read(self, va, n):
        o = self.off(va)
        return self.blob[o:o + n]

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]


def dis(va, count=40):
    pe = Pe()
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = False
    o = pe.off(va)
    for ins in md.disasm(pe.blob[o:o + 8 * count], va):
        print("%08x  %-24s %s %s" % (ins.address, ins.bytes.hex(),
                                     ins.mnemonic, ins.op_str))
        count -= 1
        if count <= 0:
            break


def find(fo, limit=20):
    pe = Pe()
    start = 0
    out = []
    while len(out) < limit:
        i = pe.blob.find(fo.encode() if isinstance(fo, str) else fo, start)
        if i < 0:
            break
        out.append((i, pe.va(i)))
        start = i + 1
    for off, va in out:
        print("file %06x  va %s" % (off, "%08x" % va if va else "?"))


def xref(target_va, limit=50):
    """Find code references to target_va (32-bit absolute address or string data VA)."""
    pe = Pe()
    text = None
    for name, vaddr, vsize, raddr, rsize in pe.sections:
        if name == ".text":
            text = (pe.base + vaddr, pe.blob[raddr:raddr + max(vsize, rsize)])
    if not text:
        print("no .text section")
        return
    tbase, tblob = text
    pat = struct.pack("<I", target_va)
    start = 0
    found = 0
    while found < limit:
        i = tblob.find(pat, start)
        if i < 0:
            break
        va = tbase + i
        print("xref at %08x" % va)
        dis(va, 8)
        print()
        start = i + 1
        found += 1


if __name__ == "__main__":
    if sys.argv[1] == "find":
        find(sys.argv[2])
    elif sys.argv[1] == "xref":
        xref(int(sys.argv[2], 0))
    else:
        dis(int(sys.argv[1], 0), int(sys.argv[2]) if len(sys.argv) > 2 else 40)
