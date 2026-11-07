"""Reader and decoder for eJay ``tPxd`` (``.pxd``) audio files.

A ``tPxd`` file starts with a small ASCII comment and is followed by a
DPCM stream decoded through a runtime code book, as produced by
PXD32D5-D4.DLL.  The container layout and the decoder are documented in
``docs/formats/PXD_FORMAT.md``; the module is a standalone, read-only,
standard-library-only view on such a file:

    f = PxdFile("bo-test.pxd")
    head = f.header()   # PxdHeader: comment, frame count, data offset
    pcm = f.samples()   # array('h'), mono 16-bit at 44.1 kHz

``samples()`` returns exactly what the engine's file conversion
(``RWavToTemp`` on the conversion path) produces for the input: the left
channel of the decoded stereo buffer as mono 16-bit little-endian PCM at
44.1 kHz.

The comment is metadata only - the decode path never reads it - but it
is not free-form either: on the Rave eJay sample bank it is a six-line
copy of the sample's library record from the install's sample index
(display name, id, producer, an empty line, category, bar size).  See
"Comment-line semantics" in ``docs/formats/PXD_FORMAT.md``;
:class:`PxdComment` exposes those fields.
"""

from __future__ import annotations

import array
import struct
from dataclasses import dataclass

__all__ = [
    "PXD_MAGIC",
    "PXD_SAMPLE_RATE",
    "BANK_BAR_FRAMES",
    "DELTA_TABLE",
    "PxdError",
    "PxdComment",
    "PxdHeader",
    "PxdDecoder",
    "PxdFile",
]

PXD_MAGIC = b"tPxD"
PXD_SAMPLE_RATE = 44100
# The sample bank's grid quantum, comment line 6 in every bank file
# (docs/formats/PXD_FORMAT.md, "Comment-line semantics"): one bar = 4 beats at
# 180 BPM (1.333 s at 44.1 kHz).  A property of the Rave eJay bank, not
# a container constant - other comment shapes may carry another value,
# and a sample's own length is the header's frame count, never this.
BANK_BAR_FRAMES = 58800


class PxdError(ValueError):
    """Raised when a ``.pxd`` file cannot be read, parsed or decoded."""


