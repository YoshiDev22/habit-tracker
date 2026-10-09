"""
Driver mínimo del protocolo de DevTools para Edge o Chrome en modo headless.
Sin Playwright ni Node: solo `websockets`, que ya instala uvicorn[standard].
"""
import asyncio
import base64
import itertools
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

SHOTS = Path(os.environ.get("HABIT_UI_SHOTS", Path(tempfile.gettempdir()) / "habit-ui-shots"))
_last_profile = None

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
NAMES = ["microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def find_browser():
    """Edge o Chrome; HABIT_UI_BROWSER manda si está definida. None si no hay."""
    forced = os.environ.get("HABIT_UI_BROWSER")
    if forced:
        return forced
    for path in CANDIDATES:
        if os.path.exists(path):
            return path
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


class Browser:
    def __init__(self, port=9333, fresh=True):
        self.port = port
        self.fresh = fresh
        self.proc = None
        self.ws = None
        self.ids = itertools.count(1)
        self.pending = {}
        self.console = []
        self.reader = None

    async def start(self):
        # Perfil nuevo en cada prueba: localStorage (tokens, un timer en marcha)
        # no debe pasar de una prueba a la siguiente. fresh=False lo conserva,
        # para probar lo que sobrevive a cerrar y reabrir el navegador.
        # Una carpeta nueva, no borrar la de siempre: en Windows el navegador anterior
        # puede tenerla abierta todavía, el borrado falla en silencio y la prueba
        # siguiente heredaba su localStorage (last_view, el token).
        global _last_profile
        if self.fresh or _last_profile is None:
            _last_profile = Path(tempfile.mkdtemp(prefix="profile-", dir=os.environ.get("HABIT_UI_TMP")))
        profile = _last_profile
        self.proc = subprocess.Popen([
            find_browser(), "--headless=new", f"--remote-debugging-port={self.port}",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--window-size=1280,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = None
        for _ in range(75):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json").read())
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        assert page, "the browser did not start"
        self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000)
        self.reader = asyncio.create_task(self._read())
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        # Una página headless nunca tiene el foco: sin esto no hay focus/blur
        await self.send("Emulation.setFocusEmulationEnabled", enabled=True)

    async def _read(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
            elif msg.get("method") == "Runtime.consoleAPICalled":
                args = " ".join(str(a.get("value", a.get("description", ""))) for a in msg["params"]["args"])
                self.console.append(f"[{msg['params']['type']}] {args}")
            elif msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.console.append(f"[exception] {d.get('exception', {}).get('description', d.get('text'))}")

    async def send(self, method, **params):
        i = next(self.ids)
        fut = asyncio.get_event_loop().create_future()
        self.pending[i] = fut
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        msg = await asyncio.wait_for(fut, 30)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
        return r["result"].get("value")

    async def wait_for(self, expr, ok=bool, timeout=8.0):
        """Evalúa `expr` hasta que `ok(valor)` se cumple o pasa `timeout`, y devuelve el
        último valor. Para lo que depende de un fetch y un repintado: un sleep fijo
        alcanzaba en una máquina tranquila y fallaba en una ocupada."""
        deadline = time.monotonic() + timeout
        # Un elemento (querySelector) llega como {} y en Python {} es falso, así que
        # la espera agotaba su tiempo aunque el elemento estuviera ahí: un nodo vuelve
        # como true. Cualquier otro valor llega tal cual (texto, números, listas)
        probe = f"(v => v instanceof Node ? true : v)({expr})"
        while True:
            value = await self.js(probe)
            if ok(value) or time.monotonic() >= deadline:
                return value
            await asyncio.sleep(0.1)

    async def goto(self, url, wait=1.5):
        await self.send("Page.navigate", url=url)
        await asyncio.sleep(wait)

    async def viewport(self, width, height, mobile=False):
        await self.send("Emulation.setDeviceMetricsOverride", width=width, height=height,
                        deviceScaleFactor=1, mobile=mobile)
        await self.send("Emulation.setTouchEmulationEnabled", enabled=mobile, maxTouchPoints=5 if mobile else 1)

    async def shot(self, name, full=True):
        params = {"format": "png"}
        if full:
            m = await self.send("Page.getLayoutMetrics")
            size = m["cssContentSize"]
            params["clip"] = {"x": 0, "y": 0, "width": size["width"], "height": size["height"], "scale": 1}
            params["captureBeyondViewport"] = True
        r = await self.send("Page.captureScreenshot", **params)
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f"{name}.png"
        path.write_bytes(base64.b64decode(r["data"]))
        return str(path)

    async def quit(self):
        """Cierre ordenado, como cerrar la ventana: el navegador guarda
        localStorage a disco. close() lo mata, que se parece más a un crash."""
        try:
            await self.ws.send(json.dumps({"id": next(self.ids), "method": "Browser.close"}))
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        time.sleep(1.0)

    async def close(self):
        try:
            await self.ws.close()
        finally:
            self.proc.kill()
            self.proc.wait()
            time.sleep(1.0)  # que suelte el perfil antes de volver a arrancar
