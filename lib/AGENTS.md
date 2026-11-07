# lib/

Standalone, read-only, standard-library-only utilities for eJay tPxd/.MIX.

- pxd_file.py — parse/decode .pxd (tPxD) files; PxdFile, PxdDecoder, comment/record semantics per
  ../docs/formats/PXD_FORMAT.md.
- pxd_info.py — summarize .pxd files.
- pxd_play.py — play .pxd via sounddevice.
- pxd_to_wav.py — convert .pxd to WAV/PCM.
- mix_file.py — parse .MIX arrangement files; collapse runs per-column (A/B lanes, 8 tracks) like work/src/mixplay.py.
  Resolves sample IDs via ID_OFFSET=731 against EJAY/PXD index.
- mix_info.py — summarize .MIX files; -e/--events lists collapsed events with optional -i/--index for sample resolution.

Do not modify these files without reason; they are clean reimplementations intended to be independent of `work/`.