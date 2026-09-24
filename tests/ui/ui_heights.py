import asyncio
import json

from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

MEASURE = """({doc: document.documentElement.scrollHeight,
    cal: document.getElementById('viewCalendar').getBoundingClientRect().height,
    proj: document.getElementById('viewProjects').getBoundingClientRect().height,
    rep: document.getElementById('viewReports').getBoundingClientRect().height,
    view: currentViewIndex})"""


async def main():
    token, _ = seed()
    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.setItem('theme', 'dark');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        before = await b.js(MEASURE)
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(1.5)
        on_reports = await b.js(MEASURE)
        await b.shot("reports_dark_mobile", full=True)
        await b.js("document.getElementById('tabCalendar').click()")
        await asyncio.sleep(0.8)
        after = await b.js(MEASURE)
        # The page is as tall as the active view: back on Calendario there is no
        # blank space left over from the taller Reportes view
        assert on_reports["doc"] > before["doc"], (before, on_reports)
        assert after["doc"] == before["doc"], (before, after)
    finally:
        await b.close()


def test_heights():
    asyncio.run(main())