# ---------------------------------------------------------------------------
# the comment field (docs/formats/PXD_FORMAT.md, parse via ``sub_10019DEE`` callers)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PxdComment:
    """The validated comment of a ``tPxD`` stream.

    Layout: ``"tPxD"`` magic, one length byte, ``length - 2`` ASCII text
    bytes, then a NUL terminator.  ``length`` counts itself, so the field
    ends at byte ``4 + length``.  The comment is descriptive only -
    ``sub_10019DEE`` validates just the magic, the length, the
    terminator and ASCII - so the decode path never depends on it.

    The text is CRLF-separated.  On the Rave eJay sample bank it is a
    six-line copy of the sample's library record from the install's
    sample index ``disk/RAVE/EJAY/PXD`` (verified by a full-bank join;
    see "Comment-line semantics" in ``docs/formats/PXD_FORMAT.md``):

        line 1  display name, part 1
        line 2  display name, part 2
                (hyper bank ``r1hg*``: sequential id ``001``-``128``)
        line 3  producer/product tag ("Rave eJay" in every bank file)
        line 4  empty
        line 5  category / browser group
        line 6  the constant "58800" - one bar in frames, the bank's
                grid quantum, not the sample's own length

    Other shapes are valid and stay parseable: ``EJAY\\INTRO.PXD`` has a
    single line (``"Rave eJay Intro"``), older files a 3-line form.
    Query :attr:`is_record` first; the field accessors return ``None``
    (or the first line, for :attr:`title`) outside the record shape.
    """

    length: int
    text: str
    lines: tuple[str, ...]

    @classmethod
    def parse(cls, head: bytes) -> PxdComment:
        """Parse the comment field at the start of ``head``.

        ``head`` only needs to contain the whole comment field (``4 +
        length`` bytes); a full file or the engine's 220-byte header
        buffer works.  Raises :class:`PxdError` when the magic, length,
        terminator or encoding is wrong.
        """
        if len(head) < 5:
            raise PxdError("header is too short for a tPxD comment")
        if head[0:4] != PXD_MAGIC:
            raise PxdError("not a tPxD stream (magic %r)" % bytes(head[0:4]))

        length = head[4]
        if length < 2:
            raise PxdError(
                "comment length %d is too small (minimum 2)" % length)
        end = 4 + length
        if end > len(head):
            raise PxdError(
                "comment length %d needs %d bytes, only %d available"
                % (length, end, len(head)))
        if head[end - 1] != 0:
            raise PxdError("comment is not NUL-terminated")

        raw = bytes(head[5:end - 1])
        if 0 in raw:
            raise PxdError("comment contains an embedded NUL")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise PxdError("comment is not ASCII: %s" % exc) from exc

        lines = tuple(text.replace("\r\n", "\n").replace("\r", "\n")
                      .split("\n"))
        return cls(length=length, text=text, lines=lines)

    # The six library-record lines of ``lines``, by index.
    _NAME1_LINE = 0    # display name, part 1
    _NAME2_LINE = 1    # display name, part 2 / hyper-bank sequential id
    _PRODUCER_LINE = 2
    _EMPTY_LINE = 3
    _CATEGORY_LINE = 4
    _BAR_LINE = 5

    @property
    def is_record(self) -> bool:
        """True when the comment has the six-line bank-record shape."""
        return len(self.lines) == 6

    @property
    def name_parts(self) -> tuple[str, ...]:
        """The two name lines of a record, or ``()`` in other shapes.

        In the hyper bank (``r1hg0001``-``r1hg0128``, absent from the
        sample index) line 2 is the sample's unique sequential id
        ``001``-``128`` instead of a name part.
        """
        if not self.is_record:
            return ()
        return (self.lines[self._NAME1_LINE],
                self.lines[self._NAME2_LINE])

    @property
    def title(self) -> str:
        """Display name: the name lines joined with a single space.

        For the record shape these are lines 1 and 2 (so a hyper sound
        shows as e.g. ``"Peel off 001"``); for any other shape, the
        first line alone (e.g. ``"Rave eJay Intro"``).
        """
        parts = self.lines[0:2] if self.is_record else self.lines[0:1]
        return " ".join(part for part in parts if part)

    @property
    def producer(self) -> str | None:
        """Producer/product tag (record line 3); ``None`` elsewhere."""
        if not self.is_record:
            return None
        return self.lines[self._PRODUCER_LINE]

    @property
    def category(self) -> str | None:
        """Category / browser group (record line 5); ``None`` elsewhere."""
        if not self.is_record:
            return None
        return self.lines[self._CATEGORY_LINE]

    @property
    def bar_frames(self) -> int | None:
        """Bar-grid size in frames (record line 6); ``None`` elsewhere.

        ``58800`` in every bank file, whatever the sample's own length:
        the value is the bar size, not the sample length.  A sample's
        own length is the header's frame count.
        """
        if not self.is_record:
            return None
        try:
            return int(self.lines[self._BAR_LINE])
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# the fixed header (docs/formats/PXD_FORMAT.md, container structure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PxdHeader:
    """The structural header of a ``tPxD`` stream.

    Behind the comment sit two unverified marker bytes (``0x00 0x54`` in
    every known file; both header readers skip them), the ``i32`` frame
    count at ``4 + comment.length + 2``, and two padding bytes.  The
    DPCM stream starts at ``data_offset`` (= ``4 + comment.length + 8``).
    """

    comment: PxdComment
    marker: bytes        # the two bytes between comment and frame count
    frame_count: int     # mono samples in the output at 44.1 kHz
    data_offset: int     # first byte of the DPCM/codebook stream

    @classmethod
    def parse(cls, data: bytes) -> PxdHeader:
        """Parse the header of a whole ``tPxD`` file or buffer."""
        comment = PxdComment.parse(data)
        offset = 4 + comment.length
        if offset + 8 > len(data):
            raise PxdError("tPxD header is truncated")
        marker = bytes(data[offset:offset + 2])
        (frame_count,) = struct.unpack_from("<i", data, offset + 2)
        return cls(comment=comment, marker=marker, frame_count=frame_count,
                   data_offset=offset + 8)

    @property
    def duration_seconds(self) -> float:
        """Length of the audio in seconds at 44.1 kHz."""
        return self.frame_count / float(PXD_SAMPLE_RATE)


