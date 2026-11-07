# work/tools/ — disassembly helpers

Small read-only tools used to produce the evidence cited by the notes in
`../docs/` and `../pxd/`. They need Capstone, installed into a scratch
directory (see [`../AGENTS.md`](../AGENTS.md)).

| file | purpose |
|---|---|
| `pxd_dis.py` | minimal PE reader + disassembler for `pxd32d5_d4.dll` (**not checked in**; set `PXD_DLL`); `dis` and `find` modes |
| `disapp.py` | disassembler for the Rave eJay host binary, `disks/Rave_eJay/RAVE/EJAY/RAVEEJAY.EXE` (formerly `Raveejay.application`); override with `RAVE_APP` |

```sh
PXD_DLL=/path/to/pxd32d5_d4.dll PYTHONPATH=/tmp/caplib \
  python work/tools/pxd_dis.py 0x100149E0 40
PXD_DLL=/path/to/pxd32d5_d4.dll PYTHONPATH=/tmp/caplib \
  python work/tools/pxd_dis.py find a380e30810
```

The binary is **not checked in**: `PXD_DLL` must point at a local copy.
These tools never load or execute the binary — they read the file bytes.
