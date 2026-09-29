"""
Export the timeline of index.html (window.exportCues) to cues.json.

The page is the single source of truth: cuts, clicks, zoom starts and beats are read
from the same BEATS / SEGMENTS / WIPES / MOVES that paint the frames.

    python video/teaser-0.2/export_cues.py
"""
import asyncio
import json

from render import HERE, Browser, serve


async def export(url):
    b = Browser(port=9445)
    await b.start()
    try:
        await b.goto(url, wait=0.5)
        assert await b.js("window.ready"), "page not ready"
        return await b.js("window.exportCues()")
    finally:
        await b.close()


def main():
    httpd, url = serve()
    try:
        data = asyncio.run(export(url))
    finally:
        httpd.shutdown()
    (HERE / "cues.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in data["cues"]:
        if c["kind"] != "beat":
            print(f"{c['t']:6.3f}  {c['kind']:<12} {c.get('to', c.get('shot', c.get('text', '')))}")


if __name__ == "__main__":
    main()
