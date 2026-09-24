"""The app is installable: manifest, icons and favicon served; nothing else through /icons."""
import asyncio
import json
import sys
import urllib.error
import urllib.request

from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def get(path):
    try:
        with urllib.request.urlopen(BASE + path) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


async def main():
    token, _ = seed()

    s, ct, body = get("/manifest.webmanifest")
    man = json.loads(body)
    check(s == 200 and ct.startswith("application/manifest+json") and man["display"] == "standalone",
          f"manifest served ({s}, {ct})")
    for icon in man["icons"]:
        s, ct, body = get(icon["src"])
        check(s == 200 and ct == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n", f"{icon['src']} ({s}, {len(body)} bytes)")
    for path in ("/icons/apple-touch-icon.png", "/favicon.ico"):
        s, ct, body = get(path)
        check(s == 200 and body[:4] == b"\x89PNG", f"{path} ({s})")
    for path in ("/icons/nope.png", "/icons/..%2Fbackend%2F.env", "/icons/%2e%2e%2fVERSION"):
        s, _, body = get(path)
        check(s == 404 and b"SECRET" not in body, f"{path} -> {s}")

    b = Browser()
    await b.start()
    try:
        await b.viewport(412, 915, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=3.0)
        errs = await b.send("Page.getInstallabilityErrors")
        manifest = await b.send("Page.getAppManifest")
        check(errs.get("installabilityErrors") == [], f"Edge says it is installable ({errs.get('installabilityErrors')})")
        check(not manifest.get("errors"), f"manifest parses without errors ({manifest.get('errors')})")
        links = await b.js("[...document.querySelectorAll('link[rel=manifest], link[rel=icon], link[rel=apple-touch-icon]')].map(l => l.getAttribute('href'))")
        check(links == ["/manifest.webmanifest", "/icons/favicon-48.png", "/icons/icon-192.png", "/icons/apple-touch-icon.png"], f"head links ({links})")
        sw = await b.js("navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(r => r.length) : 0")
        check(sw == 0, f"no service worker registered ({sw})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_pwa():
    asyncio.run(main())
