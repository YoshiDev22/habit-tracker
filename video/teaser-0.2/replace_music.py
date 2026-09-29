"""
Use your own track instead of the synthesized music, snapped to the teaser's beat grid.

    python video/teaser-0.2/build.py --no-render --music mi_tema.wav [--start 12.0]

librosa (only needed for this) finds the track's tempo and beats; the track is
time-stretched to 120 BPM and shifted so one of its beats lands on the first cut (3 s):
at 120 BPM every other cut in cues.json then falls on a beat too. `--start` is where in
your track to begin (default: its first detected beat). Effects, ducking, loudness and
the checks stay exactly as with the synthesized music.
"""
import numpy as np

SR = 48_000
GRID_BPM = 120.0
ANCHOR = 3.0          # first cut of the teaser


def load_aligned(path, duration, start=None, anchor=ANCHOR):
    import librosa  # optional dependency: pip install librosa

    y, _ = librosa.load(str(path), sr=SR, mono=False)
    y = np.atleast_2d(y)
    if y.shape[0] == 1:
        y = np.vstack([y, y])
    _, beats0 = librosa.beat.beat_track(y=librosa.to_mono(y), sr=SR, units="time")
    # Tempo from a straight-line fit over all beat times: far finer than beat_track's
    # own estimate, which drifts tens of ms over half a minute once stretched
    slope = np.polyfit(np.arange(len(beats0)), beats0, 1)[0]
    tempo = 60.0 / slope
    # Half/double-time readings are common: pick the octave closest to 120 BPM
    tempo = min((tempo * f for f in (0.5, 1, 2)), key=lambda b: abs(np.log2(b / GRID_BPM)))
    rate = GRID_BPM / tempo
    if abs(rate - 1) > 0.005:
        y = np.vstack([librosa.effects.time_stretch(ch, rate=rate) for ch in y])
    _, beats = librosa.beat.beat_track(y=librosa.to_mono(y), sr=SR, start_bpm=GRID_BPM, units="time")
    if start is not None:
        beats = beats[beats >= start / rate]
    first = float(beats[0])
    # Place that beat on the anchor; the track may start before 0 (cropped) or after (silence)
    offset = int(round((anchor - first) * SR))
    n = int(round(duration * SR))
    out = np.zeros((2, n))
    src_from, dst_from = max(0, -offset), max(0, offset)
    count = min(y.shape[1] - src_from, n - dst_from)
    out[:, dst_from:dst_from + count] = y[:, src_from:src_from + count]
    grid_beats = beats - first + anchor
    info = {"detected_bpm": round(float(tempo), 2), "stretch_rate": round(float(rate), 4),
            "anchor_beat_in_track_s": round(first, 3), "beats_in_teaser": grid_beats[(grid_beats >= 0) & (grid_beats < duration)]}
    return out, info


def cut_to_beat_report(cues, beats):
    """How far each cut is from the nearest beat of the (aligned) track, in ms."""
    rows = []
    for c in cues:
        if c["kind"] in ("cut", "wipe", "milestone", "outro"):
            d = float(np.min(np.abs(beats - c["t"]))) if len(beats) else None
            rows.append((c["t"], None if d is None else round(d * 1000, 1)))
    return rows
