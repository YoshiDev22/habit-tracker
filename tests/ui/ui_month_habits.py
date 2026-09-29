"""Un mes muestra los hábitos activos más los ocultos con registros en ese mes, en su
lugar: puntos, popover y "Este mes". Una fila hasta 5 puntos; con 6, dos filas."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
LAST_MONTH_DAY = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=5)


def seed(email, keys):
    login(email)
    ids = {}
    colors = ["#3498db", "#e74c3c", "#27ae60", "#9b59b6", "#f39c12", "#1abc9c"]
    for key, color in zip(keys, colors):
        _, h = call("POST", "/api/habits/definitions", {"key": key, "label": key.title(), "color": color}, expect=201)
        ids[key] = h["id"]
    return api.TOKEN, ids


DAY = """((d) => {
    const cell = document.querySelector(`.day-cell[data-date="${d}"]`);
    if (!cell) return null;
    const dots = [...cell.querySelectorAll('.habit-dot')];
    return {dots: dots.length, active: dots.map(x => x.classList.contains('active')),
            rows: new Set(dots.map(x => Math.round(x.getBoundingClientRect().top))).size};
})"""


async def open_app(b, token):
    await b.goto(BASE + "/")
    await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
    await b.goto(BASE + "/", wait=2.5)


async def main():
    token, ids = seed("mes@test.com", ["gym", "lectura", "musica", "dieta"])
    call("PATCH", f"/api/habits/day/{LAST_MONTH_DAY}", {"habit_key": "lectura", "done": True}, expect=200)
    call("PATCH", f"/api/habits/day/{LAST_MONTH_DAY}", {"habit_key": "dieta", "done": True}, expect=200)
    call("PATCH", f"/api/habits/definitions/{ids['lectura']}", {"is_active": False}, expect=200)
    six, _ = seed("seis@test.com", ["a", "b", "c", "d", "e", "f"])

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)
        await open_app(b, token)
        today = await b.wait_for(f"{DAY}('{TODAY}')", lambda v: v is not None)
        check(today["dots"] == 3 and today["rows"] == 1, f"this month: the 3 active habits, one row ({today})")

        # El mes pasado: Lectura (oculta) tiene un registro, así que vuelve a su lugar
        await b.js("document.getElementById('prevMonth').click()")
        d = await b.wait_for(f"{DAY}('{LAST_MONTH_DAY}')", lambda v: v is not None and v["dots"] == 4)
        check(d is not None and d["dots"] == 4 and d["active"] == [False, True, False, True],
              f"last month: 4 places, Lectura second and Dieta fourth marked ({d})")
        cards = await b.js("[...document.querySelectorAll('#statsGrid .stat-card')].map(c => [c.querySelector('.stat-label').textContent, c.querySelector('.stat-value').textContent, c.classList.contains('is-hidden')])")
        check(cards == [["Gym", "0", False], ["Lectura", "1", True], ["Musica", "0", False], ["Dieta", "1", False]],
              f"'Este mes' follows the same places, the hidden one dimmed ({cards})")

        await b.js(f"document.querySelector('.day-cell[data-date=\"{LAST_MONTH_DAY}\"]').click()")
        await asyncio.sleep(0.3)
        pop = await b.js("[...document.querySelectorAll('#habitsList .habit-btn')].map(x => [x.dataset.habit, x.classList.contains('is-hidden'), x.classList.contains('completed')])")
        check(pop == [["gym", False, False], ["lectura", True, True], ["musica", False, False], ["dieta", False, True]],
              f"popover: same order, the hidden one marked and dimmed ({pop})")
        await b.shot("month_habits_popover", full=False)

        # Desmarcar su único registro del mes lo saca de la lista de ese mes
        await b.js("document.querySelector('#habitsList .habit-btn[data-habit=\"lectura\"]').click()")
        d = await b.wait_for(f"{DAY}('{LAST_MONTH_DAY}')", lambda v: v is not None and v["dots"] == 3)
        check(d is not None and d["dots"] == 3 and d["active"] == [False, False, True],
              f"unmarking its last record there removes its place ({d})")

        # Seis hábitos: dos filas de 3
        await open_app(b, six)
        d = await b.wait_for(f"{DAY}('{TODAY}')", lambda v: v is not None)
        check(d["dots"] == 6 and d["rows"] == 2, f"six habits: two rows ({d})")
        per_row = await b.js(f"document.querySelector('.day-cell[data-date=\"{TODAY}\"] .habit-dots').style.getPropertyValue('--dots-per-row')")
        check(per_row == "3", f"three per row ({per_row})")
        await b.shot("month_habits_six", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_month_habits():
    asyncio.run(main())