# ---------------------------------------------------------------------------
# the decoder (``sub_10016361``, docs/formats/PXD_FORMAT.md)
# ---------------------------------------------------------------------------


# The gain ``sub_100149E0`` publishes for the file conversion path
# (``pan = 512``, ``volume = 0x10000``): ``(512 * 0x10000) >> 8``, a 2x
# scale of the 16-bit DPCM integrator.
_FILE_GAIN = 0x20000

_BOOK_ENTRY_SIZE = 16
# ``sub_1001186B`` allocates ``malloc(0x1FA4)`` - 256 entries plus slack,
# so a definition of up to 11 deltas at entry 255 (which overruns the
# slot into its neighbour) stays inside the buffer.
_BOOK_SIZE = 8100
# Entry 0 as written by ``sub_10011EFF``: silent (all zero deltas), then
# the int16 terminator.
_SILENT_ENTRY = (0, 0, 0, 0, 0, -1)
_ENTRY_TERMINATOR = -1


def _build_delta_table() -> tuple[int, ...]:
    """Build the engine's 256-entry DPCM delta book (``sub_10011EFF``).

    A symmetric, roughly logarithmic ladder of step sizes, built by
    accumulating an exponentially growing increment around index 128
    (which is 0), mirroring the negative half, then doubling and storing
    each entry as int16.  Properties (verified):
    ``t[128] == 0``, ``t[127] == -2``, ``t[129] == 2``, range ±25266.
    """
    v1, v20 = 2.2, 1.0565
    t = [0] * 257
    for j in range(1, 128):
        if j >= 6:
            t[j + 128] = int(v1 - 0.52) + t[j + 127]
        else:
            t[j + 128] = t[j + 127] + 1
        v1 *= v20
        v20 -= 0.00022
    for k in range(1, 129):
        t[128 - k] = -t[k + 128]
    out = []
    for m in range(256):
        v = (t[m] * 2) & 0xFFFF
        out.append(v - 0x10000 if v & 0x8000 else v)
    return tuple(out)


DELTA_TABLE = _build_delta_table()


