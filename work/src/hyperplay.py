"""Play a Rave eJay hyper preset on the speakers.

    python src/hyperplay.py --list              # list the 20 presets
    python src/hyperplay.py 3                   # play preset 3 (Kick Away)
    python src/hyperplay.py "Snare Break"       # play by name
    python src/hyperplay.py 10 --sink waveout   # Windows waveOut backend

Reads the preset table (HYPRESET) and the sound bank (HYPSOUND), decodes the
preset's base sound (field D), and plays the 16-step sequencer pattern (field B,
one slot per 16th of a bar) by triggering the base sound at each active step.
Output goes through sounddevice's RawOutputStream or a Windows waveout sink.

The hyper sound .pxd files ship under disk/RAVE/HYPER/ (or EJAY/MAX/hyper/ /
EJAY/MIN/hyper/ of a full install).  Pass --res to point at an install that has
them, or --sound-dir to point directly at the hyper/ folder.
"""

from __future__ import annotations

import array
import argparse
import os
import sys
import tempfile
import time

import pxd32d5
import pxdsink

SAMPLE_RATE = 44100
BYTES_PER_FRAME = 4  # 16 bit stereo, the ring format
END_TIMEOUT_EXTRA = 5.0
TAIL_DRAIN = 0.3

PRESET_PATH = os.path.join("disk", "RAVE", "EJAY", "HYPRESET")
SOUND_PATH = os.path.join("disk", "RAVE", "EJAY", "HYPSOUND")

# one bar at 44.1 kHz (from tPxd comment field), 16 steps per bar
BAR_FRAMES = 58800
STEP_FRAMES = BAR_FRAMES // 16

# candidate locations for the hyper sound .pxd files of a full install
# (disk\RAVE\HYPER\ is checked directly in find_sound_file)
HYPER_DIRS = [
    os.path.join("MAX", "hyper"),   # disk\RAVE\EJAY\MAX\hyper\r1hgNNNN.pxd
    os.path.join("MIN", "hyper"),   # disk\RAVE\EJAY\MIN\hyper\r1hgNNNN.pxd
    os.path.join("hyper"),
]

__all__ = [
    "Preset",
    "SoundEntry",
    "read_presets",
    "read_sounds",
    "find_sound_file",
    "build_parser",
    "list_presets",
    "list_devices",
    "main",
]


# 18-key keyboard from EJAY\KONST / EJAY\HKONST:
# G Ab A Bb B C1 Db1 D1 Eb1 E1 F1 Gb1 G1 Ab1 A1 Bb1 B1 C2
# H = B in German notation; H_G2 = G1 (octave below C1).
NOTE_NAMES = [
    "G", "Ab", "A", "Bb", "B",   # H_G H_AS H_A H_B H_H
    "C1", "Db1", "D1", "Eb1", "E1", "F1", "Gb1", "G1", "Ab1", "A1", "Bb1", "B1",
    "C2",                                          # H_C … H_C2
]


class Preset:
    """One HYPRESET record: name plus the A/B/C/D data line."""

    def __init__(self, name: str, data: str):
        self.name = name
        self.data = data
        parts = data.split()
        if len(parts) < 4:
            raise ValueError("bad preset data line: %r" % data)
        self.a = parts[0]   # 30 chars: 15 two-digit numbers
        self.b = parts[1]   # 32 chars: 16 two-digit numbers (16-step matrix)
        self.c = parts[2]   # 5 chars: binary switches
        self.d = parts[3]   # 5 chars: sound id, zero-padded
        self.sound_id = int(self.d)

    def step_values(self) -> list[int]:
        """Return the 16 B-field slot values (0 = rest)."""
        return [int(self.b[i * 2:i * 2 + 2]) for i in range(16)]

    def step_notes(self) -> list[str]:
        """Return the note name for each B slot (``"-"`` for rest)."""
        notes = []
        for v in self.step_values():
            if v == 0:
                notes.append("-")
            elif 1 <= v <= len(NOTE_NAMES):
                notes.append(NOTE_NAMES[v - 1])
            else:
                notes.append("?(%d)" % v)
        return notes


