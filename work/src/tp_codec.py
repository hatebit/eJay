"""Reference decoder for the eJay ``tP`` ADPCM byte code (PXD32D4.DLL).

Reconstruction of the 16-bit decoder at ``0x1000759D``; see
``../docs/PXD32D4.md`` section 10.3 for the instruction-level evidence.  This
module mirrors the byte-code dispatch and the sample math only - the block
bookkeeping of the wrapper ``0x100059AE`` (source window, gain, code-book
pointer, one-shot carry flag) is the caller's job.

Byte code, dispatched on the first byte at ``0x10007685``::

    0x00..0xF3  play code-book row ``opcode`` at ``codebook + 16*opcode``:
                walk int16 deltas until the 0xFFFF terminator
    0xF4..0xFE  define row: next byte is the row number, the following
                ``opcode - 0xF3`` (1..11) bytes index the delta ladder;
                write the steps, append 0xFFFF, then play that row
    0xFF        one ladder step: next byte is the ladder index

Each emitted sample integrates the int16 accumulator (``word_1003A020``) and
adds ``(int16)acc * gain >> 16`` into the left word of the next 4-byte stereo
frame (``0x100076A7``..``0x100076C3``).  Both adds saturate.

The 256-entry delta ladder is built by :func:`d4_delta_table`
(``0x10003252``..``0x100033A8``) and is the decoder's default.  ``gain`` is
the wrapper's ``(voice+0x7C * voice+0x44) >> 8`` (``0x10005B17``); ``1 << 16``
is unity.
"""

import struct

SENTINEL = 0xFFFF
ROW_SIZE = 16                   # code-book rows are 16 bytes apart
ROW_COUNT = 256                 # the row index is one byte
# The DLL's book is 8100 bytes (malloc(0x1FA4)); the 11-step define opcode
# writes at most 24 bytes into a row, so it never leaves that allocation.
# The reference book adds one spare row instead of masking the index
# (0x10007744, 0x10007762).
BOOK_SIZE = ROW_COUNT * ROW_SIZE + ROW_SIZE
MAX_STEPS = 11                  # 0xFE - 0xF3


