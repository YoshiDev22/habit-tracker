import asyncio
import json

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
STATE = "({view: currentViewIndex, scrollLeft: Math.round(document.querySelector('.board-columns').scrollLeft)})"


def seed():
    login("yoshi@test.com")
    _, bl = call("GET", "/api/boards", expect=200)
    board = bl["boards"][0]
    for name in ("Bloqueado", "Revisión", "Esperando", "Pruebas"):
        call("POST", f"/api/boards/{board['id']}/columns", {"category": "doing", "name": name}, expect=201)
    return api.TOKEN


async def swipe(b, x0, y, x1, steps=8):
    await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x0, "y": y}])
    for i in range(1, steps + 1):
        await b.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": x0 + (x1 - x0) * i / steps, "y": y}])
        await asyncio.sleep(0.02)
    await b.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    await asyncio.sleep(0.6)


async def main():
    token = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        # Teléfono en horizontal: 7 columnas no caben y el tablero se desplaza.
        w, h = 844, 390
        await b.viewport(w, h, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)
        m = await b.js("""(() => { const c = document.querySelector('.board-columns');
            return {top: c.getBoundingClientRect().top, overflow: c.scrollWidth - c.clientWidth}; })()""")
        check(m["overflow"] > 0, f"columns overflow horizontally ({m['overflow']} px)")
        y = m["top"] + 40

        await swipe(b, w * 0.8, y, w * 0.2)
        s = await b.js(STATE)
        check(s["view"] == 1 and s["scrollLeft"] > 0, f"swipe left on the columns scrolls them, stays on Tableros ({s})")

        await b.js("(() => { const c = document.querySelector('.board-columns'); c.scrollLeft = c.scrollWidth; })()")
        await asyncio.sleep(0.2)
        await swipe(b, w * 0.8, y, w * 0.2)
        s = await b.js(STATE)
        check(s["view"] == 2, f"from the right edge, swipe left goes to Reportes ({s})")

        await b.js("goToView(1, {animate: false})")
        await b.js("document.querySelector('.board-columns').scrollLeft = 300")
        await asyncio.sleep(0.3)
        await swipe(b, w * 0.2, y, w * 0.8)
        s = await b.js(STATE)
        check(s["view"] == 1 and s["scrollLeft"] < 300, f"swipe right scrolls back, stays on Tableros ({s})")

        await swipe(b, w * 0.3, m["top"] - 15, w * 0.9)
        s = await b.js(STATE)
        check(s["view"] == 0, f"swipe right outside the columns goes to Calendario ({s})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_board_swipe():
    asyncio.run(main())