class SoundEntry:
    """One HYPSOUND record: filename, label, numeric id."""

    def __init__(self, filename: str, label: str):
        self.filename = filename
        self.label = label
        digits = "".join(ch for ch in label.split()[0] if ch.isdigit())
        self.id = int(digits) if digits else 0
        self.display = " ".join(label.split()[1:]) if digits else label


def read_presets(path: str = PRESET_PATH) -> list[Preset]:
    """Read HYPRESET: 20 records of (name, data line)."""
    with open(path, "r", encoding="latin-1") as fh:
        lines = fh.read().split("\n")
    # drop a possible trailing empty line
    while lines and lines[-1] == "":
        lines.pop()
    presets = []
    for i in range(0, len(lines), 2):
        name = lines[i].strip()
        data = lines[i + 1]
        presets.append(Preset(name, data))
    return presets


def read_sounds(path: str = SOUND_PATH) -> dict[int, SoundEntry]:
    """Read HYPSOUND: id -> SoundEntry across all groups."""
    with open(path, "r", encoding="latin-1") as fh:
        lines = fh.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    sounds: dict[int, SoundEntry] = {}
    i = 0
    while i < len(lines):
        # line i: group name, line i+1: count
        count = int(lines[i + 1].strip())
        i += 2
        for _ in range(count):
            filename = lines[i].strip()
            label = lines[i + 1].strip()
            entry = SoundEntry(filename, label)
            sounds[entry.id] = entry
            i += 2
    return sounds


