import asyncio
import glob
import json
import os
import shutil

from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

import tempfile
OUT = os.path.join(tempfile.gettempdir(), "habit-ui-downloads")


async def main():
    token, _ = seed()
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    b = Browser()
    await b.start()
    try:
        await b.send("Browser.setDownloadBehavior", behavior="allow", downloadPath=OUT)
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(1.5)
        await b.js("document.getElementById('reportsExport').click()")
        await asyncio.sleep(3.0)
    finally:
        await b.close()
    files = glob.glob(os.path.join(OUT, "*.csv"))
    assert len(files) == 1, f"expected one downloaded CSV, got {files}"
    data = open(files[0], "rb").read()
    # BOM so Excel reads the accents, and the header row
    assert data.startswith(b"\xef\xbb\xbf") and b"Fecha,Inicio" in data, data[:120]


def test_export_real():
    asyncio.run(main())
