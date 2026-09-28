"""Marcar o desmarcar un hábito en el popover toca solo ese par (hábito, día): los
registros de un hábito oculto, o de otro dispositivo, no se pierden."""
import asyncio
import json
from datetime import date

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today().isoformat()


def day():
    _, h = call("GET", f"/api/habits?today={TODAY}", expect=200)
    entry = next((e for e in h["entries"] if e["date"] == TODAY), None)
    return entry["habits_data"] if entry else {}


async def main():
    login("oculto@test.com")
    token = api.TOKEN
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    call("POST", "/api/habits/definitions", {"key": "musica", "label": "Música"}, expect=201)
    _, lectura = call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura"}, expect=201)
    # Hoy: Gym y Lectura hechos; después Lectura se oculta
    call("POST", "/api/habits", {"date": TODAY, "habits": {"gym": True, "lectura": True}}, expect=200)
    call("PATCH", f"/api/habits/definitions/{lectura['id']}", {"is_active": False}, expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def toggle(habit):
        await b.js(f"document.querySelector('.day-cell[data-date=\"{TODAY}\"]').click()")
        await asyncio.sleep(0.3)
        await b.js(f"document.querySelector('#habitsList .habit-btn[data-habit=\"{habit}\"]').click()")
        await asyncio.sleep(1.2)

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)

        # Desmarcar el único hábito activo del día: el oculto debe seguir ahí
        await toggle("gym")
        d = day()
        check(not d.get("gym"), f"gym is unmarked ({d})")
        check(d.get("lectura") is True, f"the hidden habit's record survives unmarking the last active one ({d})")

        # Otro dispositivo marca Música; este, con datos viejos, marca Gym: no debe pisarla
        call("POST", "/api/habits", {"date": TODAY, "habits": {**day(), "musica": True}}, expect=200)
        await toggle("gym")
        d = day()
        check(d.get("gym") is True and d.get("musica") is True and d.get("lectura") is True,
              f"marking one habit keeps what another device saved that day ({d})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_hidden_habit_record():
    asyncio.run(main())
