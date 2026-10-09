"""Notas por día en los hábitos (1.25): el ✎ del popover, el punto del día."""
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
    api.call("POST", "/api/habits/definitions", {"key": "ejer", "label": "Ejercicio", "icon": "🏋"}, expect=201)
    # Un día de este mes que ya pasó (o hoy, si es día 1)
    day = date.today() - timedelta(days=1) if date.today().day > 1 else date.today()
    cell = f"document.querySelector('.day-cell[data-date=\"{day.isoformat()}\"]')"
    row = "document.querySelector('#habitsList .habit-row:has(.habit-btn[data-habit=ejer])')"

    def notes():
        return api.call("GET", f"/api/habits/notes?date_from={day}&date_to={day}", expect=200)[1]["notes"]

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('habitsSetupModal').classList.add('hidden')")
        await b.wait_for(cell)
        await b.js(f"{cell}.click()")
        await b.wait_for(f"!document.getElementById('habitPopover').classList.contains('hidden') && {row}")
        check(await b.js(f"Boolean({row}.querySelector('.habit-note-btn'))"), "each habit in the day's popover has a ✎")

        # Escribirla: Enter la guarda, el popover sigue abierto y el hábito no se marca
        await b.js(f"{row}.querySelector('.habit-note-btn').click()")
        await b.wait_for(f"{row}.querySelector('.habit-note-input')")
        await b.js(f"""(() => {{ const i = {row}.querySelector('.habit-note-input'); i.value = 'cuerda 20 min';
            i.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}})); }})()""")
        await b.wait_for("document.querySelector('#habitsList .habit-note-text:not([hidden])')")
        st = await b.js(f"""({{text: {row}.querySelector('.habit-note-text').textContent,
            open: !document.getElementById('habitPopover').classList.contains('hidden'),
            done: {row}.querySelector('.habit-btn').classList.contains('completed')}})""")
        check(st["text"] == "cuerda 20 min" and st["open"] and not st["done"],
              f"Enter saves it under the habit, keeps the popover open and doesn't mark it ({st})")
        check([n["text"] for n in notes()] == ["cuerda 20 min"], "the note is saved")
        check(await b.wait_for(f"Boolean({cell} && {cell}.querySelector('.day-note-dot'))"), "the day gets the note dot")
        await b.shot("habit_note_popover", full=False)

        # Vaciarla la borra, y el punto se va
        await b.js(f"{cell}.click()")
        await b.wait_for(f"{row}")
        await b.js(f"{row}.querySelector('.habit-note-btn').click()")
        await b.wait_for(f"{row}.querySelector('.habit-note-input')")
        await b.js(f"""(() => {{ const i = {row}.querySelector('.habit-note-input'); i.value = '';
            i.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}})); }})()""")
        await b.wait_for(f"!{cell}.querySelector('.day-note-dot')")
        check(notes() == [], "an empty note is deleted and the dot goes away")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_habit_notes():
    asyncio.run(main())
