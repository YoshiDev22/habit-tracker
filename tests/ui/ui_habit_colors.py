"""Habit colors live in the backend: old local colors are uploaded once, then follow the account."""
import asyncio
import datetime as dt
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def colors():
    _, d = call("GET", "/api/habits/definitions", expect=200)
    return {h["key"]: h["color"] for h in d["habits"]}


STAT_DOT = "getComputedStyle(document.querySelector('.stat-dot.gym')).backgroundColor"


async def main():
    token, _ = seed()
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "💪", "color": "#3498db"}, expect=201)
    call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "color": "#3498db", "order": 1}, expect=201)
    call("POST", "/api/habits", {"date": dt.date.today().isoformat(), "habits": {"gym": True}})

    # 1. A browser with the old local colors: uploaded on load, key removed
    b = Browser(fresh=True)
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});"
                   "localStorage.setItem('habit_colors', JSON.stringify({gym: '#e74c3c', lectura: '#3498db', borrado: '#000000'}));")
        await b.goto(BASE + "/", wait=3.0)
        await b.js(CLOSE_WELCOME)
        c = colors()
        left = await b.js("localStorage.getItem('habit_colors')")
        dot = await b.js(STAT_DOT)
        check(c["gym"] == "#e74c3c" and c["lectura"] == "#3498db", f"old local colors uploaded to the account ({c})")
        check(left is None, "the old localStorage key is removed")
        check(dot == "rgb(231, 76, 60)", f"calendar shows the color ({dot})")
    finally:
        await b.close()

    # 2. Another device (clean browser): same colors, from the backend
    b = Browser(fresh=True)
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=3.0)
        await b.js(CLOSE_WELCOME)
        dot = await b.js(STAT_DOT)
        # Sin marcar, el popover pinta el aro del hábito en su color
        pop = await b.js("getComputedStyle(document.querySelector('#habitsList .habit-dot.gym')).borderTopColor")
        check(dot == "rgb(231, 76, 60)" and pop == "rgb(231, 76, 60)", f"a clean browser gets the color from the account ({dot}, {pop})")

        # 3. Change it in the habits setup: saved to the backend, nothing local
        await b.js("showHabitsSetup()")
        await asyncio.sleep(1.5)
        await b.js("""(() => { const row = [...document.querySelectorAll('#habitsOptions .habit-option')].find(r => r.dataset.habitKey === 'gym');
            const input = row.querySelector('input[type=color]'); input.value = '#27ae60';
            input.dispatchEvent(new Event('input', {bubbles: true})); input.dispatchEvent(new Event('change', {bubbles: true})); })()""")
        await asyncio.sleep(0.3)
        await b.js("document.getElementById('saveHabitsBtn').click()")
        await asyncio.sleep(0.8)
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await asyncio.sleep(2.5)
        c = colors()
        dot = await b.js(STAT_DOT)
        left = await b.js("localStorage.getItem('habit_colors')")
        check(c["gym"] == "#27ae60" and dot == "rgb(39, 174, 96)" and left is None,
              f"changing the color saves it to the account ({c['gym']}, {dot}, local={left})")

        # 4. Reportes paints the account color
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(2.0)
        rep = await b.js("""(() => { const row = [...document.querySelectorAll('.report-bar-row')].find(r => r.textContent.includes('Gym'));
            return row ? getComputedStyle(row.querySelector('.report-bar-dot')).backgroundColor : null; })()""")
        check(rep == "rgb(39, 174, 96)", f"Reportes uses the account color ({rep})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_habit_colors():
    asyncio.run(main())
