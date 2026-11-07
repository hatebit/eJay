"""A sample whose PCM is decoded while playback reaches it."""

from __future__ import annotations

import array
from typing import TYPE_CHECKING

from .sample_error import SampleError

if TYPE_CHECKING:
    from .pxd_stream_decoder import PxdStreamDecoder
    from .riff_stream_decoder import RiffStreamDecoder
    from .sample_decoder import SampleDecoder
    from .sample_ref import SampleRef

DECODE_CHUNK = 4096
"""Frames requested from a streaming decoder at a time."""


class SampleStream:
    """A mono int16 sample that decodes as playback reaches it.

    The declared frame count comes from the sample header, so an event builder
    can position a sample without decoding it.  While the mix plays, the
    mixer asks for block-sized windows and only the frames up to the end of
    the furthest window are decoded.

    Decoded frames are kept: the stream never moves its decoder backwards.
    One stream is shared by every event that plays the same sample id, and
    those events read it at unrelated positions (a loop that wraps, a repeated
    hit, the same loop on two tracks).  A window that lies behind the decoder
    is therefore a slice of the cache, and a window ahead of it extends the
    decode.  Once the whole sample has been decoded the decoder and its source
    bytes are released; the cache then costs two bytes per frame.

    A decode failure is recorded once and the stream then acts as silence, so
    the rest of the mix keeps playing.

    Attributes:
        sample_id: Numeric id used by the mix format.
        frames: Frame count the stream header declares.
    """

    def __init__(self, sample_id: int, frames: int, *,
                 ref: "SampleRef | None" = None,
                 decoder: "SampleDecoder | None" = None,
                 pcm: array.array | None = None,
                 errors: list[str] | None = None) -> None:
        """Create a stream from a reference or from decoded PCM.

        Args:
            sample_id: Numeric id used by the mix format.
            frames: Declared frame count; ignored when ``pcm`` is given.
            ref: Location to decode when playback reaches the sample.
            decoder: Shared decoder that opens ``ref``.
            pcm: PCM that is already decoded.
            errors: List that receives a message when decoding fails.
        """
        self.sample_id = sample_id
        self.frames = (len(pcm) if pcm is not None
                       else max(0, int(frames)))
        self._ref = ref
        self._decoder = decoder
        self._pcm = pcm
        self._errors = errors
        self._stream: "PxdStreamDecoder | RiffStreamDecoder | None" = None
        self._cache = array.array("h")
        self._eof = False
        self._failed = False

    @property
    def decoded(self) -> bool:
        """True once decoding has started or a failure was recorded."""
        return (self._pcm is not None or len(self._cache) > 0
                or self._failed)

    @property
    def decoded_frames(self) -> int:
        """Number of frames decoded so far."""
        if self._pcm is not None:
            return len(self._pcm)
        return len(self._cache)

    def window(self, start: int, count: int,
               loop: bool = False) -> array.array:
        """Return exactly ``count`` frames starting at absolute ``start``.

        Args:
            start: First frame, relative to the sample start.
            count: Number of frames to return.
            loop: Wrap back to frame zero when the sample ends.

        Returns:
            Mono int16 frames, padded with silence when the stream is short
            or has failed.
        """
        if count <= 0:
            return array.array("h")
        if self._pcm is not None:
            return self._cut(self._pcm, start, count, loop)
        if self.frames <= 0:
            return self._silence(count)

        if loop:
            start %= self.frames
        elif start >= self.frames:
            return self._silence(count)

        out = array.array("h")
        position = start
        remaining = count
        while remaining > 0:
            take = self.frames - position
            if not loop:
                take = min(take, remaining)
            take = min(take, remaining)
            if take <= 0:
                break
            out.extend(self._range(position, take))
            remaining -= take
            position = 0 if loop else position + take
        if len(out) < count:
            out.extend(self._silence(count - len(out)))
        return out

    def decode(self) -> array.array:
        """Return the whole PCM, decoding it in windows.

        Returns:
            Mono int16 frames, or an empty array when decoding failed.
        """
        if self._pcm is not None:
            return self._pcm
        out = array.array("h")
        position = 0
        while position < self.frames:
            count = min(DECODE_CHUNK, self.frames - position)
            out.extend(self.window(position, count))
            position += count
        return out

    def close(self) -> None:
        """Close the decoder handle and discard decoded frames."""
        self._release()
        self._cache = array.array("h")
        self._eof = False

    def __len__(self) -> int:
        return self.frames

    def __getitem__(self, index: int) -> int:
        if index < 0:
            index += self.frames
        if index < 0 or index >= self.frames:
            raise IndexError(index)
        return self.window(index, 1)[0]

    @staticmethod
    def _silence(count: int) -> array.array:
        """Return ``count`` zero frames."""
        return array.array("h", bytes(2 * count))

    @staticmethod
    def _cut(pcm: array.array, start: int, count: int,
             loop: bool) -> array.array:
        """Return a window from already-decoded PCM."""
        out = array.array("h")
        remaining = count
        position = start
        length = len(pcm)
        if length <= 0:
            return SampleStream._silence(count)
        if loop:
            position %= length
        while remaining > 0:
            take = length - position
            if not loop:
                take = min(take, remaining)
            take = min(take, remaining)
            if take <= 0:
                break
            out.extend(pcm[position:position + take])
            remaining -= take
            position = 0 if loop else position + take
        if len(out) < count:
            out.extend(SampleStream._silence(count - len(out)))
        return out

    def _range(self, start: int, count: int) -> array.array:
        """Return up to ``count`` decoded frames at ``start``."""
        if self._failed:
            return self._silence(count)
        self._fill(start + count)
        piece = self._cache[start:start + count]
        if len(piece) < count:
            piece.extend(self._silence(count - len(piece)))
        return piece

    def _fill(self, upto: int) -> None:
        """Decode until the cache reaches absolute frame ``upto``."""
        need = upto - len(self._cache)
        while need > 0 and not self._eof and not self._failed:
            try:
                stream = self._open_stream()
                if stream is None:
                    self._eof = True
                    break
                chunk = stream.read(min(need, DECODE_CHUNK))
            except SampleError as exc:
                self._fail(exc)
                break
            if not chunk:
                self._eof = True
                break
            self._cache.extend(chunk)
            need -= len(chunk)
        if len(self._cache) >= self.frames:
            self._eof = True
        if self._eof:
            self._release()

    def _open_stream(self) -> "PxdStreamDecoder | RiffStreamDecoder | None":
        """Open the streaming decoder on first use."""
        if self._stream is None:
            if self._ref is None or self._decoder is None:
                return None
            self._stream = self._decoder.open_stream(self._ref, self.frames)
        return self._stream

    def _release(self) -> None:
        """Close the decoder handle, keeping the decoded frames."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _fail(self, exc: SampleError) -> None:
        """Record a decode failure once and turn the stream into silence."""
        self._failed = True
        self._eof = True
        self.close()
        if self._errors is not None:
            message = str(exc)
            if message not in self._errors:
                self._errors.append(message)
