"""output sinks for the playback path.

The DLL writes its mix into a DirectSound buffer (``DStart`` +
``sub_1001B464``); there is no ``waveOutWrite`` anywhere in it.  A Python port
cannot use DirectSound without a COM dependency, so the playback engine talks
to an ``OutputSink`` instead and this module supplies three backends:

* ``FileSink``  - writes the PCM stream to a file.  Deterministic, used by the
  tests and useful for ``pxd2wav``-style offline playback.
* ``WaveOutSink`` - a small ``waveOut`` ring built on ``ctypes`` (standard
  library only, and it never loads ``pxd32d5_d4.dll``).  It reproduces what the
  DirectSound buffer did: queue buffers, report the position, pause/resume,
  stop and release.
* ``SoundDeviceSink`` - the same ring on top of the optional ``sounddevice``
  package (python-sounddevice / PortAudio), so playback is not limited to
  Windows.  Imported lazily: everything else here stays standard library only.

Every sink takes 44.1 kHz / 16 bit / stereo PCM, the format of the DLL's mix
ring (``word_10093ED4 = 16``, ``dword_10093ECA = 44100`` in ``DStart``).
"""

from __future__ import annotations

import os
import threading
import time

__all__ = ["OutputSink", "FileSink", "WaveOutSink", "SoundDeviceSink"]


class OutputSink:
    """Base class: the device side of the playback ring."""

    rate = 44100
    channels = 2
    bits = 16

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._position = 0          # bytes accepted by the device
        self._paused = False
        self._closed = False

    # -- API used by Engine ------------------------------------------------

    def write(self, data: bytes) -> int:
        """Queue ``data``; returns the number of bytes accepted."""
        raise NotImplementedError

    def position(self) -> int:
        """Bytes played so far (DirectSound ``GetCurrentPosition``)."""
        return self._position

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        """Discard queued audio but keep the device open."""
        self._paused = True

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


