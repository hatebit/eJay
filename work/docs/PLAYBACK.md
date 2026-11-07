# Playback — from `PPlay` to sound

This page describes the playback path of the port: how a play request becomes
PCM on a device, which parts of the DLL it reproduces, and what is still
missing. The implementation lives in `Engine` (`src/pxd32d5.py`) and the
output backends in `src/pxdsink.py`.

Everything below comes from targeted disassembly of `pxd32d5_d4.dll` (a local
copy; the binary is not checked in) with `tools/pxd_dis.py`; addresses are the
dump's
`//----- (ADDR)` labels. Items that still need confirmation are marked
**(unverified)**.

## 1. What the DLL does

```
PInit ─ ADevice (waveOut probe only) ─ AInit ─ sub_100178D4:
        critical sections + mixerOpen + CreateThread(StartAddress)
PStart ─ AStart(176223600) ─ dword_10096D88 = 2, dword_100829F0 = arg
                                        │
StartAddress (0x10017AB4) ◄─────────────┘   loop every ~6 ms:
  sub_10017255  choose a queued slot (sub_10015B6C), refill it
                (sub_10014D10), decode into the ring (sub_10016237)
  RTimer ─► sub_10015666  mix tick (only while word_10096E04 != 0)
               sub_10016FD5  zero the ring ahead of the write front
               sub_10015907  pick the voice to decode, set its window
               sub_10016C77  + sub_10016325: duplicate left → right
               sub_10016E89  bookkeeping
  DPlayUpdate ─► sub_1001D74E ─► sub_1001B464
               IDirectSoundBuffer::Lock / memcpy / Unlock
  dword_10096D88 == 1 ─► sub_10014589  full reset
  dword_10096D88 == 2 ─► sub_10017632  start (word_10096E04 = 1)
```

There is **no `waveOutWrite` in the DLL**. `waveOutOpen` is used only to probe
a device in `ADevice`; output is a DirectSound buffer created by `DStart`
(0x1001ACDA) through `CoCreateInstance`, with one `IDirectSoundBuffer` per
stream slot. `mixerOpen` only drives the volume control.

The mix destination is the ring `dword_1008E410`, allocated by
`sub_1001186B` as `GlobalAlloc(dword_1004B314 + 512) + 44`. `dword_1004B314`
is 907 200 bytes (set in `sub_10010D83`), i.e. 226 800 stereo frames or
≈5.14 s at 44.1 kHz / 16 bit. `sub_1001C7AC` hands that buffer to DirectSound
(`DStart`, `sub_1001BAE5`), and `sub_1001D74E` keeps it fed with
`sub_1001B464` (Lock/copy/Unlock). `sub_1001BF40` reads the play position
back from `GetCurrentPosition`.

Two entry points reach it:

* `PPlay` → `APlay` → the per-voice queue → the drain. `PPlay` always takes
  the file branch (`source == 99`), because `PPlay` passes
  `a6 = &unk_1004B304` and that word is 99 (`.data` at `0x1004B304`).
* `RWaveLaden` (0x1001A152) → `RWavToTemp` → map the temp file → reset the
  mix state → `sub_1001CA3B(4)`. This is the host's whole-file path (the
  `PXD2Wav` player), not `PPlay`.

### The play request is a ring position, not a duration

`sub_10015B6C` copies three dwords straight into the voice block:

| slot | `APlay` arg | copied to | meaning |
|---|---|---|---|
| +0 | `a9` | `dword[14]` | ring **start position** (bytes) |
| +4 | `a10 + a9` | `dword[15]` | start time, or `1763823600` (sentinel) |
| +8 | `a11` | `dword[16]` | ring **end position** (bytes) |

The decode loop is `while (dword[14] < dword[16])`, so a request queued while
playback is running must carry the position the mixer is at
(`Engine.play_position()`), not `0`. `PPlay`'s `a3` is that position and `a5`
the end. This corrects the earlier "flags / start time / duration" reading in
§3.2 of [`PXD32D5-D4-engine.md`](../pxd/PXD32D5-D4-engine.md).

### Voice control block

`dword_10095108[33 * v]` is used in full, not just the slot ring:

