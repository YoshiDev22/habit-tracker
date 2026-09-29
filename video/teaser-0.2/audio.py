"""
Music + sound effects for the teaser, synthesized with numpy from cues.json.

    python video/teaser-0.2/audio.py      # out/music.wav, out/sfx.wav, out/mix.wav

Deterministic: fixed seed, no wall-clock input; two runs give byte-identical WAVs.
Music: 120 BPM in C major, one bar = 2 s, so every cut on a whole or half second is on
the beat. Structure: light intro (0-3 s), body with drums (3-26 s), lift at 14 s,
resolution at 28 s, clean tail to 31 s.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SR = 48_000
BPM = 120
BEAT = 60 / BPM            # 0.5 s
BAR = 4 * BEAT             # 2 s
SEED = 20260929
DUCK_DB = 5.0              # music under each effect
TARGET_LUFS, TARGET_TP = -14.0, -1.5   # TP a bit under -1 dBTP: AAC adds a little


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Bus:
    """Stereo float buffer with note placement and constant-power panning."""

    def __init__(self, seconds):
        self.x = np.zeros((2, int(round(seconds * SR))), dtype=np.float64)

    def add(self, t, sig, gain=1.0, pan=0.0):
        start = int(round(t * SR))
        if start >= self.x.shape[1]:
            return
        sig = sig[: self.x.shape[1] - start]
        tail = min(int(0.008 * SR), len(sig))      # no note ever stops dead: 8 ms taper
        sig = sig.copy()
        sig[len(sig) - tail:] *= np.linspace(1, 0, tail)
        ang = (pan + 1) * np.pi / 4
        self.x[0, start:start + len(sig)] += sig * gain * np.cos(ang)
        self.x[1, start:start + len(sig)] += sig * gain * np.sin(ang)


def tt(seconds):
    return np.arange(int(round(seconds * SR))) / SR


def env_ar(n_sec, attack, decay):
    t = tt(n_sec)
    return np.minimum(t / attack, 1.0) * np.exp(-t / decay)


# ---------------------------------------------------------------- instruments
def marimba(m, length=0.9):
    t, f = tt(length), midi_hz(m)
    partials = [(1.0, 1.0, 0.55), (3.93, 0.22, 0.10), (9.2, 0.05, 0.04)]
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in partials)
    return s * np.minimum(t / 0.003, 1.0)


def bell(m, length=2.2, decay=0.9):
    t, f = tt(length), midi_hz(m)
    partials = [(1.0, 1.0, decay), (2.0, 0.35, decay * 0.6), (3.01, 0.18, decay * 0.35), (4.16, 0.08, decay * 0.2)]
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in partials)
    return s * np.minimum(t / 0.002, 1.0)


def pad_voice(m, length, bright=1.0, detune_cents=0.0, rng=None):
    t, f = tt(length), midi_hz(m) * 2 ** (detune_cents / 1200)
    phase = rng.uniform(0, 2 * np.pi, 8)
    s = sum((1 / n ** (1.6 / bright)) * np.sin(2 * np.pi * f * n * t + phase[n]) for n in range(1, 7))
    return s * (1 + 0.08 * np.sin(2 * np.pi * 0.35 * t + phase[0]))   # slow shimmer


def bass_note(m, length):
    t, f = tt(length), midi_hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(4 * np.pi * f * t)
    return s * np.minimum(t / 0.008, 1.0) * np.exp(-t / 0.6) * np.minimum((length - t) / 0.05, 1.0)


def kick():
    t = tt(0.35)
    freq = 48 + 70 * np.exp(-t / 0.035)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t / 0.13) * np.minimum(t / 0.002, 1.0)


def hat(rng, decay=0.022, length=0.09):
    n = rng.standard_normal(int(length * SR) + 1)
    return np.diff(n) * np.exp(-tt(length) / decay) * 0.5


def clap(rng):
    return bandpass_sweep(rng.standard_normal(int(0.12 * SR)), 1800, 1600, width=900) * np.exp(-tt(0.12) / 0.035)


def bandpass_sweep(noise, f0, f1, width=700, n_fft=1024):
    """Noise through a Gaussian band-pass whose centre glides f0 -> f1 (STFT overlap-add)."""
    hop = n_fft // 4
    win = np.hanning(n_fft)
    pad = np.concatenate([np.zeros(n_fft), noise, np.zeros(n_fft)])
    out = np.zeros_like(pad)
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    frames = range(0, len(pad) - n_fft, hop)
    for i, pos in enumerate(frames):
        k = i / max(len(frames) - 1, 1)
        fc = f0 * (f1 / f0) ** k
        spec = np.fft.rfft(pad[pos:pos + n_fft] * win) * np.exp(-0.5 * ((freqs - fc) / width) ** 2)
        out[pos:pos + n_fft] += np.fft.irfft(spec, n_fft) * win
    return out[n_fft:n_fft + len(noise)] / 1.5


def reverb(x, seconds=1.4, mix=0.18, seed=SEED):
    """Stereo convolution with a seeded, exponentially decaying noise tail."""
    rng = np.random.default_rng(seed + 7)
    t = tt(seconds)
    out = np.zeros_like(x)
    for ch in range(2):
        ir = rng.standard_normal(len(t)) * np.exp(-t / (seconds / 5)) * np.minimum(t / 0.01, 1)
        ir /= np.sqrt(np.sum(ir ** 2))
        n = x.shape[1] + len(ir)
        size = 1 << (n - 1).bit_length()
        wet = np.fft.irfft(np.fft.rfft(x[ch], size) * np.fft.rfft(ir, size), size)[: x.shape[1]]
        out[ch] = x[ch] + mix * wet
    return out


# ---------------------------------------------------------------- music
CHORDS = {  # pad voicing (octave 4), bass root, melody tones (octave 5)
    "C":  ([60, 64, 67], 36, [72, 76, 79]),
    "Am": ([57, 60, 64], 33, [69, 72, 76]),
    "F":  ([57, 60, 65], 41, [69, 72, 77]),
    "G":  ([55, 59, 62], 43, [67, 71, 74]),
}
# One chord per 2-s bar; bar 7 (14 s) starts the lift, bar 14 (28 s) resolves to C
PROGRESSION = ["C", "Am", "F", "G", "C", "Am", "F", "Am", "F", "G", "C", "Am", "F", "G", "C", "C"]
MELODY_RHYTHM = [0, 0.5, 1.5, 2.0, 3.0]                 # in beats
MELODY_SHAPES = [[0, 1, 2, 1, 0], [2, 1, 0, 1, 2], [0, 2, 1, 2, 1], [1, 0, 2, 0, 1]]


def music(duration, rng):
    pad, keys, bass, drums, lift = (Bus(duration) for _ in range(5))
    for bar, name in enumerate(PROGRESSION):
        t0 = bar * BAR
        if t0 >= duration:
            break
        voicing, root, tones = CHORDS[name]
        final = bar >= 14
        in_lift = 7 <= bar <= 8

        # Pad: overlapping bars, a touch brighter in the lift, long release at the end
        length = 3.0 if not final else duration - t0
        if bar == 15:
            length = 0   # bar 14 already holds the final chord to the end
        for i, m in enumerate(voicing + [root + 12]):
            for det, pan in ((-6, -0.6), (6, 0.6)):
                if length <= 0:
                    continue
                v = pad_voice(m, length, bright=1.35 if in_lift else 1.0, detune_cents=det + i, rng=rng)
                attack = 0.35 if bar else 0.9
                release = 2.4 if final else 0.9
                t = tt(length)
                e = np.minimum(t / attack, 1) * np.clip((length - t) / release, 0, 1)
                if final:
                    e *= np.exp(-t / 1.6)
                pad.add(t0, v * e, 0.035, pan)

        # Marimba melody: sparse in the intro, full from bar 1, one long note at the end
        if final:
            if bar == 14:
                keys.add(t0, marimba(72, 2.5), 0.32, 0.15)
                for j, m in enumerate([84, 88, 91]):
                    keys.add(t0 + 0.06 * j, bell(m, 2.8, 0.8), 0.07, -0.2 + 0.2 * j)
            continue
        shape = MELODY_SHAPES[bar % 4]
        for step, beat in enumerate(MELODY_RHYTHM):
            if bar == 0 and step % 2:
                continue
            if bar == 13 and step > 2:
                continue    # leave air before the resolution
            m = tones[shape[step]]
            keys.add(t0 + beat * BEAT, marimba(m), 0.30 if bar else 0.2, 0.15)
        if bar == 13:
            keys.add(t0 + 2 * BEAT, marimba(74, 1.2), 0.22, 0.15)

        # Lift: a glockenspiel arpeggio an octave up, in eighths
        if in_lift:
            for step in range(8):
                m = tones[[0, 1, 2, 1][step % 4]] + 12
                lift.add(t0 + step * BEAT / 2, bell(m, 0.6, 0.18), 0.05, -0.35)

        # Bass from 3 s: root on 1, fifth on 3, pickup on the "and" of 4
        for beat, interval, length in ((0, 0, 0.9), (2, 7, 0.7), (3.5, 0, 0.25)):
            t = t0 + beat * BEAT
            if t >= 3.0:
                bass.add(t, bass_note(root + interval, length), 0.30)

        # Drums from 3 s: soft kick on 1 and 3, hats on the off-beats, a light clap on 2 and 4
        for beat in range(4):
            t = t0 + beat * BEAT
            if t >= 3.0 and (beat in (0, 2)) and not (bar == 13 and beat == 2):
                drums.add(t, kick(), 0.55)
            if t >= 3.0 and beat in (1, 3):
                drums.add(t, clap(rng), 0.10, 0.1)
            if t + BEAT / 2 >= 3.0:
                drums.add(t + BEAT / 2, hat(rng), 0.11, 0.3)
            if in_lift and t >= 3.0:   # a little extra motion in the lift
                drums.add(t + BEAT / 4, hat(rng, 0.012), 0.05, -0.3)
                drums.add(t + 3 * BEAT / 4, hat(rng, 0.012), 0.05, -0.3)
        if bar == 13:   # tiny hat run into the resolution
            for i in range(4):
                drums.add(t0 + 3 * BEAT + i * BEAT / 4, hat(rng, 0.015), 0.05 + 0.02 * i, 0.3)

    # Swell into the lift (13 -> 14 s) and the resolution hit at 28 s
    # It stops 50 ms before the cut (fast fade) so the cut's whoosh is not buried in it
    sw = bandpass_sweep(rng.standard_normal(int(0.95 * SR)), 500, 5000, width=1500)
    shape = np.linspace(0, 1, len(sw)) ** 2
    shape[-int(0.04 * SR):] *= np.linspace(1, 0, int(0.04 * SR))
    lift.add(13.0, sw * shape, 0.05)
    drums.add(28.0, kick(), 0.6)
    cym = bandpass_sweep(rng.standard_normal(int(2.2 * SR)), 6000, 3000, width=2500) * np.exp(-tt(2.2) / 0.6)
    drums.add(28.0, cym, 0.05, 0.2)

    melodic = reverb(pad.x + keys.x + lift.x, mix=0.22)
    return melodic + bass.x + reverb(drums.x, seconds=0.6, mix=0.06)


# ---------------------------------------------------------------- effects
def sfx_click(rng):
    t = tt(0.03)
    tone = np.sin(2 * np.pi * 2600 * t) * np.exp(-t / 0.006)
    return 0.6 * tone + 0.25 * hat(rng, 0.003, 0.03)


def sfx_whoosh(rng):
    n = rng.standard_normal(int(0.38 * SR))
    s = bandpass_sweep(n, 700, 3200, width=900)
    t = tt(0.38)
    return s * np.minimum(t / 0.012, 1) * (1 - t / 0.38) ** 2


def sfx_chime():
    out = np.zeros(int(1.6 * SR))
    for j, m in enumerate([88, 91, 96]):          # E6 G6 C7: "done"
        b = bell(m, 1.4, 0.55)
        start = int(j * 0.07 * SR)
        out[start:start + len(b)] += b * (1 - 0.15 * j)
    return out


def sfx_pop():
    t = tt(0.09)
    freq = 420 * (2.4 ** (t / 0.09))
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.minimum(t / 0.002, 1) * np.exp(-t / 0.03)


def sfx_ding():
    b = np.zeros(int(0.9 * SR))
    for j, m in enumerate([84, 91]):             # C6 -> G6: file ready
        n = bell(m, 0.8, 0.3)
        s = int(j * 0.09 * SR)
        b[s:s + len(n)] += n
    return b


def plan_effects(cues):
    """Which cue gets which sound. Fewer is better: one whoosh per big scene change."""
    clicks = [c["t"] for c in cues if c["kind"] in ("click", "export_click")]
    events, whoosh_at = [], set()
    for c in cues:
        k, t = c["kind"], c["t"]
        if k == "click":
            events.append({"t": t, "sfx": "click", "gain": 0.20, "dur": 0.03})
        elif k == "export_click":
            events.append({"t": t, "sfx": "pop", "gain": 0.30, "dur": 0.09})
        elif k == "toast":
            events.append({"t": t, "sfx": "ding", "gain": 0.12, "dur": 0.5})
        elif k == "milestone":
            events.append({"t": t, "sfx": "chime", "gain": 0.16, "dur": 0.9})
        elif k in ("cut", "wipe", "zoom_start", "outro"):
            # One whoosh per moment; none right after a click (the click already says it)
            after_click = any(0 <= t - ct <= 0.35 for ct in clicks)
            if not after_click and not any(abs(t - w) < 0.1 for w in whoosh_at):
                whoosh_at.add(t)
                events.append({"t": t, "sfx": "whoosh", "gain": 0.10 if k == "zoom_start" else 0.17, "dur": 0.3})
    return sorted(events, key=lambda e: e["t"])


def effects(duration, events, rng):
    bus = Bus(duration)
    makers = {"click": lambda: sfx_click(rng), "whoosh": lambda: sfx_whoosh(rng), "chime": sfx_chime,
              "pop": sfx_pop, "ding": sfx_ding}
    pans = {"click": 0.1, "whoosh": 0.0, "chime": 0.0, "pop": 0.1, "ding": 0.0}
    for e in events:
        bus.add(e["t"], makers[e["sfx"]](), e["gain"], pans[e["sfx"]])
    return bus.x


def duck_curve(n, events, depth_db=DUCK_DB, attack=0.02, release=0.25):
    """1.0 = full music; dips by depth_db around each effect (ramps, no clicks)."""
    t = np.arange(n) / SR
    amount = np.zeros(n)
    for e in events:
        a, b = e["t"], e["t"] + e["dur"]
        ramp_in = np.clip((t - (a - attack)) / attack, 0, 1)
        ramp_out = np.clip(1 - (t - b) / release, 0, 1)
        amount = np.maximum(amount, np.where(t < a, ramp_in, np.where(t <= b, 1.0, ramp_out)))
    return 10 ** (-depth_db * amount / 20)


def fades(x, fade_in=0.3, fade_out=1.0):
    n = x.shape[1]
    g = np.ones(n)
    i, o = int(fade_in * SR), int(fade_out * SR)
    g[:i] = np.linspace(0, 1, i)
    g[n - o:] = np.linspace(1, 0, o) ** 1.5
    return x * g


def write_wav(path, x, bits=24):
    x = np.clip(x, -1, 1 - 1e-9)
    if bits == 24:
        ints = np.round(x.T * (2 ** 23 - 1)).astype("<i4").reshape(-1)
        raw = np.frombuffer(ints.tobytes(), dtype=np.uint8).reshape(-1, 4)[:, :3].tobytes()
    else:
        raw = np.round(x.T * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(bits // 8)
        w.setframerate(SR)
        w.writeframes(raw)


def sliding(x, width, fn):
    """Centered sliding max/min over `width` samples (numpy only)."""
    pad = np.pad(x, (width // 2, width - width // 2 - 1), mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(pad, width)
    return fn(view, axis=1)


def limit(x, ceiling, lookahead=0.005):
    """Look-ahead peak limiter: the needed gain is held for +-lookahead and then averaged
    over a window no wider than that, so it is already down at every peak and moves
    smoothly. Only the few transients above `ceiling` are touched."""
    peak = np.max(np.abs(x), axis=0)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    k = int(lookahead * SR)
    held = sliding(need, 2 * k + 1, np.min)
    g = np.convolve(np.pad(held, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    return x * g


def measure(path):
    spec = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:print_format=json"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", spec, "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def loudnorm(src, dst):
    """Two-pass ffmpeg loudnorm to -14 LUFS / -1.5 dBTP, linear (a constant gain)."""
    spec = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11"
    p1 = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af", spec + ":print_format=json",
                         "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    m = json.loads(p1[p1.rindex("{"):p1.rindex("}") + 1])
    second = (f"{spec}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json")
    p2 = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-af", second,
                         "-ar", str(SR), "-c:a", "pcm_s24le", str(dst)], capture_output=True, text=True, check=True).stderr
    r = json.loads(p2[p2.rindex("{"):p2.rindex("}") + 1])
    return m, r


def main():
    cues = json.loads((HERE / "cues.json").read_text(encoding="utf-8"))
    duration = cues["duration"]
    rng = np.random.default_rng(SEED)
    OUT.mkdir(exist_ok=True)

    mus = music(duration, rng)      # always synthesized: keeps the RNG stream (and the effects) identical
    if "--music" in sys.argv:
        from replace_music import cut_to_beat_report, load_aligned
        start = float(sys.argv[sys.argv.index("--start") + 1]) if "--start" in sys.argv else None
        mus, info = load_aligned(sys.argv[sys.argv.index("--music") + 1], duration, start)
        mus *= 0.25 / max(np.max(np.abs(mus)), 1e-9)      # roughly the synthesized music's level
        report = cut_to_beat_report(cues["cues"], info.pop("beats_in_teaser"))
        print("custom music:", info)
        print("cuts vs nearest beat of your track (ms):", ", ".join(f"{t}:{d}" for t, d in report))
    events = plan_effects(cues["cues"])
    fx = effects(duration, events, rng)
    duck = duck_curve(mus.shape[1], events)

    # Gentle bus glue so the master has headroom for -14 LUFS at -1.5 dBTP without limiting
    mix = fades(mus * duck + fx)
    peak = np.max(np.abs(mix))
    scale = 0.5 / peak
    write_wav(OUT / "music.wav", fades(mus) * scale)       # stems: same scale, music NOT ducked
    write_wav(OUT / "sfx.wav", fades(fx) * scale)
    # Limit only as much as a linear (constant-gain) loudnorm needs: peak-to-loudness
    # must fit TARGET_TP - TARGET_LUFS, with a margin for inter-sample peaks.
    mix = mix * scale
    for _ in range(3):
        write_wav(OUT / "mix_raw.wav", mix)
        m = measure(OUT / "mix_raw.wav")
        room = (TARGET_TP - TARGET_LUFS) - (float(m["input_tp"]) - float(m["input_i"]))
        if room > 0.3:
            break
        ceiling = 10 ** ((float(m["input_i"]) + TARGET_TP - TARGET_LUFS - 0.8) / 20)
        mix = limit(mix, ceiling)
    first, second = loudnorm(OUT / "mix_raw.wav", OUT / "mix.wav")
    (OUT / "mix_raw.wav").unlink()
    (HERE / "sfx_plan.json").write_text(json.dumps(events, indent=1) + "\n", encoding="utf-8")
    print(f"effects: {len(events)}  " + ", ".join(f"{e['t']:.2f} {e['sfx']}" for e in events))
    print(f"loudnorm in: I={first['input_i']} TP={first['input_tp']} LRA={first['input_lra']}"
          f" -> out: I={second['output_i']} TP={second['output_tp']} ({second['normalization_type']})")


if __name__ == "__main__":
    main()
