# AGENTS.md — working in `iso/`

`iso/` holds the download index (`index.json`), the product table
(`README.md`) and, after a download, the ISO images themselves
(`*.iso`, ignored by git).

## Rules

1. **Do not modify or delete downloaded ISOs.** They are the reference copies of
   the original software; re-download from `index.json` if one is missing.
2. **Do not execute anything extracted from an ISO.** The binaries are
   read-only reverse-engineering material; see the repository
   [`AGENTS.md`](../AGENTS.md).
3. **Keep `index.json` valid.** It is a flat object keyed by product name with
   `year`, `developer`, `iso` (URL or `null`), an optional `root` directory
   (only that ISO folder is extracted, into the key's directory, so its own
   files land at the top level) and an optional `skip` list of files or
   directories relative to `root`. `iso_download.py` and `iso_extract.py`
   both read it by key.
4. **Run the scripts from the repository root**, not from this folder:

   ```sh
   python iso_download.py "Rave eJay"
   python iso_extract.py "Rave eJay"      # -> disks/Rave_eJay/
   ```

5. **Do not commit ISO images** or extend `.gitignore` to hide extracted data
   that the tools need.
