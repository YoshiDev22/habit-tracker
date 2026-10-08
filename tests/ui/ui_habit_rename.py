"""Renombrar un hábito desde Configuración › Hábitos (1.24): conserva sus días."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import login
from cdp import Browser

BASE = api.BASE
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, habit = api.call("POST", "/api/habits/definitions", {"key": "gymx", "label": "Gym", "icon": "💪"}, expect=201)
    days = [date.today() - timedelta(days=i) for i in (1, 2, 3)]
    for d in days:
        api.call("PATCH", f"/api/habits/day/{d}", {"habit_key": "gymx", "done": True}, expect=200)
    name = "document.querySelector('.habit-option[data-habit-key=gymx] .habit-name')"

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("openSettings('habits')")
        await b.wait_for(f"{name}")
        check(await b.js(f"{name}.value") == "Gym", "the habit's name is an editable field")
        # El campo no aprieta a los demás: el check sigue cuadrado y el color redondo
        sizes = await b.js("""(() => { const row = document.querySelector('.habit-option[data-habit-key=gymx]');
            const box = s => { const r = row.querySelector(s).getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
            return {check: box('.habit-check'), color: box('.habit-color')}; })()""")
        check(sizes["check"] == [20, 20] and sizes["color"] == [30, 30], f"the check stays square and the color round ({sizes})")
        await b.shot("habit_rename_row", full=False)

        # Vacío: no se guarda
        await b.js(f"{name}.value = '  '; {name}.dispatchEvent(new Event('input'))")
        await b.js("document.getElementById('saveHabitsBtn').click()")
        await b.wait_for("!document.getElementById('setupError').classList.contains('hidden')")
        check("nombre" in await b.js("document.getElementById('setupError').textContent"), "an empty name is not saved")

        # Ejercicio: se guarda, y el hábito conserva sus días
        await b.js(f"{name}.value = 'Ejercicio'; {name}.dispatchEvent(new Event('input'))")
        await b.js("document.getElementById('saveHabitsBtn').click()")
        await b.wait_for("!document.getElementById('confirmModal').classList.contains('hidden')")
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for("document.getElementById('habitsSetupModal').classList.contains('hidden')")
        _, defs = api.call("GET", "/api/habits/definitions", expect=200)
        renamed = next(h for h in defs["habits"] if h["id"] == habit["id"])
        check(renamed["label"] == "Ejercicio" and renamed["key"] == "gymx" and renamed["icon"] == "💪",
              f"the name changed, its key and emoji stay ({renamed})")
        _, export = api.call("GET", f"/api/habits/export?date_from={days[-1]}&date_to={days[0]}&today={date.today()}", expect=200)
        done = sorted(r["date"] for r in export["rows"] if r["habit_key"] == "gymx" and r["done"])
        check(done == sorted(d.isoformat() for d in days) and all(r["label"] == "Ejercicio" for r in export["rows"] if r["habit_key"] == "gymx"),
              f"its days are kept under the new name ({done})")
        legend = await b.js("document.body.textContent.includes('Ejercicio')")
        check(legend, "the calendar shows the new name")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_habit_rename():
    asyncio.run(main())
