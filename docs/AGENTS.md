# AGENTS.md — working in `docs/`

This folder holds the user-facing format reference and the product manual text.
Folder rules for the reverse-engineering source material are in
[`../work/AGENTS.md`](../work/AGENTS.md) and
[`../work/pxd/AGENTS.md`](../work/pxd/AGENTS.md); the repository-wide rules are
in [`../AGENTS.md`](../AGENTS.md).

## What belongs here

| path | contents |
|---|---|
| `formats/` | container and companion-file format references |
| `RAVE_HELP.md`, `TECHNO_HELP.md` | transcribed product manual text |

Do not restate the export/arity tables from `../work/pxd/` here; link to the
owning document instead.

## Rules

1. **Addresses and confidence tags are part of the deliverable.** Any claim
   about engine behaviour keeps its `0x...` address and its `[certain]` /
   `[likely]` / `[guess]` tag. Do not round or paraphrase an address.
2. **One owner per fact.** A container fact lives in `formats/<NAME>.md`; other
   documents link to it. The reverse-engineering narrative lives under
   `../work/docs/` or `../work/pxd/`.
3. **Fix links when a file moves.** Use paths relative to the document; verify
   them (a Markdown link checker or a quick `os.path.exists` pass is enough).
4. **Do not invent behaviour.** If the evidence is missing, write
   **(unverified)** or leave the question open; do not fill the gap with a
   plausible story.
5. **Product manual text is historical.** Fix transcription errors, but do not
   modernise wording or delete original statements.

## Verification

* Every relative link resolves.
* Tables have a constant column count, and code fences pair up.
* Cross-references name the section (`§2.1`) rather than a line number, so the
  link survives edits.

## Style

* Markdown, tables for anything with addresses or field layouts.
* Hex for machine facts, decimal for human quantities.
* No emojis or decorative unicode.
* Keep the source documents' confidence tags and section numbering intact.
