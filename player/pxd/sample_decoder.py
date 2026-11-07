"""Common sample decoding: reference -> PCM, independent of the mix format."""

from __future__ import annotations

import array

from .pxd_decoder import PxdDecoder
from .pxd_stream_decoder import PxdStreamDecoder
from .riff_decoder import RiffDecoder
from .riff_stream_decoder import RiffStreamDecoder
from .sample_bank import SampleBank
from .sample_collection import SampleCollection
from .sample_error import SampleError
from .sample_ref import SampleRef
from .sample_stream import SampleStream
from .stream_source import StreamSource

HEADER_BYTES = 4096
"""Bytes read to learn a sample's declared frame count."""


class SampleDecoder:
    """Decode sample references into a :class:`SampleBank`.

    The decoder owns the codecs, so a new mix format only has to say *where*
    a sample lives, not how to decode it.  A collection becomes a bank of
    streams: only each header is read up front, and the PCM is decoded in
    block-sized windows while playback advances.
    """

    def __init__(self, tp_decoder: PxdDecoder | None = None,
                 riff_decoder: RiffDecoder | None = None) -> None:
        self._tp = tp_decoder or PxdDecoder()
        self._riff = riff_decoder or RiffDecoder()

    def decode_bytes(self, data: bytes) -> array.array:
        """Decode one sample stream by its magic.

        Args:
            data: Whole sample stream.

        Returns:
            Mono int16 frames at 44.1 kHz.

        Raises:
            SampleError: The stream magic is unknown or decoding fails.
        """
        if data[0:2] == b"tP":
            return self._tp.decode(data)
        if data[0:4] == b"RIFF":
            return self._riff.decode(data)
        raise SampleError("unknown sample format")

    def length_bytes(self, data: bytes) -> int:
        """Return the frame count a sample stream declares.

        Only the header is inspected; no PCM is decoded.

        Args:
            data: Whole sample stream, or at least its header.

        Returns:
            Declared mono int16 frames at 44.1 kHz.

        Raises:
            SampleError: The stream magic is unknown or the header is bad.
        """
        if data[0:2] == b"tP":
            return self._tp.length(data)
        if data[0:4] == b"RIFF":
            return self._riff.length(data)
        raise SampleError("unknown sample format")

    def decode_file(self, path) -> array.array:
        """Decode a standalone sample file.

        Args:
            path: File to read.

        Returns:
            Mono int16 frames at 44.1 kHz.

        Raises:
            SampleError: The file cannot be read or decoded.
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise SampleError(f"{path}: {exc.strerror or exc}") from exc
        try:
            return self.decode_bytes(data)
        except SampleError as exc:
            raise SampleError(f"{path}: {exc}") from exc

    def decode_ref(self, ref: SampleRef) -> array.array:
        """Decode the stream a :class:`SampleRef` points at.

        Args:
            ref: Reference to a standalone file or an archive slice.

        Returns:
            Mono int16 frames at 44.1 kHz.

        Raises:
            SampleError: The reference has no location, or decoding fails.
        """
        if ref.path is None and ref.archive is None:
            raise SampleError(f"{ref.display_name}: no sample location")
        data = self._read_ref(ref, None)
        try:
            return self.decode_bytes(data)
        except SampleError as exc:
            raise self._located(ref, exc) from exc

    def decode_length(self, ref: SampleRef) -> int:
        """Return the frame count ``ref`` declares, without decoding it.

        A header is normally smaller than :data:`HEADER_BYTES`; when the
        payload is larger, the reference is read again so the header can be
        checked against the whole stream.

        Args:
            ref: Reference to a standalone file or an archive slice.

        Returns:
            Declared mono int16 frames at 44.1 kHz.

        Raises:
            SampleError: The reference has no location, the header is bad, or
                the stream is truncated.
        """
        if ref.path is None and ref.archive is None:
            raise SampleError(f"{ref.display_name}: no sample location")
        data = self._read_ref(ref, HEADER_BYTES)
        try:
            return self.length_bytes(data)
        except SampleError as exc:
            if len(data) < HEADER_BYTES:
                raise self._located(ref, exc) from exc
        data = self._read_ref(ref, None)
        try:
            return self.length_bytes(data)
        except SampleError as exc:
            raise self._located(ref, exc) from exc

    def open_stream(self, ref: SampleRef, frames: int
                    ) -> PxdStreamDecoder | RiffStreamDecoder:
        """Open an incremental decoder for one sample reference.

        Args:
            ref: Reference to a standalone file or an archive slice.
            frames: Declared frame count from the header.

        Returns:
            A decoder whose ``read`` produces block-sized windows.

        Raises:
            SampleError: The reference has no location, cannot be read, or
                has unknown magic.
        """
        if ref.path is None and ref.archive is None:
            raise SampleError(f"{ref.display_name}: no sample location")
        source = StreamSource(ref)
        head = source.data[0:4]
        if head[0:2] == b"tP":
            return PxdStreamDecoder(source, frames)
        if head[0:4] == b"RIFF":
            return RiffStreamDecoder(source, frames)
        raise self._located(ref, SampleError("unknown sample format"))

    def decode_collection(self,
                          collection: SampleCollection) -> SampleBank:
        """Turn every reference in ``collection`` into a lazy stream.

        Header problems are recorded in ``bank.errors`` and that sample is
        skipped.  The audio itself is decoded later, when playback reaches
        the sample.

        Args:
            collection: References resolved by a mix format.

        Returns:
            A bank holding one stream per usable reference, plus one error
            message per reference that could not be read.
        """
        bank = SampleBank()
        for sample_id in collection.ids:
            ref = collection.refs[sample_id]
            try:
                frames = self.decode_length(ref)
            except SampleError as exc:
                bank.errors.append(str(exc))
                continue
            bank.add_stream(
                SampleStream(sample_id, frames, ref=ref, decoder=self,
                             errors=bank.errors),
                ref.display_name)
        return bank

    @staticmethod
    def _read_ref(ref: SampleRef, limit: int | None) -> bytes:
        """Read up to ``limit`` bytes of a reference, or all of it."""
        if ref.path is not None:
            try:
                with ref.path.open("rb") as handle:
                    if limit is None:
                        return handle.read()
                    return handle.read(limit)
            except OSError as exc:
                raise SampleError(
                    f"{ref.path}: {exc.strerror or exc}") from exc
        size = ref.size
        try:
            with ref.archive.open("rb") as handle:
                handle.seek(ref.offset)
                return handle.read(size if limit is None
                                   else min(size, limit))
        except OSError as exc:
            raise SampleError(f"{ref.archive}: {exc.strerror or exc}") from exc

    @staticmethod
    def _located(ref: SampleRef, exc: SampleError) -> SampleError:
        """Prefix a decode error with the location it came from."""
        if ref.path is not None:
            return SampleError(f"{ref.path}: {exc}")
        return SampleError(f"{ref.display_name}: {exc}")
