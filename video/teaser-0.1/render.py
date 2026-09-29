"""
Render index.html frame by frame (window.seek(t) + CDP screenshot) and encode with ffmpeg.

    python video/teaser-0/render.py                 # out/teaser.mp4 + out/contact.png
    python video/teaser-0/render.py --frames 4.5,15.6   # only stills, to out/frame_*.png
"""
import asyncio
import base64
import functools
import http.server
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tests" / "ui"))
if not os.environ.get("HABIT_UI_BROWSER") and os.name == "posix" and os.path.exists("/opt/pw-browsers/chromium"):
    os.environ["HABIT_UI_BROWSER"] = str(HERE / "chromium.sh")
from cdp import Browser  # noqa: E402

FPS, DURATION, W, H = 60, 31, 1920, 1080
OUT = HERE / "out"


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(HERE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}/index.html"


async def grab(b):
    r = await b.send("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": W, "height": H, "scale": 1})
    return base64.b64decode(r["data"])


async def render(url, stills=None):
    OUT.mkdir(exist_ok=True)
    b = Browser(port=9444)
    await b.start()
    try:
        await b.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
        await b.goto(url, wait=0.5)
        assert await b.js("window.ready"), "page not ready"
        if stills:
            for t in stills:
                await b.js(f"window.seek({t})")
                (OUT / f"frame_{t:05.2f}.png").write_bytes(await grab(b))
            return
        ff = subprocess.Popen([
            "ffmpeg", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(OUT / "teaser.mp4")], stdin=subprocess.PIPE)
        total = FPS * DURATION
        for n in range(total):
            await b.js(f"window.seek({n / FPS})")
            ff.stdin.write(await grab(b))
            if n % 120 == 0:
                print(f"frame {n}/{total}", flush=True)
        ff.stdin.close()
        assert ff.wait() == 0, "ffmpeg failed"
        errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
        assert not errors, errors
    finally:
        await b.close()


def contact_sheet():
    # 2 fps over 20 s = 62 thumbnails, 8 columns x 8 rows
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(OUT / "teaser.mp4"), "-vf",
                    "fps=2,scale=480:-1,drawtext=text='%{pts\\:hms}':x=8:y=8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6,tile=8x8:padding=4",
                    "-frames:v", "1", str(OUT / "contact.png")], check=True)


def main():
    httpd, url = serve()
    try:
        if "--frames" in sys.argv:
            stills = [float(x) for x in sys.argv[sys.argv.index("--frames") + 1].split(",")]
            asyncio.run(render(url, stills))
        else:
            asyncio.run(render(url))
            contact_sheet()
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
