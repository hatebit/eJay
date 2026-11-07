"""Verification for the reference ``tP`` byte-code decoder.

Run:  python test_tp_codec.py

The opcode cases pin the table and the sample math of
``../docs/PXD32D4.md`` section 10.3 with a simple ``ladder[i] == int8(i)``
stand-in.  The decoded builder (``tp_codec.d4_delta_table``) is additionally
locked value for value against the ported family table
``pxd32d5.DELTA_TABLE``.
"""

import struct

import pxd32d5
import tp_codec

LADDER = [i if i < 128 else i - 256 for i in range(256)]


def test_play_row(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.set_row(2, (100, -50))
    out = bytearray(4 * 4)
    struct.pack_into("<h", out, 2, 1234)          # right channel, frame 0
    assert dec.decode(b"\x02", out) == (1, 2)
    assert tp_codec.left_samples(out, 4) == [100, 50, 0, 0]
    assert dec.acc == 50
    assert struct.unpack_from("<h", out, 2)[0] == 1234
    assert struct.unpack_from("<h", out, 6)[0] == 0


def test_accrues_into_existing_left_word(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.set_row(0, (100, -50))
    out = bytearray(8)
    struct.pack_into("<hh", out, 0, 1000, 7)
    struct.pack_into("<hh", out, 4, -1000, 7)
    assert dec.decode(b"\x00", out) == (1, 2)
    assert tp_codec.left_samples(out, 2) == [1100, -950]
    assert struct.unpack_from("<h", out, 2)[0] == 7
    assert struct.unpack_from("<h", out, 6)[0] == 7


def test_gain_scales_the_accumulator(tmp):
    dec = tp_codec.TpDecoder(LADDER, gain=1 << 15)
    dec.set_row(0, (100,))
    out = bytearray(4)
    assert dec.decode(b"\x00", out) == (1, 1)
    assert tp_codec.left_samples(out, 1) == [50]


def test_single_step_opcode(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    out = bytearray(8)
    assert dec.decode(b"\xff\x05\xff\xfe", out) == (4, 2)
    assert tp_codec.left_samples(out, 2) == [5, 3]
    assert dec.acc == 3


def test_define_then_play(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    out = bytearray(4 * 3)
    # 0xF6 -> three steps, row 9, ladder indices 1, 2, 3.
    assert dec.decode(b"\xf6\x09\x01\x02\x03", out) == (5, 3)
    assert dec.steps(9) == [1, 2, 3]
    assert tp_codec.left_samples(out, 3) == [1, 3, 6]
    assert struct.unpack_from("<H", dec.book, 9 * 16 + 6)[0] == 0xFFFF


def test_define_counts_one_and_eleven(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    out = bytearray(4 * 11)
    data = b"\xfe\x05" + bytes([10] * 11)
    assert dec.decode(data, out) == (13, 11)
    assert dec.steps(5) == [10] * 11
    assert tp_codec.left_samples(out, 11) == [10 * n for n in range(1, 12)]

    one = tp_codec.TpDecoder(LADDER)
    small = bytearray(4)
    assert one.decode(b"\xf4\x07\x0a", small) == (3, 1)
    assert tp_codec.left_samples(small, 1) == [10]


def test_saturating_add(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.set_row(0, (30000,))
    out = bytearray(4)
    struct.pack_into("<h", out, 0, 30000)
    dec.decode(b"\x00", out)
    assert tp_codec.left_samples(out, 1) == [32767]

    low = tp_codec.TpDecoder(LADDER)
    low.set_row(0, (-30000,))
    buf = bytearray(4)
    struct.pack_into("<h", buf, 0, -30000)
    low.decode(b"\x00", buf)
    assert tp_codec.left_samples(buf, 1) == [-32768]


def test_pending_sample_is_emitted_once(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.acc = 1234
    dec.pending = True
    dec.set_row(0, (10,))
    out = bytearray(8)
    assert dec.decode(b"\x00", out) == (1, 2)
    assert tp_codec.left_samples(out, 2) == [1234, 1244]
    assert dec.pending is False


def test_run_is_not_cut_at_the_frame_limit(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.set_row(0, (1, 2, 3, 4, 5))
    out = bytearray(4 * 2)
    assert dec.decode(b"\x00", out, frames=2) == (1, 2)
    assert tp_codec.left_samples(out, 2) == [1, 3]
    assert dec.acc == 15


def test_truncated_unit_is_not_consumed(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    out = bytearray(4 * 4)
    assert dec.decode(b"\xf6\x09\x01", out) == (0, 0)
    assert dec.decode(b"\xff", out) == (0, 0)
    assert dec.decode(b"", out) == (0, 0)
    assert tp_codec.left_samples(out, 4) == [0, 0, 0, 0]


def test_set_row_rejects_more_than_eleven_steps(tmp):
    dec = tp_codec.TpDecoder(LADDER)
    dec.set_row(0, [1] * 11)
    try:
        dec.set_row(0, [1] * 12)
    except ValueError:
        return
    raise AssertionError("12 steps must be rejected")


def test_d4_ladder_matches_the_ported_family_table(tmp):
    table = tp_codec.d4_delta_table()
    assert table == pxd32d5.DELTA_TABLE
    assert table[128] == 0
    assert table[127] == -table[129]
    assert (min(table), max(table)) == (-25266, 25266)
    assert tp_codec.TpDecoder().ladder == table


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(None)
            print("ok  %s" % name)
    print("all passed")


if __name__ == "__main__":
    main()