def _s16(value):
    """Interpret the low 16 bits of ``value`` as a signed int16."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _wrap16(value):
    """The int16 wrap of ``add dx, ax`` (``0x100076A7``)."""
    return _s16(value)


def _u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


def _put16(buf, off, value):
    struct.pack_into("<H", buf, off, value & 0xFFFF)


def d4_delta_table():
    """The 256-entry DPCM ladder built at ``0x10003252``..``0x100033A8``.

    Two x87 doubles drive it: ``v = 2.2`` minus ``0.52`` (``0x1001F238``)
    is truncated by ``0x10012A00`` (``fistp`` with round-to-zero) and added
    to the previous step for indices 6..127; the first five steps grow by
    one.  ``v *= 1.0565`` and ``step -= 0.00022`` (``0x1001F240``) close the
    loop, the positive half is mirrored around index 128 = 0, and every
    entry is doubled with a 16-bit ``shl``.

    The result is value-for-value identical to the ported family ladder
    ``pxd32d5.DELTA_TABLE``.
    """
    value, step = 2.2, 1.0565
    table = [0] * 257
    for j in range(1, 128):
        if j < 6:
            table[128 + j] = _wrap16(table[127 + j] + 1)
        else:
            table[128 + j] = _wrap16(table[127 + j] + int(value - 0.52))
        value *= step
        step -= 0.00022
    for k in range(1, 129):
        table[128 - k] = _wrap16(-table[128 + k])
    return [_wrap16(v << 1) for v in table[:256]]


class TpDecoder:
    """Decoder state: accumulator, code book and the one-shot carry flag."""

    def __init__(self, ladder=None, book=None, gain=1 << 16):
        """Create a decoder.

        Args:
            ladder: 256 int16 delta step sizes, indexed by the byte operands
                of ``0xFF`` and ``0xF4``..``0xFE``; defaults to
                :func:`d4_delta_table`.
            book: optional initial code book; short buffers are padded with
                zeros, an 8100-byte one is used as is.
            gain: 16.16 gain word applied to every sample.

        Raises:
            ValueError: if ``ladder`` has fewer than 256 entries.
        """
        if ladder is None:
            ladder = d4_delta_table()
        if len(ladder) < ROW_COUNT:
            raise ValueError("ladder needs 256 entries")
        self.ladder = [_s16(v) for v in ladder]
        self.book = bytearray(book) if book is not None else bytearray()
        if len(self.book) < BOOK_SIZE:
            self.book.extend(bytes(BOOK_SIZE - len(self.book)))
        self.gain = gain
        self.acc = 0            # word_1003A020, int16 DPCM integrator
        self.pending = False    # word_10039FFC, emit acc once before decoding

    def set_row(self, row, steps):
        """Write ``steps`` and the 0xFFFF terminator into code-book ``row``.

        Raises:
            ValueError: if more than 11 steps are given (the largest count the
                define opcode can produce).
        """
        if len(steps) > MAX_STEPS:
            raise ValueError("a code-book row holds at most %d steps"
                             % MAX_STEPS)
        base = row * ROW_SIZE
        for i, value in enumerate(steps):
            _put16(self.book, base + 2 * i, value)
        _put16(self.book, base + 2 * len(steps), SENTINEL)

    def steps(self, row):
        """The deltas of ``row`` up to the 0xFFFF terminator."""
        out = []
        off = row * ROW_SIZE
        while off + 2 <= len(self.book):
            value = _u16(self.book, off)
            off += 2
            if value == SENTINEL:
                break
            out.append(_s16(value))
        return out

    def decode(self, data, out, frames=None):
        """Decode ``data`` into ``out``; return ``(consumed, produced)``.

        ``out`` is a writable buffer of 4-byte stereo frames; only the low
        word of each frame is touched, because the decoder strides 4
        (``add esi, 4``) and never writes the right channel.

        Args:
            data: byte-code block.
            out: destination buffer, at least ``4 * frames`` bytes.
            frames: frame budget; defaults to ``len(out) // 4``.

        Returns:
            ``(bytes consumed from ``data``, frames written)``.  A truncated
            trailing unit is not consumed at all, which differs from the DLL
            (it would read past the block).
        """
        room = len(out) // 4 if frames is None else frames
        room = min(room, len(out) // 4)
        pos = 0
        made = 0
        if self.pending:
            self.pending = False
            if made < room:
                self._emit(out, 4 * made)
                made += 1
        while made < room and pos < len(data):
            opcode = data[pos]
            if opcode < 0xF4:
                pos += 1
                made += self._play(out, 4 * made, room - made, opcode)
            elif opcode == 0xFF:
                if pos + 1 >= len(data):
                    break
                self.acc = _wrap16(self.acc + self.ladder[data[pos + 1]])
                if made < room:
                    self._emit(out, 4 * made)
                    made += 1
                pos += 2
            else:
                count = opcode - 0xF3
                if pos + 2 + count > len(data):
                    break
                row = data[pos + 1]
                for k in range(count):
                    _put16(self.book, row * ROW_SIZE + 2 * k,
                           self.ladder[data[pos + 2 + k]])
                _put16(self.book, row * ROW_SIZE + 2 * count, SENTINEL)
                pos += 2 + count
                made += self._play(out, 4 * made, room - made, row)
        return pos, made

    def _play(self, out, off, room, row):
        """Walk one code-book row; return the number of frames written.

        The DLL checks the destination only between byte-code units
        (``0x1000777B``), so a row is never cut in half: the whole run is
        integrated even when the caller's frame budget is already full.
        """
        base = row * ROW_SIZE
        written = 0
        i = 0
        while base + i + 2 <= len(self.book):
            value = _u16(self.book, base + i)
            i += 2
            if value == SENTINEL:
                break
            self.acc = _wrap16(self.acc + _s16(value))
            if written < room:
                self._emit(out, off + 4 * written)
                written += 1
        return written

    def _emit(self, out, off):
        """Add one scaled sample to the left word at ``off``.

        ``imul`` overflow clamps to ``0x7FFF`` / ``0x8000`` (``0x10007613``);
        the final ``add word ptr [esi], ax`` saturates too (``0x1000765B``..
        ``0x10007669``), storing ``0x7FFF`` for a positive overflow and
        ``0x8000`` for a negative one.
        """
        product = _s16(self.acc) * self.gain
        if product > 0x7FFFFFFF or product < -0x80000000:
            word = 0x7FFF if product > 0 else 0x8000
        else:
            word = (product >> 16) & 0xFFFF
        total = _s16(_u16(out, off)) + _s16(word)
        if total > 0x7FFF:
            total = 0x7FFF
        elif total < -0x8000:
            total = -0x8000
        _put16(out, off, total)


def left_samples(out, frames):
    """The left channel of ``frames`` 4-byte frames, as signed int16."""
    return [_s16(_u16(out, 4 * i)) for i in range(frames)]