def _wrap16(value: int) -> int:
    """int16 wrap of the DPCM integrator (C 16-bit arithmetic)."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _s16(buf: bytes, offset: int) -> int:
    """Read a signed little-endian int16 from a buffer."""
    (value,) = struct.unpack_from("<h", buf, offset)
    return value


def _put16(buf: bytearray, offset: int, value: int) -> None:
    """Store a masked little-endian int16 into a buffer."""
    struct.pack_into("<h", buf, offset, value)


def _sample(acc: int, gain: int) -> int:
    """Scale one integrator value by ``gain`` (the ``emit()`` step).

    ``(acc * gain) >> 16``, with the signed 32-bit IMUL handling of the
    original: on overflow the sample clamps to ``0x7FFF`` / ``0x8000``
    depending on the sign of the product.
    """
    prod = acc * gain
    if prod > 0x7FFFFFFF or prod < -0x80000000:
        return 0x7FFF if prod > 0 else -0x8000
    word = (prod >> 16) & 0xFFFF
    return word - 0x10000 if word & 0x8000 else word


class PxdDecoder:
    """The ``tPxD`` DPCM/code-book decoder (``sub_10016361``).

    The stream is byte code over a runtime code book of 256 entries,
    ``_BOOK_ENTRY_SIZE`` bytes each, held as int16 deltas terminated by
    ``0xFFFF``.  Opcodes:

    * ``0x00..0xF3`` — play code book entry ``byte``;
    * ``0xFF`` — one step: add ``DELTA_TABLE[next byte]`` to the
      integrator;
    * ``0xF4..0xFE`` — define entry ``next byte`` from ``opcode - 0xF3``
      (1..11) ``DELTA_TABLE`` deltas, then play it.  (Hex-Rays shows
      ``opcode + 13`` because of char→int sign extension; the actual
      count is 1..11.)

    Each applied delta wraps the 16-bit integrator; ``gain`` (default: the
    file-conversion gain ``_FILE_GAIN``) scales what is emitted.
    """

    def __init__(self, stream: bytes, frames: int,
                 gain: int = _FILE_GAIN):
        self.stream = stream
        self.frames = frames
        self.gain = gain

    def decode(self) -> array.array:
        """Return the decoded stream as mono int16 samples.

        Exactly ``frames`` samples are produced - a byte code that ends
        early is heard as silence, matching ``RWavToTemp`` truncating its
        output to the declared length.  The default gain reproduces the
        engine's file conversion, which doubles the integrator.
        """
        data, frames, gain = self.stream, self.frames, self.gain
        out = array.array("h")
        if frames <= 0:
            return out

        book = bytearray(_BOOK_SIZE)
        struct.pack_into("<6h", book, 0, *_SILENT_ENTRY)
        table = DELTA_TABLE
        end = len(data)
        pos = 0
        acc = 0

        while pos < end and len(out) < frames:
            code = data[pos]
            if code >= 0xF4:
                if code == 0xFF:
                    if pos + 2 > end:
                        break
                    acc = _wrap16(acc + table[data[pos + 1]])
                    pos += 2
                    out.append(_sample(acc, gain))
                    continue
                if pos + 2 > end:
                    break
                idx = data[pos + 1]
                count = code - 0xF3            # (char)(opcode + 13)
                pos += 2
                if pos + count > end:
                    break
                base = _BOOK_ENTRY_SIZE * idx
                for k in range(count):
                    _put16(book, base + 2 * k, table[data[pos + k]])
                _put16(book, base + 2 * count, _ENTRY_TERMINATOR)
                pos += count
                entry = base
            else:
                pos += 1
                entry = _BOOK_ENTRY_SIZE * code

            # play the entry; an entry is never cut in half by the bounds
            while len(out) < frames:
                delta = _s16(book, entry)
                if delta == _ENTRY_TERMINATOR:
                    break
                acc = _wrap16(acc + delta)
                out.append(_sample(acc, gain))
                entry += 2

        if len(out) < frames:
            out.extend(array.array("h", bytes(2 * (frames - len(out)))))
        return out


# ---------------------------------------------------------------------------
# the file (entry point)
# ---------------------------------------------------------------------------


class PxdFile:
    """A ``.pxd`` file on disk: header metadata and decoded samples.

    ``header()`` and ``samples()`` are lazy and cached; reading the file
    happens on first use only.
    """

    def __init__(self, filename):
        self.filename = filename
        self._contents = None
        self._header = None
        self._samples = None

    def _load(self) -> bytes:
        """Return the file contents, reading them once."""
        if self._contents is None:
            try:
                with open(self.filename, "rb") as fh:
                    self._contents = fh.read()
            except OSError as exc:
                raise PxdError("%s: %s" % (self.filename, exc)) from exc
        return self._contents

    def header(self) -> PxdHeader:
        """Return the parsed ``tPxD`` header."""
        if self._header is None:
            self._header = PxdHeader.parse(self._load())
        return self._header

    def frames(self) -> int:
        """Number of mono PCM samples the stream declares."""
        return self.header().frame_count

    def duration_seconds(self) -> float:
        """Length of the audio in seconds at 44.1 kHz."""
        return self.header().duration_seconds

    def samples(self) -> array.array:
        """Return the decoded stream as mono int16 at 44.1 kHz."""
        if self._samples is None:
            data, header = self._load(), self.header()
            decoder = PxdDecoder(data[header.data_offset:],
                                 header.frame_count)
            self._samples = decoder.decode()
        return self._samples

    def __repr__(self):
        return "PxdFile(%r)" % (self.filename,)