| dword | use |
|---|---|
| `[3]` | read position in the sample buffer |
| `[4]` | base of the sample buffer |
| `[7]` | file offset |
| `[8]` | bytes queued |
| `[9]` | stream length |
| `[10]` | format flags (1 = `tP`, 0 = RIFF, >1 = other) |
| `[11]`–`[13]` | decode window: bytes, request, produced |
| `[14]` | play position in the ring |
| `[15]` | start time of the slot |
| `[16]` | end position in the ring |
| `[17]` | extra (loop/limit) |
| `[19..23]` | source pointer / handle / file position |
| `[25]` | slot ring pointer |
| `[26]` | low word = read cursor, high word = write cursor |
| `[31]` | saved volume (16.16) |
| `[32]` | ring size |

Word fields: `word[48]` state (−2 new, −1 streaming, 0 idle), `word[52]` /
`word[53]` cursors, `word[54]` marker (matched against slot +16).

## 2. What the port implements

| DLL piece | port |
|---|---|
| `PStart` / `AStart` | `PStart`, `Engine.AStart` |
| `StartAddress` (0x10017AB4) | `Engine._player_loop` (thread) and `Engine.pump` |
| `sub_100144C9` | `Engine._wait_play_command` (real wait, 2 s cap) |
| `sub_10017632` | `Engine.sub_10017632` |
| `sub_10014589` | `Engine.sub_10014589` |
| `sub_10015B6C` (file branch) | `Engine._drain` / `_open_slot` |
| `sub_10016237` + decoder wrappers | `Engine._decode_block` with a per-voice `Session` |
| `sub_10016FD5` | `Engine._zero_ahead` |
| `sub_10015907` | `Engine._mix_voices` |
| `sub_10016C77` + `sub_10016325` | `Engine._stereo_ready` / `_duplicate` |
| `sub_10015666` (tick) | `Engine._mix_tick` |
| `DPlayUpdate` / `sub_1001B464` | `Engine._feed_sink` |
| `DStart` / `sub_1001BAE5` / `sub_1001B0FF` / `sub_1001BD99` | `pxdsink.OutputSink` implementations |
| `RWavePause1` / `RWavePause2` / `RWaveStop` | same names on `Engine` and as module wrappers |
| `RWaveLaden` | conversion + `laden_wave`; device hand-off not ported |

### Output sinks (`src/pxdsink.py`)

The DirectSound COM layer is replaced by an `OutputSink` abstraction:

* `FileSink(path)` — writes the mixed PCM. Deterministic, used by the tests.
* `WaveOutSink(buffers, frames)` — a `waveOut` ring built on `ctypes`
  (standard library; it never loads `pxd32d5_d4.dll`). Eight buffers of 4410
  frames by default, `WAVE_FORMAT_PCM` 44.1 kHz / 16 bit / stereo. `write`
  blocks until the driver releases a buffer, so the engine's ring cannot run
  away; pause/resume/stop/close map to `waveOutReset`/`waveOutClose`.
* `SoundDeviceSink(device, blocksize, latency)` — the same ring on top of the
  optional `sounddevice` package (python-sounddevice / PortAudio, prebuilt
  binaries), so playback is not Windows-only. It drives a blocking
  `RawOutputStream` (`int16`, no callback, so no NumPy is needed); `write`
  blocks until PortAudio consumes the whole frames, giving the same
  backpressure as `WaveOutSink`, and `stop` aborts the stream while `resume`
  re-arms it. The package is imported lazily, so the module and the suite stay
  standard-library only when it is absent:
  `engine.sink = pxdsink.SoundDeviceSink(device="Speakers")`.
* Any other `OutputSink` subclass can be assigned to `Engine.sink`.

`Engine.AStart` opens the default sink lazily; if the device cannot be opened
the status bit `0x02` is set and playback still advances the ring silently,
mirroring the DLL's "no device" behaviour.

```python
import sys; sys.path.insert(0, "src")
import pxd32d5

pxd32d5.PInit(1.0)
pxd32d5.PStart()                       # starts the player thread + waveOut
pos = pxd32d5.engine.play_position()   # ring start position, in bytes
pxd32d5.PPlay("data/bo-test.pxd", 0, pos, 0, pos + 470400, 0)  # fixture not checked in
# ...
pxd32d5.PClose()
```

The fifth argument is the ring **end** position, not a duration.  For offline
work pass a `pxdsink.FileSink` as `engine.sink` and set
`engine.autostart_thread = False`, then drive `engine.pump()` / `wait_for_end()`.

