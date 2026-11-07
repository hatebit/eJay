"""Blocking PortAudio output through an optional ``sounddevice`` import."""

from __future__ import annotations

import array

from .binary import pcm_bytes
from .constants import DEFAULT_BLOCK_FRAMES, SAMPLE_RATE
from .playback_error import PlaybackError


class AudioOutput:
    """A lazily opened ``sounddevice.RawOutputStream``.

    ``sounddevice`` is imported on the first :meth:`open` or :meth:`write`, so
    importing the package and using ``--list`` never require the dependency.

    Attributes:
        device: Device index, name substring, or None for the default.
        block_frames: PortAudio block size.
        channels: 1 for mono, 2 for stereo.
        sample_rate: Output rate.
    """

    def __init__(self, device=None, block_frames: int = DEFAULT_BLOCK_FRAMES,
                 channels: int = 2, sample_rate: int = SAMPLE_RATE) -> None:
        self.device = device
        self.block_frames = block_frames
        self.channels = channels
        self.sample_rate = sample_rate
        self._stream = None
        self._paused = False

    def open(self) -> None:
        """Open and start the stream.

        Raises:
            PlaybackError: ``sounddevice`` is missing or PortAudio fails.
        """
        if self._stream is not None:
            return
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise PlaybackError(
                "playback needs the 'sounddevice' package "
                "('pip install sounddevice')") from exc

        device = self.device
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        try:
            stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=self.block_frames,
                device=device,
            )
            stream.start()
        except sd.PortAudioError as exc:
            raise PlaybackError(
                f"cannot open the output device: {exc}") from exc
        self._stream = stream
        self._paused = False

    def write(self, samples: array.array) -> None:
        """Write one block of int16 samples.

        Args:
            samples: Mono or interleaved stereo values.

        Raises:
            PlaybackError: The stream cannot be opened or written.
        """
        self.open()
        try:
            self._stream.write(pcm_bytes(samples))
        except Exception as exc:  # PortAudio raises several unrelated types.
            raise PlaybackError(f"output write failed: {exc}") from exc

    def pause(self) -> None:
        """Stop the stream without closing it.

        Raises:
            PlaybackError: The stream has not been opened or cannot stop.
        """
        stream = self._stream
        if stream is None:
            raise PlaybackError("cannot pause: the output is not open")
        try:
            stream.stop()
        except Exception as exc:  # PortAudio raises several unrelated types.
            raise PlaybackError(f"cannot pause the output: {exc}") from exc
        self._paused = True

    def resume(self) -> None:
        """Restart a stream stopped by :meth:`pause`.

        Raises:
            PlaybackError: The stream has not been opened or cannot start.
        """
        stream = self._stream
        if stream is None:
            raise PlaybackError("cannot resume: the output is not open")
        try:
            stream.start()
        except Exception as exc:  # PortAudio raises several unrelated types.
            raise PlaybackError(f"cannot resume the output: {exc}") from exc
        self._paused = False

    def close(self) -> None:
        """Stop and close the stream, if it was opened."""
        stream, self._stream = self._stream, None
        paused, self._paused = self._paused, False
        if stream is None:
            return
        try:
            if not paused:
                stream.stop()
        finally:
            stream.close()

    def __enter__(self) -> "AudioOutput":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