def find_sound_file(sound_id: int, res_root: str = "disk/RAVE",
                    sound_dir: str | None = None) -> str | None:
    """Locate ``r1hgNNNN.pxd`` for ``sound_id`` under the install root."""
    filename = "r1hg%04d.pxd" % sound_id
    if sound_dir:
        path = os.path.join(sound_dir, filename)
        if os.path.isfile(path):
            return path
    # disk\RAVE\HYPER\r1hgNNNN.pxd (where the shipped copy has them)
    path = os.path.join(res_root, "HYPER", filename)
    if os.path.isfile(path):
        return path
    for sub in HYPER_DIRS:
        path = os.path.join(res_root, "EJAY", sub, filename)
        if os.path.isfile(path):
            return path
    # last resort: plain search next to disk/RAVE/EJAY
    path = os.path.join(res_root, "EJAY", filename)
    if os.path.isfile(path):
        return path
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hyperplay",
        description="List and play Rave eJay hyper generator presets.")
    p.add_argument("selection", nargs="?", metavar="PRESET",
                   help="preset number (1-20) or name to play; omit to list")
    p.add_argument("-r", "--res", default="disk/RAVE", metavar="DIR",
                   help="eJay install root holding disk/RAVE (default: disk/RAVE)")
    p.add_argument("--sound-dir", default=None, metavar="DIR",
                   help="folder holding r1hgNNNN.pxd hyper sound files")
    p.add_argument("-l", "--list", action="store_true",
                   help="list presets and exit (same as no selection)")
    p.add_argument("--list-devices", action="store_true",
                   help="list sounddevice output devices and exit")
    p.add_argument("-s", "--sink", choices=("sounddevice", "waveout"),
                   default="sounddevice",
                   help="audio backend (default: sounddevice)")
    p.add_argument("-d", "--device", default=None, metavar="DEV",
                   help="output device for sounddevice (index or name "
                        "substring)")
    p.add_argument("-g", "--gain", type=float, default=1.0, metavar="F",
                   help="engine gain passed to PInit (default: 1.0)")
    p.add_argument("--base-note", type=int, default=6, metavar="N",
                   help="base note index (1-18) played at the sample's "
                        "natural pitch; default 6 = C1")
    p.add_argument("--transpose", type=int, default=0, metavar="N",
                   help="transpose all notes by N semitones (default: 0)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="only report errors")
    p.add_argument("--loops", type=int, default=1, metavar="N",
                   help="repeat the 16-step pattern N times (default: 1)")
    return p


def list_devices() -> int:
    """List sounddevice output devices and exit."""
    try:
        import sounddevice
    except ImportError as exc:
        print("hyperplay: %s" % exc, file=sys.stderr)
        return 1
    try:
        print(sounddevice.query_devices())
    except sounddevice.PortAudioError as exc:
        print("hyperplay: %s" % exc, file=sys.stderr)
        return 1
    return 0


def list_presets(presets: list[Preset], sounds: dict[int, SoundEntry],
                 res_root: str, sound_dir: str | None, quiet: bool) -> int:
    """Print the 20 presets with sound resolution status."""
    width = max(len(p.name) for p in presets)
    for idx, preset in enumerate(presets, 1):
        entry = sounds.get(preset.sound_id)
        if entry:
            path = find_sound_file(preset.sound_id, res_root, sound_dir)
            status = "ready" if path else "missing .pxd"
            notes = " ".join(preset.step_notes())
            line = ("  %2d  %-*.*s  id=%04d  %-28s  %-12s  %s  %s"
                    % (idx, width, width, preset.name, preset.sound_id,
                       entry.label, entry.filename, status, notes))
        else:
            line = ("  %2d  %-*.*s  id=%04d  (no sound bank entry)  %s"
                    % (idx, width, width, preset.name, preset.sound_id,
                       " ".join(preset.step_notes())))
        if quiet and "missing" not in line and "no sound bank" not in line:
            continue
        print(line)
    missing = sum(1 for p in presets
                  if not find_sound_file(p.sound_id, res_root, sound_dir)
                  and p.sound_id in sounds)
    if missing and not quiet:
        print("hyperplay: %d preset(s) have no resolvable .pxd file"
              % missing, file=sys.stderr)
    return 0


def _resample_pitch(samples: array.array, semitones: int) -> array.array:
    """Resample stereo int16 ``samples`` by ``semitones`` (positive = higher).

    Linear-interpolation resampling.  ``semitones`` = 0 returns ``samples``
    unchanged; each semitone multiplies the playback rate by 2**(1/12).
    """
    if semitones == 0:
        return samples
    ratio = 2.0 ** (semitones / 12.0)
    in_frames = len(samples) // 2
    out_frames = int(in_frames / ratio) + 1
    out = array.array("h", bytes(2 * 2 * out_frames))
    for f in range(out_frames):
        pos = f * ratio
        f0 = int(pos)
        f1 = min(f0 + 1, in_frames - 1)
        frac = pos - f0
        for ch in range(2):
            s0 = samples[f0 * 2 + ch]
            s1 = samples[f1 * 2 + ch]
            out[f * 2 + ch] = int(s0 + (s1 - s0) * frac)
    return out


def _decode_stereo(src: str) -> array.array:
    """Decode ``src`` to stereo int16 at 44.1 kHz via RWavToTemp."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        pxd32d5.PInit(1.0)
        pxd32d5.engine.output_kind = 4      # write a 44-byte RIFF header
        rc = pxd32d5.RWavToTemp(src, tmp.name, 0, None, 0, 0, 0)
        pxd32d5.PClose()
        if rc != 0:
            raise RuntimeError("RWavToTemp failed (rc=%d)" % rc)
        with open(tmp.name, "rb") as fh:
            wav = fh.read()
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
    if len(wav) < 44 or wav[0:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise RuntimeError("decoded output is not a RIFF/WAVE stream")
    pcm = array.array("h")
    pcm.frombytes(wav[44:])
    # interleave left/right from the engine's mono-left-duplicated output
    if len(pcm) % 2:
        pcm = pcm[:-1]
    return pcm


def _mix_into(mix: array.array, src: array.array, start_frame: int) -> None:
    """Add stereo int16 ``src`` into ``mix`` at ``start_frame`` with saturation."""
    frame = start_frame * 2            # two samples per stereo frame
    end = min(frame + len(src), len(mix))
    n = end - frame
    if n <= 0:
        return
    for i in range(n):
        total = mix[frame + i] + src[i]
        if total > 32767:
            total = 32767
        elif total < -32768:
            total = -32768
        mix[frame + i] = total


def _build_preset_pcm(preset: Preset, entry: SoundEntry,
                      res_root: str, sound_dir: str | None,
                      base_note: int, transpose: int) -> bytes:
    """Render one bar of the 16-step sequencer pattern.

    Each active step triggers the base sound resampled to its note pitch
    (note value minus ``base_note``, plus ``transpose`` semitones).
    """
    src = find_sound_file(preset.sound_id, res_root, sound_dir)
    if src is None:
        raise RuntimeError("no .pxd file for sound %04d" % preset.sound_id)

    base = _decode_stereo(src)          # stereo int16 array
    if len(base) == 0:
        raise RuntimeError("decoded empty sound for %s" % src)

    mix = array.array("h", bytes(2 * 2 * BAR_FRAMES))  # stereo silence
    steps = preset.step_values()
    for step, value in enumerate(steps):
        if value == 0:
            continue
        semitones = value - base_note + transpose
        pitched = _resample_pitch(base, semitones)
        _mix_into(mix, pitched, step * STEP_FRAMES)
    return mix.tobytes()


def _play_sounddevice(args: argparse.Namespace, preset: Preset,
                      entry: SoundEntry, pcm: bytes, src_path: str) -> int:
    """Play ``pcm`` (stereo int16) through sounddevice's RawOutputStream."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        print("hyperplay: sounddevice needed for this sink: %s" % exc,
              file=sys.stderr)
        return 1

    device = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    try:
        stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE, channels=2, dtype="int16",
            blocksize=2048, device=device)
        stream.start()
    except sd.PortAudioError as exc:
        print("hyperplay: cannot open the output device: %s" % exc,
              file=sys.stderr)
        return 1

    if not args.quiet:
        frames = len(pcm) // 4
        seconds = frames / float(SAMPLE_RATE)
        notes = " ".join(preset.step_notes())
        print("%s  preset '%s'  sound %04d '%s'  %d frames  %.2f s  "
              "base-note=%d transpose=%d  steps: %s  via sounddevice"
              % (src_path, preset.name, preset.sound_id,
                 entry.label, frames, seconds, args.base_note,
                 args.transpose, notes))

    try:
        block_frames = 2048
        total_frames = len(pcm) // 4
        for start_frame in range(0, total_frames, block_frames):
            end_frame = min(start_frame + block_frames, total_frames)
            stream.write(pcm[start_frame * 4:end_frame * 4])
    except KeyboardInterrupt:
        if not args.quiet:
            print("hyperplay: interrupted", file=sys.stderr)
        return 130
    finally:
        stream.stop()
        stream.close()

    if not args.quiet:
        print("done")
    return 0