class FileSink(OutputSink):
    """Write the mixed PCM stream to ``path``."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self._fh = open(path, "wb")

    def write(self, data: bytes) -> int:
        with self._lock:
            if self._closed or self._paused:
                return 0
            self._fh.write(data)
            self._position += len(data)
            return len(data)

    def flush(self) -> None:
        with self._lock:
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._fh.flush()
            self._fh.close()


# ---------------------------------------------------------------------------
# sounddevice backend
# ---------------------------------------------------------------------------

class SoundDeviceSink(OutputSink):
    """A cross-platform device sink built on ``sounddevice``.

    ``sounddevice`` (python-sounddevice) wraps PortAudio and ships prebuilt
    binaries, so it is the portable alternative to ``WaveOutSink``.  It is an
    *optional* dependency: the import happens in ``__init__``, so this module
    and the test suite keep working without it.

    The device side is a blocking ``RawOutputStream`` (``int16``, no callback),
    which needs no NumPy.  ``write`` hands whole frames to PortAudio and blocks
    until they are consumed, giving the engine the same backpressure as
    ``WaveOutSink``: the mix ring cannot outrun the device.

    Assign it to ``Engine.sink``::

        import pxdsink
        engine.sink = pxdsink.SoundDeviceSink(device="Speakers")
    """

    def __init__(self, device=None, blocksize: int = 0,
                 latency=None) -> None:
        super().__init__()
        try:
            import sounddevice
        except ImportError as exc:                  # pragma: no cover
            raise ImportError(
                "SoundDeviceSink needs the optional 'sounddevice' package "
                "('pip install sounddevice')") from exc
        self._sd = sounddevice
        self._stream = None
        self._framesize = self.channels * (self.bits // 8)   # 16 bit stereo
        self._pending = b""         # partial frame carried into the next write
        try:
            self._stream = sounddevice.RawOutputStream(
                samplerate=self.rate, blocksize=blocksize,
                channels=self.channels, dtype="int16",
                device=device, latency=latency)
            self._stream.start()
        except sounddevice.PortAudioError as exc:
            raise OSError(str(exc)) from exc

    def write(self, data: bytes) -> int:
        """Queue ``data``, blocking until PortAudio has consumed it.

        PortAudio rejects a buffer that is not a whole number of frames, so a
        trailing partial frame is kept in ``_pending`` until the next call.
        ``stop``/``close`` abort the stream from another thread, which makes a
        blocked write return 0 instead of raising.
        """
        if self._closed or self._paused or not data:
            return 0
        with self._lock:
            stream = self._stream
            buf = self._pending + bytes(data)
            n = len(buf) - (len(buf) % self._framesize)
            self._pending = buf[n:]
        if stream is None or n == 0:
            return len(data)
        try:
            if stream.stopped:              # stopped by ``stop``/``abort``
                with self._lock:
                    if self._closed or self._paused:
                        return 0
                stream.start()
            stream.write(buf[:n])
        except self._sd.PortAudioError as exc:
            with self._lock:
                if self._closed or self._paused:
                    return len(data)        # deliberate abort, not a failure
            raise OSError(str(exc)) from exc
        with self._lock:
            self._position += n
        return len(data)

    def stop(self) -> None:
        """Discard queued audio; ``resume`` re-arms the stream."""
        self._paused = True
        with self._lock:
            self._pending = b""
            stream = self._stream
        if stream is not None:
            stream.abort()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._pending = b""
            stream = self._stream
            self._stream = None
        if stream is not None:
            stream.abort()
            stream.close()


# ---------------------------------------------------------------------------
# waveOut backend
# ---------------------------------------------------------------------------

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _winmm = ctypes.WinDLL("winmm", use_last_error=True)

    class _WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", wintypes.WORD),
            ("nChannels", wintypes.WORD),
            ("nSamplesPerSec", wintypes.DWORD),
            ("nAvgBytesPerSec", wintypes.DWORD),
            ("nBlockAlign", wintypes.WORD),
            ("wBitsPerSample", wintypes.WORD),
            ("cbSize", wintypes.WORD),
        ]

    class _WAVEHDR(ctypes.Structure):
        pass

    _WAVEHDR._fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.POINTER(_WAVEHDR)),
        ("reserved", ctypes.c_size_t),
    ]

    _WHDR_DONE = 0x00000001
    _WHDR_PREPARED = 0x00000002
    _WAVE_MAPPER = 0xFFFFFFFF

    _winmm.waveOutOpen.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.UINT,
        ctypes.POINTER(_WAVEFORMATEX), ctypes.c_size_t, ctypes.c_size_t,
        wintypes.DWORD,
    ]
    _winmm.waveOutOpen.restype = wintypes.UINT
    _winmm.waveOutPrepareHeader.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_WAVEHDR), wintypes.UINT]
    _winmm.waveOutPrepareHeader.restype = wintypes.UINT
    _winmm.waveOutUnprepareHeader.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_WAVEHDR), wintypes.UINT]
    _winmm.waveOutWrite.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_WAVEHDR), wintypes.UINT]
    _winmm.waveOutWrite.restype = wintypes.UINT
    _winmm.waveOutReset.argtypes = [wintypes.HANDLE]
    _winmm.waveOutReset.restype = wintypes.UINT
    _winmm.waveOutClose.argtypes = [wintypes.HANDLE]
    _winmm.waveOutClose.restype = wintypes.UINT

    class WaveOutSink(OutputSink):
        """A waveOut ring with ``buffers`` fixed-size buffers.

        ``write`` blocks until a buffer is free, so the engine's ring cannot
        grow past the device's queue.  ``position`` counts the bytes handed to
        the driver; it is the port's stand-in for
        ``IDirectSoundBuffer::GetCurrentPosition``.
        """

        def __init__(self, buffers: int = 8, frames: int = 4410) -> None:
            super().__init__()
            self._hwo = wintypes.HANDLE()
            self._bufsize = frames * 4          # 16 bit stereo
            self._count = buffers
            self._buffers = []
            self._headers = []
            self._free = list(range(buffers))
            self._busy = []
            self._opened = False
            self._open()

        def _open(self) -> None:
            fmt = _WAVEFORMATEX(1, self.channels, self.rate,
                                self.rate * 4, 4, self.bits, 0)
            rc = _winmm.waveOutOpen(ctypes.byref(self._hwo), _WAVE_MAPPER,
                                    ctypes.byref(fmt), 0, 0, 0)
            if rc != 0:
                raise OSError("waveOutOpen failed: %d" % rc)
            for _ in range(self._count):
                buf = ctypes.create_string_buffer(self._bufsize)
                hdr = _WAVEHDR()
                hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
                hdr.dwBufferLength = self._bufsize
                hdr.dwFlags = 0
                if _winmm.waveOutPrepareHeader(
                        self._hwo, ctypes.byref(hdr),
                        ctypes.sizeof(hdr)) != 0:
                    raise OSError("waveOutPrepareHeader failed")
                self._buffers.append(buf)
                self._headers.append(hdr)
            self._opened = True

        def _take_header(self) -> int:
            """Return an index of a buffer the driver is done with."""
            deadline = time.monotonic() + 5.0
            while True:
                with self._lock:
                    if self._closed:
                        raise OSError("sink closed")
                    if self._free:
                        return self._free.pop()
                    for k in list(self._busy):
                        if self._headers[k].dwFlags & _WHDR_DONE:
                            self._busy.remove(k)
                            return k
                if time.monotonic() > deadline:
                    raise OSError("waveOut buffers did not drain")
                time.sleep(0.002)

        def write(self, data: bytes) -> int:
            if self._closed or self._paused or not data:
                return 0
            view = memoryview(data)
            written = 0
            while view:
                if self._paused or self._closed:
                    break
                k = self._take_header()
                hdr = self._headers[k]
                n = min(len(view), self._bufsize)
                ctypes.memmove(hdr.lpData, bytes(view[:n]), n)
                hdr.dwBufferLength = n
                hdr.dwFlags &= ~_WHDR_DONE
                with self._lock:
                    rc = _winmm.waveOutWrite(self._hwo, ctypes.byref(hdr),
                                             ctypes.sizeof(hdr))
                    if rc == 0:
                        self._busy.append(k)
                        self._position += n
                if rc != 0:
                    raise OSError("waveOutWrite failed: %d" % rc)
                written += n
                view = view[n:]
            return written

        def stop(self) -> None:
            self._paused = True
            with self._lock:
                if self._opened:
                    _winmm.waveOutReset(self._hwo)

        def close(self) -> None:
            with self._lock:
                if self._closed:
                    return
                self._closed = True
                if not self._opened:
                    return
                _winmm.waveOutReset(self._hwo)
                for hdr in self._headers:
                    _winmm.waveOutUnprepareHeader(
                        self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr))
                _winmm.waveOutClose(self._hwo)
                self._opened = False

    __all__.append("WaveOutSink")

else:                                       # pragma: no cover - POSIX
    class WaveOutSink(OutputSink):
        """waveOut is Windows-only; every other platform gets an error."""

        def __init__(self, *args, **kwargs) -> None:
            raise OSError("waveOut playback is only available on Windows")

    __all__.append("WaveOutSink")
