"""
Measure what cannot be listened to: loudness, sync of every effect with cues.json, the
video's own cuts against cues.json, and audio/video duration. Writes out/verify.json and
out/waveform.png (with the cuts marked).

    python video/teaser-0.2/verify.py
"""
import json
import re
import subprocess

import numpy as np

from audio import SR
from render import HERE, OUT

TEASER = OUT / "teaser.mp4"
FPS = 60
MATCH_WINDOW = 0.05    # an effect with no onset within +-50 ms counts as missing


def ffmpeg_err(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *map(str, args)],
                          capture_output=True, text=True, check=True).stderr


def loudness():
    err = ffmpeg_err("-i", TEASER, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-")
    summary = err[err.rindex("Summary:"):]
    num = lambda key: float(re.search(rf"{key}:\s+(-?[\d.]+)", summary).group(1))
    return {"integrated_lufs": num("I"), "lra_lu": num("LRA"), "true_peak_dbtp": num("Peak")}


def decode_mono(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def onsets(x, n=256, hop=48):
    """Spectral-flux onsets (log magnitude, above 300 Hz), 1 ms hop, adaptive threshold.
    Returns onset times in seconds (frame centres)."""
    win = np.hanning(n)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (n // 2, n)), n)[::hop]
    mag = np.log1p(1000 * np.abs(np.fft.rfft(frames * win, axis=1)))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    flux = np.maximum(np.diff(mag[:, freqs > 300], axis=0), 0).sum(axis=1)
    flux = np.concatenate([[0], flux])
    # threshold: local median + 3 * local MAD over ~0.4 s
    w = 401
    padded = np.pad(flux, w // 2, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(padded, w)
    med = np.median(view, axis=1)
    mad = np.median(np.abs(view - med[:, None]), axis=1)
    thr = med + 3 * mad + 1e-3
    peaks = [i for i in range(1, len(flux) - 1)
             if flux[i] > thr[i] and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]]
    # rising edge: first frame of the run above threshold that leads to each peak
    times = []
    for p in peaks:
        i = p
        while i > 0 and flux[i - 1] > thr[i - 1]:
            i -= 1
        times.append(i * hop / SR)
    return np.array(sorted(set(times)))


def match(expected, detected):
    rows = []
    for e in expected:
        d = detected[np.argmin(np.abs(detected - e["t"]))] if len(detected) else None
        off = None if d is None or abs(d - e["t"]) > MATCH_WINDOW else round((d - e["t"]) * 1000, 1)
        rows.append({"t": e["t"], "sfx": e["sfx"], "offset_ms": off})
    found = [abs(r["offset_ms"]) for r in rows if r["offset_ms"] is not None]
    return rows, (max(found) if found else None), sum(r["offset_ms"] is None for r in rows)


def frame_diffs():
    """Mean absolute difference between consecutive frames (160x90 grey)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(OUT / "video.mp4"), "-vf", "scale=160:90,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 90, 160).astype(np.float64)
    return np.concatenate([[0], np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))])


def video_cuts(expected, diffs, search=10):
    """For each cue, the frame with the biggest change within +-search frames, and how much
    bigger it is than the typical change around it (a real cut stands far above the zooms)."""
    rows = []
    for t in expected:
        c = int(round(t * FPS))
        lo, hi = max(c - search, 1), min(c + search, len(diffs) - 1)
        i = lo + int(np.argmax(diffs[lo:hi + 1]))
        around = np.median(diffs[max(c - 30, 1):c + 30])
        rows.append({"t": t, "video_s": round(i / FPS, 4), "offset_ms": round((i / FPS - t) * 1000, 1),
                     "contrast": round(float(diffs[i] / max(around, 1e-6)), 1)})
    return rows


def mux_lag():
    """Lag of the AAC in teaser.mp4 against mix.wav (cross-correlation over the first 8 s)."""
    a = decode_mono(OUT / "mix.wav")[: 8 * SR]
    b = decode_mono(TEASER)[: 8 * SR]
    size = 1 << (len(a) + len(b)).bit_length()
    xc = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
    lag = int(np.argmax(np.concatenate([xc[-2000:], xc[:2000]]))) - 2000
    return {"samples": lag, "ms": round(lag / SR * 1000, 2)}


def durations():
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                          "-of", "json", str(TEASER)], capture_output=True, text=True, check=True).stdout
    d = {s["codec_type"]: float(s["duration"]) for s in json.loads(out)["streams"]}
    return {"video_s": d["video"], "audio_s": d["audio"], "diff_frames": round(abs(d["video"] - d["audio"]) * FPS, 2)}


def waveform(cues, events):
    """Waveform of the final audio with every cut (dark) and effect (accent) marked."""
    W, H, top = 1920, 360, 70
    font = HERE / "assets" / "fonts" / "Inter-500.ttf"
    dur = cues["duration"]
    x = lambda t: int(round(t / dur * (W - 1)))
    draw = []
    for c in cues["cues"]:
        if c["kind"] in ("cut", "wipe", "milestone", "outro"):
            draw.append(f"drawbox=x={x(c['t'])}:y={top}:w=2:h={H}:color=0x1b1d2e@0.85:t=fill")
            draw.append(f"drawtext=fontfile={font}:text='{c['t']:.2f}':x={x(c['t']) + 4}:y={top - 22}"
                        f":fontsize=16:fontcolor=0x1b1d2e")
    for e in events:
        draw.append(f"drawbox=x={x(e['t'])}:y={top + H - 26}:w=3:h=26:color=0xe67e22:t=fill")
    for s in range(0, int(dur) + 1):
        draw.append(f"drawbox=x={x(s)}:y={top + H}:w=1:h=8:color=0x6b6f86:t=fill")
    draw.append(f"drawtext=fontfile={font}:text='cortes (lineas oscuras) y efectos (naranja)':x=12:y=12"
                f":fontsize=20:fontcolor=0x6b6f86")
    graph = (f"[0:a]showwavespic=s={W}x{H}:colors=0x667eea:scale=sqrt,format=rgba[w];"
             f"color=c=white:s={W}x{H + top + 30}[bg];[bg][w]overlay=0:{top}," + ",".join(draw))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(TEASER), "-filter_complex", graph,
                    "-frames:v", "1", str(OUT / "waveform.png")], check=True)


def main():
    cues = json.loads((HERE / "cues.json").read_text(encoding="utf-8"))
    events = json.loads((HERE / "sfx_plan.json").read_text(encoding="utf-8"))
    report = {"loudness": loudness(), "durations": durations()}

    final_rows, final_max, final_missing = match(events, onsets(decode_mono(TEASER)))
    stem_rows, stem_max, stem_missing = match(events, onsets(decode_mono(OUT / "sfx.wav")))
    report["onsets_final_mix"] = {"max_abs_offset_ms": final_max, "missing": final_missing, "events": final_rows}
    report["onsets_sfx_stem"] = {"max_abs_offset_ms": stem_max, "missing": stem_missing}

    expected_cuts = [c["t"] for c in cues["cues"] if c["kind"] in ("cut", "milestone")]
    cut_rows = video_cuts(expected_cuts, frame_diffs())
    report["video_cuts_vs_cues"] = cut_rows
    report["mux_lag"] = mux_lag()
    waveform(cues, events)

    (OUT / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    L, D = report["loudness"], report["durations"]
    print(f"loudness: I={L['integrated_lufs']} LUFS  LRA={L['lra_lu']} LU  TP={L['true_peak_dbtp']} dBTP")
    print(f"durations: video={D['video_s']} s  audio={D['audio_s']} s  diff={D['diff_frames']} frames")
    print(f"effect onsets, final mix: max |offset| = {final_max} ms, missing {final_missing}/{len(events)}")
    for r in final_rows:
        print(f"   {r['t']:6.2f} {r['sfx']:<7} {r['offset_ms']} ms")
    print(f"effect onsets, sfx stem:  max |offset| = {stem_max} ms, missing {stem_missing}/{len(events)}")
    print("video cuts vs cues: " + ", ".join(f"{r['t']}:{r['offset_ms']:+.1f}ms(x{r['contrast']})" for r in cut_rows))
    print(f"mux lag (AAC vs mix.wav): {report['mux_lag']['samples']} samples = {report['mux_lag']['ms']} ms")


if __name__ == "__main__":
    main()
