from __future__ import annotations

import argparse
import array
import os
import struct
import sys

try:
    import mix_file
    import pxd_file
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mix_file
    import pxd_file

SAMPLE_RATE = mix_file.SAMPLE_RATE
DEFAULT_BPM = mix_file.DEFAULT_BPM
DEFAULT_BEATS = mix_file.DEFAULT_BEATS
BLOCK_FRAMES = 2048


class MixPlayError(ValueError):
    pass


def step_seconds(bpm: float = DEFAULT_BPM, beats: float = DEFAULT_BEATS) -> float:
    if bpm <= 0 or beats <= 0:
        raise MixPlayError("bpm and beats must be positive")
    return 60.0 * beats / bpm


def step_frames(bpm: float = DEFAULT_BPM, beats: float = DEFAULT_BEATS, sample_rate: int = SAMPLE_RATE) -> int:
    return int(round(step_seconds(bpm, beats) * sample_rate))


def find_index(mix_path: str):
    here = os.path.dirname(os.path.abspath(mix_path))
    candidates = [
        here,
        os.path.join(here, "disk", "RAVE"),
        os.path.join(os.path.dirname(here), "disk", "RAVE"),
        os.getcwd(),
        os.path.join(os.getcwd(), "disk", "RAVE"),
    ]
    for base in candidates:
        path = os.path.join(base, "EJAY", "PXD")
        if os.path.isfile(path):
            return path
    return None


def resolve_sample_path(sample_id: int, index, res_dir: str | None):
    ent = mix_file.sample_for(sample_id, index) if index is not None else None
    if ent is None:
        return None
    p = ent.path.replace("\\", "/")
    if res_dir:
        cand = os.path.normpath(os.path.join(res_dir, p))
        if os.path.isfile(cand):
            return cand
        cand2 = os.path.normpath(os.path.join(res_dir, os.path.basename(p)))
        if os.path.isfile(cand2):
            return cand2
    cand3 = os.path.normpath(p)
    if os.path.isfile(cand3):
        return cand3
    return None


def is_riff(data: bytes) -> bool:
    return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE"


def decode_riff_wav(data: bytes) -> array.array:
    if not is_riff(data):
        raise MixPlayError("not a RIFF/WAVE stream")
    pos = 12
    fmt = None
    wav_data = None
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if tag == b"fmt ":
            if size < 16:
                raise MixPlayError("fmt chunk too small")
            fmt = data[pos + 8:pos + 8 + size]
        elif tag == b"data":
            wav_data = data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
        if fmt is not None and wav_data is not None:
            break
    if fmt is None:
        raise MixPlayError("RIFF stream has no fmt chunk")
    if wav_data is None:
        raise MixPlayError("RIFF stream has no data chunk")
    audio_format, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if audio_format != 1:
        raise MixPlayError("compressed WAV (format %d) is not supported" % audio_format)
    if bits == 16 and channels == 1:
        out = array.array("h")
        raw = wav_data[:len(wav_data) - (len(wav_data) % 2)]
        out.frombytes(raw)
        if sys.byteorder == "big":
            out.byteswap()
        return out
    if bits == 16 and channels == 2:
        out = array.array("h")
        raw = wav_data[:len(wav_data) - (len(wav_data) % 4)]
        a = array.array("h")
        a.frombytes(raw)
        if sys.byteorder == "big":
            a.byteswap()
        out = array.array("h", a[0::2])
        return out
    raise MixPlayError("unsupported WAV format %d-bit %d-channel" % (bits, channels))


def decode_sample(path: str) -> array.array:
    with open(path, "rb") as fh:
        data = fh.read()
    if is_riff(data):
        return decode_riff_wav(data)
    if len(data) >= 4 and data[0:4] == pxd_file.PXD_MAGIC:
        f = pxd_file.PxdFile(path)
        return f.samples()
    raise MixPlayError("unknown sample format: %s" % path)


def event_frames(event, step_s: float, rate: int):
    start = int(round(event.run_start * step_s * rate))
    end = int(round(event.run_end * step_s * rate))
    if end <= start:
        end = start + int(round(rate * step_s))
    return start, end


class Mixer:
    def __init__(self, events, samples, step_s: float, gain: float = 1.0, rate: int = SAMPLE_RATE, on_start=None):
        self.rate = rate
        self.gain = float(gain)
        self.samples = samples
        self.on_start = on_start
        self.spans = []
        record_frames = int(round(step_s * rate))
        positions = []
        for event in events:
            pcm = samples.get(event.sample_id)
            if not pcm:
                continue
            start, end = event_frames(event, step_s, rate)
            positions.append((start, end, event, len(pcm)))
        positions.sort(key=lambda s: s[0])

        if positions:
            last_end = max(p[1] for p in positions)
            final_start = min(p[0] for p in positions if p[1] == last_end)
        else:
            last_end = 0
            final_start = 0

        total = 0
        for start, end, event, length in positions:
            loop = end - start > length and length >= record_frames
            if loop:
                audio_end = end
            else:
                natural = start + length
                if end >= last_end:
                    audio_end = natural
                else:
                    audio_end = min(natural, final_start)
            self.spans.append((start, audio_end, event, loop))
            if audio_end > total:
                total = audio_end
            if end > total:
                total = end
        self.total = total
        self._next = 0
        self._active = []

    def mix(self, start: int, count: int) -> array.array:
        out = array.array("h", bytes(2 * count))
        end = start + count
        while self._next < len(self.spans) and self.spans[self._next][0] < end:
            ev_start, ev_end, event, loop = self.spans[self._next]
            self._next += 1
            if ev_end <= start:
                continue
            self._active.append((ev_start, ev_end, event, loop))
            if self.on_start is not None:
                try:
                    self.on_start(event)
                except Exception:
                    pass

        alive = []
        gain = self.gain
        for ev_start, ev_end, event, loop in self._active:
            pcm = self.samples.get(event.sample_id)
            if not pcm:
                if ev_end > end:
                    alive.append((ev_start, ev_end, event, loop))
                continue
            length = len(pcm)
            limit = ev_end
            lo = ev_start if ev_start > start else start
            hi = end if end < limit else limit
            if hi > lo:
                dst = lo - start
                n = hi - lo
                for i in range(n):
                    if loop and length > 0:
                        s = (lo - ev_start + i) % length
                    else:
                        s = lo - ev_start + i
                    if s < 0 or s >= length:
                        break
                    if gain == 1.0:
                        v = pcm[s]
                    else:
                        v = int(pcm[s] * gain)
                        if v > 32767:
                            v = 32767
                        elif v < -32768:
                            v = -32768
                    totalv = out[dst + i] + v
                    if totalv > 32767:
                        totalv = 32767
                    elif totalv < -32768:
                        totalv = -32768
                    out[dst + i] = totalv
                else:
                    if limit > end:
                        alive.append((ev_start, ev_end, event, loop))
                    continue
                if limit > end:
                    alive.append((ev_start, ev_end, event, loop))
            elif limit > end:
                alive.append((ev_start, ev_end, event, loop))
        self._active = alive
        return out


