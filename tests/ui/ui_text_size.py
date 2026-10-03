import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
FONT = "getComputedStyle(document.documentElement).fontSize"


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('text_size');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        check(await b.js(FONT) == "16px", "default text size is 16px")

        await b.js("openSettings('accessibility')")
        await b.wait_for("!document.getElementById('habitsSetupModal').classList.contains('hidden')")
        pressed = await b.js("document.querySelector('#textSizeToggle [aria-pressed=\"true\"]').dataset.size")
        check(pressed == "normal", f"Configuración › Accesibilidad marks Normal ({pressed})")

        await b.js("document.querySelector('#textSizeToggle [data-size=\"xlarge\"]').click()")
        await asyncio.sleep(0.3)
        await b.js("document.querySelector('#textSizeToggle [data-size=\"large\"]').click()")
        await asyncio.sleep(0.3)
        check(await b.js(FONT) == "19px", "Grande is 19px")
        await b.js("document.querySelector('#textSizeToggle [data-size=\"xlarge\"]').click()")
        await asyncio.sleep(0.3)
        check(await b.js(FONT) == "22px", "Muy grande applies at once (22px)")
        check(await b.js("localStorage.getItem('text_size')") == "xlarge", "saved on this device")
        await b.shot("text_size_settings", full=False)

        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        check(await b.js(FONT) == "22px", "survives a reload")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"nothing overflows the phone width ({wide})")
        await b.shot("text_size_calendar_xlarge", full=False)
        for tab in ("tabProjects", "tabReports"):
            await b.js(f"document.getElementById('{tab}').click()")
            await asyncio.sleep(1.0)
            wide = await b.js("document.documentElement.scrollWidth")
            check(wide <= 390, f"{tab}: nothing overflows the phone width ({wide})")
            await b.shot(f"text_size_{tab}_xlarge", full=False)

        await b.js("document.getElementById('logoutBtn').click()")
        await asyncio.sleep(1.0)
        check(await b.js("localStorage.getItem('text_size')") == "xlarge", "kept after logging out")

        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("openSettings('accessibility')")
        await b.wait_for("!document.getElementById('habitsSetupModal').classList.contains('hidden')")
        await b.js("document.querySelector('#textSizeToggle [data-size=\"normal\"]').click()")
        await asyncio.sleep(0.3)
        check(await b.js(FONT) == "16px", "Normal goes back to 16px")
        check(await b.js("localStorage.getItem('text_size')") is None, "Normal clears the stored value")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_text_size():
    asyncio.run(main())
