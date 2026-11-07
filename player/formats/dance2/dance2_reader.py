"""Byte-level reader for Dance eJay 2.0 ``.MIX`` files."""

from __future__ import annotations

import struct

from ...format_error import FormatError
from .dance2_kit import Dance2Kit
from .dance2_mix_data import Dance2MixData
from .dance2_palette_entry import Dance2PaletteEntry
from .dance2_sample_event import Dance2SampleEvent
from .dance2_text_event import Dance2TextEvent
from .dance2_track_settings import Dance2TrackSettings

MIX_MAGIC = 0x0A19
MIX_FOOTER = b"\xa9\x7a\x8a\x01"
TEXT_OFFSET = 0x10
NAME_SUFFIX = b"\x00\x01"
PALETTE_TAG = 0x01000002
TRACKS = 17
SAMPLE_TRACKS = 16
SONG_SETTINGS_BYTES = 22
SHORT_BYTES = 7
LONG_BYTES = 17
TEXT_PREFIX_BYTES = 27
MAX_KITS = 64
DEFAULT_BPM = 140.0


class Dance2Reader:
    """Read the sections of a Dance eJay 2.0 mix in file order."""

    def read(self, data: bytes, name: str = "") -> Dance2MixData:
        """Parse a complete mix.

        Args:
            data: Whole ``.MIX`` file.
            name: File name used in error messages.

        Returns:
            The parsed container.

        Raises:
            FormatError: The file is too short, has the wrong magic or
                footer, or a section does not end where the next one starts.
        """
        label = name or "<mix>"
        if len(data) < TEXT_OFFSET:
            raise FormatError(f"{label}: too short for a Dance eJay 2.0 mix")
        magic = struct.unpack_from("<H", data, 0)[0]
        if magic != MIX_MAGIC:
            raise FormatError(
                f"{label}: header 0x{magic:04X}, "
                f"expected 0x{MIX_MAGIC:04X}")
        if not data.endswith(MIX_FOOTER):
            raise FormatError(f"{label}: missing 0x018A7AA9 footer")

        header = tuple(struct.unpack_from("<8H", data, 0))
        bpm = float(header[4]) if 40 <= header[4] <= 300 else DEFAULT_BPM

        title, position = _cstring(data, TEXT_OFFSET, label, "title")
        subtitle, position = _cstring(data, position, label, "subtitle")
        description, position = _description(data, position, label)

        settings, position = _track_settings(data, position, label)
        position += 8                      # two zeroed reserved pairs

        catalog_name, catalog_count, position = _catalog(
            data, position, label)
        kits, position = _kits(
            data, position, label, catalog_count)
        palette, position = _palette(data, position, label)

        if position + SONG_SETTINGS_BYTES > len(data):
            raise FormatError(f"{label}: song settings are truncated")
        song_settings = data[position:position + SONG_SETTINGS_BYTES]
        position += SONG_SETTINGS_BYTES

        limit = len(data) - len(MIX_FOOTER)
        sample_events, position = _sample_events(
            data, position, limit, label)
        text_events, position = _text_events(data, position, limit, label)
        if position != limit or data[position:] != MIX_FOOTER:
            raise FormatError(f"{label}: event table does not end at footer")

        return Dance2MixData(
            header=header,
            bpm=bpm,
            tempo_aux=header[5],
            title=title,
            subtitle=subtitle,
            description=description,
            catalog_name=catalog_name,
            catalog_count=catalog_count,
            kits=kits,
            palette=palette,
            track_settings=settings,
            song_settings=song_settings,
            sample_events=sample_events,
            text_events=text_events,
        )


def _need(data: bytes, position: int, count: int, label: str,
          what: str) -> None:
    """Raise when ``count`` bytes at ``position`` run past the file."""
    if position < 0 or position + count > len(data):
        raise FormatError(f"{label}: {what} is truncated")


def _u16(data: bytes, position: int, label: str, what: str) -> int:
    """Read a little-endian u16 after a bounds check."""
    _need(data, position, 2, label, what)
    return struct.unpack_from("<H", data, position)[0]


def _u32(data: bytes, position: int, label: str, what: str) -> int:
    """Read a little-endian u32 after a bounds check."""
    _need(data, position, 4, label, what)
    return struct.unpack_from("<I", data, position)[0]


def _cstring(data: bytes, position: int, label: str,
             what: str) -> tuple[str, int]:
    """Read a NUL-terminated string plus the offset after it."""
    end = data.find(b"\x00", position)
    if position < 0 or end < 0:
        raise FormatError(f"{label}: {what} is not NUL-terminated")
    text = data[position:end].decode("latin-1", "replace")
    return text, end + 1


def _text(raw: bytes) -> str:
    """Decode a stored name and drop its ``00 01`` terminator."""
    if raw.endswith(NAME_SUFFIX):
        raw = raw[:-2]
    return raw.rstrip(b"\x00").decode("latin-1", "replace")


def _description(data: bytes, position: int, label: str
                 ) -> tuple[str, int]:
    """Read the ``01 + u16 length + bytes`` description block."""
    _need(data, position, 3, label, "description")
    if data[position] != 1:
        raise FormatError(
            f"{label}: description marker 0x{data[position]:02X}, "
            "expected 0x01")
    length = struct.unpack_from("<H", data, position + 1)[0]
    position += 3
    _need(data, position, length, label, "description")
    raw = data[position:position + length]
    if not raw.endswith(NAME_SUFFIX):
        raise FormatError(f"{label}: description lacks its 00 01 terminator")
    return _text(raw), position + length


