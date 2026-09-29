"""
Teaser 0.2 in one command: cues -> frames -> audio -> mux -> checks.

    python video/teaser-0.2/build.py              # everything
    python video/teaser-0.2/build.py --no-render  # reuse out/video.mp4 (audio work only)
    python video/teaser-0.2/build.py --no-render --music track.wav [--start 12]   # your own music

Reuses the approved captures and clicks.json: demo.py is NOT run here.
"""
import subprocess
import sys

from render import HERE, OUT

PY = sys.executable


def run(*args):
    print("+", " ".join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True)


def main():
    run(PY, HERE / "export_cues.py")
    if "--no-render" not in sys.argv or not (OUT / "video.mp4").exists():
        run(PY, HERE / "render.py")
    passthrough = [a for i, a in enumerate(sys.argv[1:], 1)
                   if a in ("--music", "--start") or sys.argv[i - 1] in ("--music", "--start")]
    run(PY, HERE / "audio.py", *passthrough)
    # Video stream copied as is; audio AAC 192 kbps, 48 kHz, stereo
    run("ffmpeg", "-loglevel", "error", "-y", "-i", OUT / "video.mp4", "-i", OUT / "mix.wav",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-ac", "2", "-movflags", "+faststart", OUT / "teaser.mp4")
    run(PY, HERE / "verify.py")


if __name__ == "__main__":
    main()
