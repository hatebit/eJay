"""Tiny PE reader / disassembler for pxd32d5_d4.dll (one-off RE helper).

The binary is not checked in. Point ``PXD_DLL`` at a local copy:

Usage:  PXD_DLL=/path/to/pxd32d5_d4.dll python tools/pxd_dis.py 0x100149E0 40
"""

import os
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# The reference binary is not checked in; point PXD_DLL at a local copy.
DLL = os.environ.get("PXD_DLL")
if not DLL:
    sys.exit("set PXD_DLL to a local copy of pxd32d5_d4.dll")


class Pe:
    def __init__(self, path=DLL):
        self.blob = open(path, "rb").read()
        e_lfanew = struct.unpack_from("<I", self.blob, 0x3C)[0]
        assert self.blob[e_lfanew:e_lfanew + 4] == b"PE\0\0"
        coff = e_lfanew + 4
        self.nsec, = struct.unpack_from("<H", self.blob, coff + 2)
        self.optsize, = struct.unpack_from("<H", self.blob, coff + 16)
        opt = coff + 20
        self.base, = struct.unpack_from("<I", self.blob, opt + 28)
        self.sections = []
        s = opt + self.optsize
        for i in range(self.nsec):
            name, vsize, vaddr, rsize, raddr = struct.unpack_from(
                "<8sIIII", self.blob, s + 40 * i)
            self.sections.append((name.rstrip(b"\0").decode(), vaddr, vsize,
                                  raddr, rsize))

    def off(self, va):
        rva = va - self.base
        for name, vaddr, vsize, raddr, rsize in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        raise ValueError("VA %08x not mapped" % va)

    def read(self, va, n):
        o = self.off(va)
        return self.blob[o:o + n]

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]


def dis(va, count=40, mode=CS_MODE_32):
    pe = Pe()
    md = Cs(CS_ARCH_X86, mode)
    md.detail = False
    o = pe.off(va)
    for ins in md.disasm(pe.blob[o:o + 8 * count], va):
        print("%08x  %-24s %s %s" % (ins.address, ins.bytes.hex(),
                                     ins.mnemonic, ins.op_str))
        count -= 1
        if count <= 0:
            break


def find(pattern_hex, limit=20):
    pe = Pe()
    pat = bytes.fromhex(pattern_hex)
    out = []
    start = 0
    while len(out) < limit:
        i = pe.blob.find(pat, start)
        if i < 0:
            break
        va = None
        for name, vaddr, vsize, raddr, rsize in pe.sections:
            if raddr <= i < raddr + rsize:
                va = pe.base + vaddr + (i - raddr)
        out.append((i, va))
        start = i + 1
    for off, va in out:
        print("file %06x  va %s" % (off, "%08x" % va if va else "?"))


if __name__ == "__main__":
    if sys.argv[1] == "find":
        find(sys.argv[2])
    else:
        dis(int(sys.argv[1], 0), int(sys.argv[2]) if len(sys.argv) > 2 else 40)
