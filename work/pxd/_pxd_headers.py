"""Print the PE headers, section table and data directories of the subject.

Usage:
    python _pxd_headers.py

No disassembly and no Capstone, so it runs without the scratch install.  This
is the source of the numbers in `PXD32D5-D4-layout.md` section 1.
"""
import struct
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get("PXD_DLL", os.path.join(HERE, "pxd32d5_d4.dll"))
d = open(PATH, "rb").read()

pe = struct.unpack_from("<I", d, 0x3C)[0]
mach, nsec, stamp, _, _, optsz, chars = struct.unpack_from("<HHIIIHH", d, pe + 4)
opt = pe + 24
magic = struct.unpack_from("<H", d, opt)[0]
(major_link, minor_link) = struct.unpack_from("<BB", d, opt + 2)
entry, _, _, base, sec_align, file_align = struct.unpack_from("<IIIIII", d, opt + 16)
img_size, hdr_size, checksum = struct.unpack_from("<III", d, opt + 56)
subsys, dllchars = struct.unpack_from("<HH", d, opt + 68)
stack_res, stack_com, heap_res, heap_com = struct.unpack_from("<IIII", d, opt + 72)
(os_major, os_minor, img_major, img_minor, ss_major, ss_minor) = \
    struct.unpack_from("<HHHHHH", d, opt + 40)
ddoff = opt + (112 if magic == 0x20B else 96)
names = ["Export", "Import", "Resource", "Exception", "Security", "Reloc",
         "Debug", "Architecture", "GlobalPtr", "TLS", "LoadConfig", "BoundImport",
         "IAT", "DelayImport", "CLR", "Reserved"]

fmt = lambda n: "%#x (%d)" % (n, n)
print("file                %s  %d bytes" % (os.path.basename(PATH), len(d)))
print("machine             %#06x   sections %d   characteristics %#06x" % (mach, nsec, chars))
print("link stamp          %#010x -> %s UTC" % (
    stamp, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stamp))))
print("optional magic      %#06x  linker %d.%d" % (magic, major_link, minor_link))
print("image base          %#x" % base)
print("entry point (RVA)   %#x -> %#x" % (entry, base + entry))
print("size of image       %#x" % img_size)
print("section/file align  %#x / %#x   header size %#x" % (sec_align, file_align, hdr_size))
print("os / image / subsys version  %d.%d / %d.%d / %d.%d" % (
    os_major, os_minor, img_major, img_minor, ss_major, ss_minor))
print("subsystem           %d   dll characteristics %#x   checksum %#x" % (
    subsys, dllchars, checksum))
print("stack               reserve %#x commit %#x" % (stack_res, stack_com))
print("heap                reserve %#x commit %#x" % (heap_res, heap_com))

print("\nsections")
print("  %-8s %-10s %-10s %-10s %-10s %s" % ("name", "VA", "vsize", "rawptr", "rawsize", "characteristics"))
for i in range(nsec):
    o = opt + optsz + i * 40
    nm = d[o:o + 8].rstrip(b"\0").decode("latin1")
    vsz, va, rsz, ra = struct.unpack_from("<IIII", d, o + 8)
    ch = struct.unpack_from("<I", d, o + 36)[0]
    print("  %-8s %#-10x %#-10x %#-10x %#-10x %#010x" % (nm, va, vsz, ra, rsz, ch))

print("\ndata directories")
for i in range(16):
    rva, sz = struct.unpack_from("<II", d, ddoff + 8 * i)
    if rva or sz:
        print("  %2d %-12s RVA %#-9x size %#x" % (i, names[i], rva, sz))