def _track_settings(data: bytes, position: int, label: str
                    ) -> tuple[tuple[Dance2TrackSettings, ...], int]:
    """Read the sixteen pan/volume pairs."""
    _need(data, position, SAMPLE_TRACKS * 4, label, "track settings")
    settings = []
    for track in range(1, SAMPLE_TRACKS + 1):
        pan, volume = struct.unpack_from("<2H", data, position)
        settings.append(Dance2TrackSettings(track, pan, volume))
        position += 4
    return tuple(settings), position


def _catalog(data: bytes, position: int, label: str
             ) -> tuple[str, int, int]:
    """Read the catalog name, kit count and two year fields."""
    _u16(data, position, label, "catalog prefix")
    position += 2
    length = _u16(data, position, label, "catalog name length")
    position += 2
    _need(data, position, length, label, "catalog name")
    name = _text(data[position:position + length])
    position += length
    count = _u16(data, position, label, "kit count")
    position += 2
    _need(data, position, 8, label, "catalog years")
    position += 8
    if not 0 < count <= MAX_KITS:
        raise FormatError(f"{label}: kit count {count} is implausible")
    return name, count, position


def _kits(data: bytes, position: int, label: str, count: int
          ) -> tuple[tuple[Dance2Kit, ...], int]:
    """Read ``count`` kit records."""
    kits = []
    for _ in range(count):
        length = _u16(data, position, label, "kit name length")
        position += 2
        _need(data, position, length, label, "kit name")
        name = _text(data[position:position + length])
        position += length
        _need(data, position, 8, label, "kit range")
        first, last = struct.unpack_from("<II", data, position)
        position += 8
        kits.append(Dance2Kit(name, first, last))
    return tuple(kits), position


def _palette(data: bytes, position: int, label: str
             ) -> tuple[tuple[Dance2PaletteEntry, ...], int]:
    """Read the tagged sample palette."""
    tag = _u32(data, position, label, "palette header")
    if tag != PALETTE_TAG:
        raise FormatError(
            f"{label}: palette header 0x{tag:08X}, "
            f"expected 0x{PALETTE_TAG:08X}")
    position += 4
    entries = []
    while position + 4 <= len(data) - len(MIX_FOOTER):
        if _u32(data, position, label, "palette entry") != PALETTE_TAG:
            break
        position += 4
        sample_id = _u16(data, position, label, "palette id")
        length = _u16(data, position + 2, label, "palette name length")
        position += 4
        _need(data, position, length, label, "palette name")
        name = _text(data[position:position + length])
        position += length
        _need(data, position, 8, label, "palette parameters")
        first, second = struct.unpack_from("<II", data, position)
        position += 8
        entries.append(Dance2PaletteEntry(sample_id, name, first, second))
    return tuple(entries), position


def _sample_events(data: bytes, position: int, limit: int, label: str
                   ) -> tuple[tuple[Dance2SampleEvent, ...], int]:
    """Read the sixteen sample-track blocks."""
    events = []
    for track in range(1, SAMPLE_TRACKS + 1):
        if position + 5 > limit:
            raise FormatError(f"{label}: track table is truncated")
        found, count = struct.unpack_from("<BI", data, position)
        position += 5
        if found != track:
            raise FormatError(
                f"{label}: expected track {track}, got {found}")
        for _ in range(count):
            if position + SHORT_BYTES > limit:
                raise FormatError(f"{label}: sample event is truncated")
            flag, time, second = struct.unpack_from("<Bhh", data, position)
            size = LONG_BYTES if time >= 0 else SHORT_BYTES
            if position + size > limit:
                raise FormatError(f"{label}: sample event is truncated")
            sample_id = struct.unpack_from("<H", data, position + 5)[0]
            extension = (data[position + SHORT_BYTES:position + LONG_BYTES]
                         if size == LONG_BYTES else b"")
            units = time if time >= 0 else -(time + 1)
            events.append(Dance2SampleEvent(
                track=track,
                units=units,
                flag=flag,
                sample_id=sample_id,
                long=size == LONG_BYTES,
                extension=extension,
            ))
            position += size
    return tuple(events), position


def _text_events(data: bytes, position: int, limit: int, label: str
                 ) -> tuple[tuple[Dance2TextEvent, ...], int]:
    """Read the lyric block on track 17."""
    if position + 5 > limit:
        raise FormatError(f"{label}: text track is truncated")
    found, count = struct.unpack_from("<BI", data, position)
    position += 5
    if found != TRACKS:
        raise FormatError(
            f"{label}: expected text track {TRACKS}, got {found}")
    events = []
    for _ in range(count):
        if position + TEXT_PREFIX_BYTES > limit:
            raise FormatError(f"{label}: text event is truncated")
        flag, time, second = struct.unpack_from("<Bhh", data, position)
        prefix = data[position + 5:position + TEXT_PREFIX_BYTES]
        units = time if time >= 0 else -(time + 1)
        position += TEXT_PREFIX_BYTES
        name, position = _sized_text(data, position, limit, label,
                                     "text name")
        if position + 2 > limit:
            raise FormatError(f"{label}: text value is truncated")
        length = struct.unpack_from("<H", data, position)[0]
        position += 2
        if position + length > limit:
            raise FormatError(f"{label}: text value is truncated")
        value = data[position:position + length]
        position += length
        events.append(Dance2TextEvent(
            units=units,
            flag=flag,
            second=second,
            prefix=prefix,
            name=name,
            value=value,
        ))
    return tuple(events), position


def _sized_text(data: bytes, position: int, limit: int, label: str,
                what: str) -> tuple[str, int]:
    """Read a ``u16 length`` prefixed name."""
    if position + 2 > limit:
        raise FormatError(f"{label}: {what} is truncated")
    length = struct.unpack_from("<H", data, position)[0]
    position += 2
    if position + length > limit:
        raise FormatError(f"{label}: {what} is truncated")
    return _text(data[position:position + length]), position + length
