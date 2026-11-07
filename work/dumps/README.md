# work/dumps/ — derived mix dumps

Plain-text dumps derived from the Techno eJay mix `WAMBAM.MIX`. They are
evidence for [`../../docs/formats/MIX_FORMAT_TECHNO.md`](../../docs/formats/MIX_FORMAT_TECHNO.md)
and are not generated at build time.

| file | contents |
|---|---|
| `WAMBAM.tracks.txt` | per-track placements and channel assignment |
| `WAMBAM.samples.txt` | resolved sample labels (`RAVE20.INF`) per placement |
| `WAMBAM.index.txt` | sample-index records used for the resolution |

The parse scripts that produced them are not checked in. Treat the files as
read-only reference data; the format note is the canonical description.