`src/pxdplay.py` is that sequence as a demo: `python src/pxdplay.py FILE`
plays a `.pxd` (or RIFF/WAVE) on the speakers with `SoundDeviceSink`
(`--sink waveout` picks the stdlib backend, `--list-devices` lists outputs,
`--device` selects one).

### Behaviour and deviations

* The DLL's thread is created in `AInit`; the port starts it on the first
  `AStart` so an engine that never plays owns no thread and no device.
* `Engine.pump()` runs one command + one mix tick synchronously; the tests set
  `autostart_thread = False` and use it instead of racing the thread.
* The ring position comparison is the DLL's; the "playback finished" latch is
  set when the front reaches the highest requested end position (the DLL waits
  for `dword_1008E630 = 705600`). Without a request it does not latch.
* The decoder's 64-frame entry overrun (`PLAY_OVERRUN`) is held inside the
  lookahead guard so it cannot be overwritten by the next zero-ahead pass.
* The right channel is produced by `sub_10016325`'s duplication, as in the
  DLL; the decoder still writes the left channel only.
* `_decode_pcm` now **adds** its samples into the destination instead of
  overwriting it. `RWavToTemp` zeroes each block first, so conversion is
  unchanged, but two PCM voices now mix correctly.
* **Port-only robustness:** the DLL has no code path that can raise, but a
  Python decoder exception (or a decoder that produces 0 bytes) used to leave
  the voice at `state = -1` for ever, and `_stereo_ready` takes the *minimum*
  over active voices — so one bad stream froze both mix fronts and every
  later request with them. Such a voice is now closed instead
  (`_finish_voice`), the tick that raised is caught in `_player_loop`, and the
  failures are kept in `Engine.playback_errors` ("file: reason");
  `Engine.last_error` holds the last exception out of a mix tick.
  `mixplay` prints those as `skipped ...` and, if the front stops moving for
  `STALL_SECONDS`, reports the position, event count and mixer error instead
  of waiting out the whole arrangement's timeout.
* Not ported: the memory-source branch of `sub_10015B6C`, the marker re-sync
  fast path, `sub_10016985`/`sub_1001F7A4` (module synth) and the DirectSound
  volume/mixer controls. `RWaveLaden`'s `sub_1001CA3B(4)` hand-off is not
  modelled, so it loads but does not start playback.

## 3. Tests

`src/test_pxd32d5.py` covers, with `FileSink`:

* `hyper-test.pxd` → exactly 14 700 stereo frames, left == right, equal to a
  unity-gain decode, range −6302…6294;
* a synthetic `tP` stream → `[0, 2, 2, 4, 8]` per channel (unity, not the
  converter's ×2);
* two voices of the same stream → `[0, 4, 4, 8, 16]` (additive mixing);
* pause → no further bytes until resume;
* the real player thread (`autostart_thread` on) → 58 800 bytes and a joined
  thread after `PClose`;
* re-queueing with `play_position()` → writes into the live part of the ring;
* the silent `waveOut` device path was exercised manually (no automated test
  needs a sound card); the sink also passes a silent open/write/pause/stop/
  close probe. The `sounddevice` sink was verified the same way — its
  open/write/pause/resume/stop/restart/close contract plus a real
  `hyper-test.pxd` play through the engine — so neither device backend has a
  suite entry.
* `src/pxdplay.py` is covered on its argument/validation paths (a missing
  file, an unrecognised stream, a missing `INPUT`); its playback path needs a
  device and is verified by hand as above.

## 4. Open questions

* `word_100823F8` modes other than 0/4 (mode 1 bypasses DirectSound).
  **(unverified)**
* What sets `dword_10096D52 = 1`, required for `DPlayUpdate` to feed the
  device. **(unverified)**
* `sub_10016985`'s module mixing and `sub_1001F7A4`'s tracker sequencer are
  understood only at call-site level.
* DirectSound vtable offsets (`+44` Lock, `+48` Play, `+52` SetCurrentPosition,
  `+60` SetVolume, `+68` SetFrequency, `+76` Unlock) are inferred from the
  call shapes. **(unverified)**
* `AStart`'s `176223600` (`44100 * 3996`) is treated as a play limit; its
  exact role in `sub_10016985` is not confirmed. **(unverified)**
* The `RWaveLaden` hand-off `sub_1001CA3B(4)`. **(unverified)**
