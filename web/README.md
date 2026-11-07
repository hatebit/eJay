# web/ — browser PXD to WAV converter

A single static page that converts a dropped `.pxd` file to a downloadable
`.wav` entirely in the browser. There is no backend, no build step and no
dependencies.

Open `index.html` directly (`file://` works) or serve the folder with any
static server. The decoder is a hand port of the Python `tPxd` path in
`../work/src/`; see [`AGENTS.md`](AGENTS.md) for the mapping and the rules for
keeping the JS in sync.

## Files

| path | role |
|---|---|
| `index.html` | the whole app: markup, CSS, decoder core and UI script |
| `background.webp` | page background |
| `background-original.jfif` | original background source image |
| `favicon.png` | page icon |

Output is always mono, 16-bit, 44.1 kHz PCM WAV with a 44-byte RIFF header.
The page works offline and makes no external requests.

## Documentation

* [`AGENTS.md`](AGENTS.md) — port scope, C semantics, verification and style.
* [`../docs/formats/PXD_FORMAT.md`](../docs/formats/PXD_FORMAT.md) — the
  format the decoder implements.