def _play_waveout(args: argparse.Namespace, presets: list[Preset],
                  preset: Preset, entry: SoundEntry, pcm: bytes) -> int:
    """Play ``pcm`` (stereo int16) through the engine's WaveOut sink."""
    try:
        sink = pxdsink.WaveOutSink()
    except OSError as exc:
        print("hyperplay: cannot open waveout sink: %s" % exc,
              file=sys.stderr)
        return 1

    # write the rendered bar to a temp WAV and play it via the engine
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        import struct
        with open(tmp_path, "wb") as fh:
            fh.write(b"RIFF")
            fh.write(struct.pack("<I", 36 + len(pcm)))
            fh.write(b"WAVEfmt ")
            fh.write(struct.pack("<IHHIIHH", 16, 1, 2, SAMPLE_RATE,
                                 SAMPLE_RATE * 4, 4, 16))
            fh.write(b"data")
            fh.write(struct.pack("<I", len(pcm)))
            fh.write(pcm)

        pxd32d5.PInit(args.gain)
        engine = pxd32d5.engine
        engine.sink = sink
        try:
            pxd32d5.PStart()
            start = engine.play_position()
            length = pxd32d5.awave_dauer(tmp_path)
            if length <= 0:
                print("hyperplay: %s: not a decodable stream" % tmp_path,
                      file=sys.stderr)
                return 1
            frames = length // BYTES_PER_FRAME
            seconds = frames / float(SAMPLE_RATE)
            pxd32d5.PPlay(tmp_path, 0, start, 0, start + length, 0)
            if not args.quiet:
                print("%s  preset %d '%s'  sound %04d '%s'  %d frames  %.2f s  "
                      "via waveout"
                      % (tmp_path, presets.index(preset) + 1, preset.name,
                         preset.sound_id, entry.label, frames, seconds))
            deadline = time.monotonic() + seconds + END_TIMEOUT_EXTRA
            while not engine.word_10083528 and time.monotonic() < deadline:
                time.sleep(0.02)
            if not engine.word_10083528:
                print("hyperplay: playback did not finish (timeout)",
                      file=sys.stderr)
                return 1
            time.sleep(TAIL_DRAIN)
        except KeyboardInterrupt:
            if not args.quiet:
                print("hyperplay: interrupted", file=sys.stderr)
            return 130
        finally:
            pxd32d5.PClose()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    if not args.quiet:
        print("done")
    return 0


