"""Estimado contra real (épica 24, Fase 4): el campo Estimado del detalle de la
tarjeta, el "de X" en el tablero y la Lista, y la tarjeta del desvío en la
ficha y en Costos (solo con el plan maker)."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import api
from api import call, wait_api
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

ROOT = Path(__file__).resolve().parents[2]
KANBAN = "Revisión de idea para cambiar a kanban"
POMODOROS = "Corrección de Pomodoros"


def grant(email):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_card_estimate.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "maker"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def card(title):
    return (f"[...document.querySelectorAll('.board-card')].find(c => "
            f"c.querySelector('.board-card-title').textContent === {json.dumps(title)})")


def card_time(title):
    return f"({{text: {card(title)}.querySelector('.board-card-time .timer-idle').textContent, over: {card(title)}.querySelector('.board-card-time').classList.contains('over-estimate')}})"


async def main():
    token, _ = seed()
    _, tl = call("GET", "/api/tasks", expect=200)
    by = {t["title"]: t for t in tl["tasks"]}
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def set_estimate(hours, minutes):
        await b.js(f"""(() => {{
            const h = document.getElementById('cardEstimateHours'); h.value = {json.dumps(hours)};
            const m = document.getElementById('cardEstimateMinutes'); m.value = {json.dumps(minutes)};
            m.dispatchEvent(new Event('change'));
        }})()""")

    async def close_card():
        await b.js("document.getElementById('closeCardModalBtn').click()")
        await b.wait_for("document.getElementById('cardModal').classList.contains('hidden')")

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for(f"!!{card(KANBAN)}")

        # Sin el plan maker: el campo está y se guarda (el estimado es de todos)
        await b.js(f"{card(KANBAN)}.click()")
        await b.wait_for("!document.getElementById('cardModal').classList.contains('hidden')")
        empty = await b.js("[document.getElementById('cardEstimateHours').value, document.getElementById('cardEstimateMinutes').value]")
        check(empty == ["", ""], f"a task without an estimate shows the field empty ({empty})")
        await set_estimate("1", "30")
        t = await wait_api("/api/tasks", lambda body: next(x for x in body["tasks"] if x["title"] == KANBAN)["estimate_minutes"] == 90)
        check(next(x for x in t["tasks"] if x["title"] == KANBAN)["estimate_minutes"] == 90,
              "1 h 30 min is saved as 90 minutes, without the maker plan")
        await b.shot("card_estimate_field", full=False)
        await close_card()
        await b.wait_for(f"{card(KANBAN)}.querySelector('.board-card-time').textContent.includes(' de ')")
        st = await b.js(card_time(KANBAN))
        check(st == {"text": "0m de 1h 30m", "over": False}, f"the card says how much of its estimate it took ({st})")

        # Pasado de su estimado: el número en el color de alerta, sin más
        call("PATCH", f"/api/tasks/{by[POMODOROS]['id']}", {"estimate_minutes": 180}, expect=200)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.wait_for(f"!!{card(POMODOROS)}")
        st = await b.js(card_time(POMODOROS))
        color = await b.js(f"[getComputedStyle({card(POMODOROS)}.querySelector('.board-card-time')).color, getComputedStyle(document.documentElement).getPropertyValue('--danger-fg').trim()]")
        check(st["text"].endswith(" de 3h") and st["over"], f"over its estimate, the time turns to the alert color ({st}, {color})")
        check(await b.js(card_time(KANBAN)) == {"text": "0m de 1h 30m", "over": False}, "after reloading the estimate is still there")
        await b.shot("card_estimate_board", full=False)

        # Vaciar el campo lo quita
        await b.js(f"{card(KANBAN)}.click()")
        await b.wait_for("document.getElementById('cardEstimateHours').value === '1'")
        await set_estimate("", "")
        await wait_api("/api/tasks", lambda body: next(x for x in body["tasks"] if x["title"] == KANBAN)["estimate_minutes"] is None)
        await close_card()
        await b.wait_for(f"!{card(KANBAN)}.querySelector('.board-card-time').textContent.includes(' de ')")
        check(await b.js(card_time(KANBAN)) == {"text": "0m", "over": False}, "emptying the field removes the estimate")

        # La Lista dice lo mismo que el tablero
        await b.js("document.querySelector('[data-projects-view=\"list\"]').click()")
        project = "[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent.includes('Habit Tracker'))"
        await b.wait_for(f"!!{project}")
        await b.js(f"{project}.querySelector('.project-toggle').click()")
        row = f"[...document.querySelectorAll('.task-row')].find(r => r.textContent.includes({json.dumps(POMODOROS)}))"
        await b.wait_for(f"!!{row}")
        lst = await b.js(f"({{text: {row}.querySelector('.task-time .timer-idle').textContent, over: {row}.querySelector('.task-time').classList.contains('over-estimate')}})")
        check(lst == st, f"the List shows the same as the card ({lst})")

        # Ficha sin el plan: el "de X" de cada tarea, pero no el desvío
        await b.js(f"{project}.querySelector('.project-main').click()")
        await b.wait_for("document.querySelectorAll('#overviewBody .report-card').length >= 2")
        text = await b.js("document.getElementById('overviewBody').textContent")
        check("de 3h" in text and "Estimado contra real" not in text, "without Maker the overview has the estimate but not the deviation")
        await b.js("document.getElementById('closeOverviewBtn').click()")
        await asyncio.sleep(0.4)

        # Con el plan: estimados para tres tareas terminadas, y la cifra de la API
        grant("yoshi@test.com")
        call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
        _, tl = call("GET", "/api/tasks", expect=200)
        done = [t for t in tl["tasks"] if t["is_done"] and t["seconds"] > 0 and t["title"] != POMODOROS][:2]
        for t in done:
            call("PATCH", f"/api/tasks/{t['id']}", {"estimate_minutes": max(1, t["seconds"] // 60 - 5)}, expect=200)
        _, est = call("GET", "/api/costs/estimates", expect=200)
        ratio = f"{est['overall']['ratio_pct'] / 100:.1f}×"
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.wait_for(f"!!{project}")
        await b.js(f"{project}.querySelector('.project-main').click()")
        await b.wait_for("[...document.querySelectorAll('#overviewBody .report-card-title')].some(t => t.textContent === 'Estimado contra real')")
        text = await b.js("document.getElementById('overviewBody').textContent")
        check(est["overall"]["tasks"] == 3 and ratio in text, f"the overview shows the deviation ({ratio}, {est['overall']})")
        tags = await b.js("[...document.querySelectorAll('#overviewBody .estimate-row')].map(r => [r.querySelector('.estimate-name').textContent, r.querySelector('.estimate-ratio').textContent])")
        check(["documentación", "poco historial"] in tags, f"a tag with fewer than 3 tasks gives no figure ({tags})")
        wide = await b.js("document.documentElement.scrollWidth")
        await b.shot("card_estimate_overview", full=False)
        await b.js("document.getElementById('closeOverviewBtn').click()")
        await asyncio.sleep(0.4)

        # Costos: la misma cifra, de todos los proyectos
        await b.viewport(390, 844, mobile=True)
        await b.js("document.getElementById('tabCosts').click()")
        await b.wait_for("[...document.querySelectorAll('#costsSummary .report-card-title')].some(t => t.textContent === 'Tus estimados')")
        text = await b.js("[...document.querySelectorAll('#costsSummary .report-card')].find(c => c.querySelector('.report-card-title').textContent === 'Tus estimados').textContent")
        check(ratio in text and "3 tareas" in text, f"Costos shows the same figure ({text[:120]})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"no horizontal overflow on a phone ({wide}px)")
        await b.js("window.scrollTo(0, [...document.querySelectorAll('#costsSummary .report-card')].pop().getBoundingClientRect().top + window.scrollY - 80)")
        await asyncio.sleep(0.3)
        await b.shot("card_estimate_costs", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_card_estimate():
    asyncio.run(main())
