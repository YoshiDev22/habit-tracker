"""Calendario v2, fase 6: vacaciones. Días en pausa rayados en el calendario, que no
cortan la racha; programar, terminar y el tope de 30 días desde ⚙️."""
import asyncio
import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
DB = Path(os.environ["HABIT_UI_TMP"]) / "test_vacation_pause.db"   # la base de este servidor (conftest)


def insert_past_pause(user_id, start, end):
    """La API no deja programar hacia atrás: unas vacaciones que ya pasaron van directas."""
    with sqlite3.connect(DB) as db:
        db.execute("INSERT INTO streak_pauses (user_id, start_date, end_date) VALUES (?, ?, ?)",
                   (user_id, start.isoformat(), end.isoformat()))


async def main():
    login("vacaciones@test.com")
    token = api.TOKEN
    _, me = call("GET", "/api/auth/me", expect=200)
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    for i in (5, 6, 7):
        call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": "gym", "done": True}, expect=200)
    insert_past_pause(me["id"], TODAY - timedelta(days=4), TODAY - timedelta(days=1))

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    paused_cells = "[...document.querySelectorAll('.day-cell.paused')].map(c => c.dataset.date)"
    pause_items = "[...document.querySelectorAll('#pauseList .pause-item')].map(i => i.textContent)"

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)

        streak = await b.wait_for("document.getElementById('streakCount').textContent", lambda v: v != "0")
        check(streak == "3", f"the vacation did not break the 3-day streak ({streak})")
        asking = await b.js("!document.getElementById('missedDayModal').classList.contains('hidden')")
        check(not asking, "no 'did you forget yesterday?' after a vacation day")
        expected = [str(TODAY - timedelta(days=i)) for i in (4, 3, 2, 1) if (TODAY - timedelta(days=i)).month == TODAY.month]
        cells = await b.js(paused_cells)
        check(cells == expected, f"paused days are marked in the calendar ({cells})")
        if expected:
            await b.js(f"document.querySelector('.day-cell[data-date=\"{expected[-1]}\"]').click()")
            await asyncio.sleep(0.3)
            state = await b.js("document.getElementById('popoverState').textContent")
            check(state == "🏖️ Vacaciones", f"the popover says it was a vacation day ({state})")
            await b.js("hideHabitPopover()")
        await b.shot("vacation_calendar", full=False)

        # ⚙️: la pausa pasada no se lista; programar una desde hoy
        await b.js("document.getElementById('settingsBtn').click()")
        await b.wait_for("!document.getElementById('settingsMenu').hidden && !document.getElementById('habitsSetupModal').classList.contains('hidden')")
        await b.js("document.querySelector('#settingsMenu [data-open=days]').click()")
        await b.wait_for("document.getElementById('pauseStart').value", bool)
        check(await b.js(pause_items) == [], "a finished pause is not listed")
        await b.js(f"""(() => {{ const s = document.getElementById('pauseStart'), e = document.getElementById('pauseEnd');
            s.value = '{TODAY}'; e.value = '{TODAY + timedelta(days=40)}'; }})()""")
        await b.js("document.getElementById('pauseAddBtn').click()")
        err = await b.wait_for("document.getElementById('pauseError').textContent", bool)
        check("30 días" in err, f"more than 30 days is refused with a reason ({err})")

        await b.js(f"document.getElementById('pauseEnd').value = '{TODAY + timedelta(days=2)}'")
        await b.js("document.getElementById('pauseAddBtn').click()")
        items = await b.wait_for(pause_items, lambda v: len(v) == 1)
        check(len(items) == 1 and "En pausa" in items[0] and "Terminar" in items[0], f"the new pause is listed as ongoing ({items})")
        cells = await b.wait_for(paused_cells, lambda v: str(TODAY) in v)
        check(str(TODAY) in cells, "today shows as paused in the calendar")
        await b.shot("vacation_settings", full=False)

        # Terminarla hoy mismo la quita (empezó hoy)
        await b.js("document.querySelector('#pauseList [data-pause-id]').click()")
        items = await b.wait_for(pause_items, lambda v: v == [])
        check(items == [], "ending it today removes it")
        _, pauses = call("GET", "/api/habits/pauses", expect=200)
        check(len(pauses["pauses"]) == 1, "only the past vacation stays in the history")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_vacation_pause():
    asyncio.run(main())