def play(args: argparse.Namespace) -> int:
    presets = read_presets(os.path.join(args.res, "EJAY", "HYPRESET"))
    sounds = read_sounds(os.path.join(args.res, "EJAY", "HYPSOUND"))

    if args.list or args.selection is None:
        return list_presets(presets, sounds, args.res, args.sound_dir,
                            args.quiet)

    # resolve the selection: number or name
    preset = None
    try:
        num = int(args.selection)
        if 1 <= num <= len(presets):
            preset = presets[num - 1]
    except ValueError:
        pass
    if preset is None:
        for p in presets:
            if p.name.lower() == args.selection.lower():
                preset = p
                break
    if preset is None:
        print("hyperplay: unknown preset '%s' (use --list)" % args.selection,
              file=sys.stderr)
        return 1

    entry = sounds.get(preset.sound_id)
    if entry is None:
        print("hyperplay: preset '%s' references sound id %04d, not in bank"
              % (preset.name, preset.sound_id), file=sys.stderr)
        return 1

    src = find_sound_file(preset.sound_id, args.res, args.sound_dir)
    if src is None:
        print("hyperplay: preset '%s' sound %04d (%s): no .pxd file found"
              % (preset.name, preset.sound_id, entry.filename),
              file=sys.stderr)
        print("hyperplay: hyper sounds live under disk/RAVE/HYPER/ or "
              "EJAY/MAX/hyper/; pass --res or --sound-dir", file=sys.stderr)
        return 1

    # render the full 16-step pattern into one bar of stereo PCM
    try:
        pcm = _build_preset_pcm(preset, entry, args.res, args.sound_dir,
                                args.base_note, args.transpose)
    except RuntimeError as exc:
        print("hyperplay: %s" % exc, file=sys.stderr)
        return 1

    # repeat the bar for --loops iterations
    if args.loops > 1:
        pcm = pcm * args.loops

    steps_on = sum(1 for v in preset.step_values() if v != 0)
    notes = " ".join(preset.step_notes())
    if not args.quiet:
        frames = len(pcm) // 4
        seconds = frames / float(SAMPLE_RATE)
        print("preset %d '%s'  sound %04d '%s'  %d active step(s)  %.2f s  "
              "loops=%d base-note=%d transpose=%d  steps: %s"
              % (presets.index(preset) + 1, preset.name, preset.sound_id,
                 entry.label, steps_on, seconds, args.loops, args.base_note,
                 args.transpose, notes))

    if args.sink == "waveout":
        return _play_waveout(args, presets, preset, entry, pcm)
    return _play_sounddevice(args, preset, entry, pcm, src)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_devices:
        return list_devices()
    return play(args)


if __name__ == "__main__":
    sys.exit(main())