def pcm_bytes(samples: array.array) -> bytes:
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mix_play", description="Play a Rave eJay .MIX arrangement")
    p.add_argument("input", nargs="?", metavar="MIX")
    p.add_argument("-r", "--res", default=None, metavar="DIR")
    p.add_argument("-i", "--index", default=None, metavar="FILE")
    p.add_argument("-b", "--bpm", type=float, default=DEFAULT_BPM)
    p.add_argument("--beats", type=float, default=DEFAULT_BEATS)
    p.add_argument("--step", type=float, default=None)
    p.add_argument("-l", "--list", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("-d", "--device", default=None)
    p.add_argument("--block", type=int, default=BLOCK_FRAMES)
    p.add_argument("-g", "--gain", type=float, default=1.0)
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input:
        build_parser().print_help()
        return 1
    mix_path = args.input
    try:
        mix = mix_file.MixFile(mix_path)
    except Exception as e:
        print("mix_play: %s" % e, file=sys.stderr)
        return 1

    idx_path = args.index or find_index(mix_path)
    idx = None
    if idx_path and os.path.isfile(idx_path):
        try:
            idx = mix_file.read_index(idx_path)
        except Exception as e:
            if args.strict:
                print("mix_play: %s" % e, file=sys.stderr)
                return 1

    res_dir = args.res
    if not res_dir and idx_path:
        res_dir = os.path.dirname(idx_path)

    if args.step is not None:
        step_s = float(args.step)
    else:
        step_s = step_seconds(args.bpm, args.beats)

    events = mix.events(index=idx, bpm=args.bpm, beats=args.beats)

    if args.list:
        rate = SAMPLE_RATE
        print("%s" % mix_path)
        print("  records %d used %d" % (len(mix.records()), mix.used_records()))
        print("  events %d" % len(events))
        for ev in events:
            t = ev.time_frames / float(rate)
            mm = int(t // 60)
            ss = t % 60
            p = resolve_sample_path(ev.sample_id, idx, res_dir)
            name = ev.sample_name or ""
            path_s = ev.sample_path or (p or "")
            print("    rec %3d  %d:%05.2f  T%d/%s  ID 0x%03X  %s  %s" % (ev.record, mm, ss, ev.track, ev.lane, ev.sample_id, path_s, name))
        return 0

    samples = {}
    for ev in events:
        if ev.sample_id in samples:
            continue
        p = resolve_sample_path(ev.sample_id, idx, res_dir)
        if not p or not os.path.isfile(p):
            if args.strict:
                print("mix_play: cannot resolve sample 0x%03X" % ev.sample_id, file=sys.stderr)
                return 1
            if not args.quiet:
                print("mix_play: skipping unresolvable sample 0x%03X" % ev.sample_id, file=sys.stderr)
            continue
        try:
            samples[ev.sample_id] = decode_sample(p)
        except Exception as e:
            if args.strict:
                print("mix_play: %s: %s" % (p, e), file=sys.stderr)
                return 1
            if not args.quiet:
                print("mix_play: %s: %s" % (p, e), file=sys.stderr)
            continue

    try:
        import sounddevice as sd
    except Exception as e:
        print("mix_play: sounddevice not installed: %s" % e, file=sys.stderr)
        return 1

    printed = set()

    def on_start(ev):
        key = (ev.record, ev.track, ev.lane, ev.sample_id)
        if key in printed:
            return
        printed.add(key)
        t = ev.time_frames / float(SAMPLE_RATE)
        mm = int(t // 60)
        ss = t % 60
        name = ev.sample_name or ""
        pth = ev.sample_path or ""
        print("%d:%05.2f  T%d/%s  0x%03X  %s  %s" % (mm, ss, ev.track, ev.lane, ev.sample_id, pth, name), flush=True)

    mixer = Mixer(events, samples, step_s, gain=args.gain, on_start=on_start)
    if mixer.total == 0:
        if not args.quiet:
            print("mix_play: nothing to play", file=sys.stderr)
        return 0

    if not args.quiet:
        print("Playing %s" % os.path.basename(mix_path), flush=True)

    block = int(args.block)
    stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=args.device, blocksize=block)
    stream.start()
    try:
        pos = 0
        total = mixer.total
        while pos < total:
            count = block if pos + block <= total else total - pos
            out = mixer.mix(pos, count)
            stream.write(pcm_bytes(out))
            pos += count
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())