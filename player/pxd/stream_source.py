"""Bounded, in-memory reads from one sample reference."""

from __future__ import annotations

from .sample_error import SampleError
from .sample_ref import SampleRef


class StreamSource:
    """Hold one sample's bytes and hand them out sequentially.

    Opening is lazy: creating a source does not touch the disk.  The first
    :meth:`open` reads the reference's whole slice (the file, or
    ``offset``..``offset + size`` of the archive) into memory once.  After
    that every read is a slice of ``bytes`` and a decoder may index
    :attr:`data` directly, which avoids a file read per code byte.  A sample
    is a few hundred kilobytes at most, so keeping it resident is cheap, and
    :meth:`reset` only rewinds :attr:`position`.

    Attributes:
        ref: The reference this source reads.
        position: Offset of the next byte, relative to the reference start.
            A decoder that indexes :attr:`data` itself writes its final
            position back here.
    """

    def __init__(self, ref: SampleRef) -> None:
        self.ref = ref
        self.position = 0
        self._data: bytes | None = None

    @property
    def location(self) -> str:
        """Best available name for error messages."""
        return (str(self.ref.path) if self.ref.path is not None
                else self.ref.display_name)

    @property
    def data(self) -> bytes:
        """The whole slice, loaded on first use.

        Raises:
            SampleError: The reference has no location or cannot be read.
        """
        return self.open()._data

    def open(self) -> "StreamSource":
        """Load the reference's bytes if they are not loaded yet.

        Returns:
            This source.

        Raises:
            SampleError: The reference has no location or cannot be read.
        """
        if self._data is not None:
            return self
        ref = self.ref
        if ref.path is None and ref.archive is None:
            raise SampleError(f"{ref.display_name}: no sample location")
        try:
            if ref.path is not None:
                data = ref.path.read_bytes()
            else:
                with ref.archive.open("rb") as handle:
                    handle.seek(ref.offset)
                    data = handle.read(ref.size)
        except OSError as exc:
            raise SampleError(
                f"{self.location}: {exc.strerror or exc}") from exc
        self._data = data
        self.position = 0
        return self

    def seek(self, position: int) -> None:
        """Move to ``position``, relative to the reference start."""
        data = self.open()._data
        self.position = max(0, min(position, len(data)))

    def read(self, count: int) -> bytes:
        """Read up to ``count`` bytes, stopping at the slice end.

        Returns:
            The bytes read; empty at end of stream.

        Raises:
            SampleError: The reference cannot be loaded.
        """
        if count <= 0:
            return b""
        data = self.open()._data
        start = self.position
        chunk = data[start:start + count]
        self.position = start + len(chunk)
        return chunk

    def read_byte(self) -> int | None:
        """Read one byte as an int, or ``None`` at end of stream."""
        data = self.open()._data
        position = self.position
        if position >= len(data):
            return None
        self.position = position + 1
        return data[position]

    def reset(self) -> None:
        """Rewind to the start; the loaded bytes stay in memory."""
        self.position = 0

    def close(self) -> None:
        """Release the loaded bytes; the next read loads them again."""
        self._data = None
        self.position = 0
