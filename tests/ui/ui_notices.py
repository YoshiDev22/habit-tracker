"""La campanita de avisos: sesiones por confirmar (épica 30, Fase 2)."""
import asyncio
import datetime as dt
import json

import api
from api import call, wait_api
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

AUTOCLOSE = "Cerrado automáticamente a las 8 h"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    token, _ = seed()
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if not t["is_done"])
    today = dt.date.today()

    def capped(days_ago):
        start = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0) - dt.timedelta(days=days_ago, hours=9)
        _, s = call("POST", "/api/pomodoro", {
            "project_id": task["project_id"], "task_id": task["id"],
            "session_date": (today - dt.timedelta(days=days_ago)).isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(hours=8)).isoformat(),
            "duration_seconds": 8 * 3600, "planned_seconds": 0, "mode": "focus", "was_completed": True,
            "source": "stopwatch", "note": AUTOCLOSE, "needs_review": True}, expect=201)
        return s

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        st = await b.js("({shown: document.getElementById('bellBtn').offsetWidth > 0, count: document.getElementById('bellCount').hidden})")
        check(st == {"shown": True, "count": True}, f"the bell is always there, without a number when nothing is pending ({st})")

        first = capped(0)
        second = capped(1)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.wait_for("!document.getElementById('bellCount').hidden")
        count = await b.js("document.getElementById('bellCount').textContent")
        check(count == "2", f"the bell counts the sessions to review ({count})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"the bar still fits a phone ({wide}px)")
        await b.shot("notices_bar", full=False)

        # Reportes dice que está contando tiempo sin confirmar
        await b.js("document.getElementById('tabReports').click()")
        await b.wait_for("!!document.querySelector('.report-review-note')")
        note = await b.js("document.querySelector('.report-review-note').textContent")
        check("sin confirmar" in note and "8h" in note.replace(" ", ""), f"Reportes mentions the unconfirmed time ({note})")

        # La lista: "Está bien" confirma la segunda tal cual
        await b.js("document.getElementById('bellBtn').click()")
        await b.wait_for("document.querySelectorAll('.notice-item').length === 2")
        text = await b.js("document.getElementById('noticesList').textContent")
        check(task["title"] in text and "8h" in text.replace(" ", ""), f"each notice names the task and the 8 h ({text[:120]})")
        await b.shot("notices_list", full=False)
        await b.js(f"document.querySelector('.notice-item[data-session-id=\"{second['id']}\"] .notice-ok').click()")
        await wait_api("/api/pomodoro/review", lambda body: body["total"] == 1)
        await b.wait_for("document.getElementById('bellCount').textContent === '1'")
        _, s2 = call("GET", f"/api/pomodoro?task_id={task['id']}", expect=200)
        kept = next(s for s in s2["sessions"] if s["id"] == second["id"])
        check(kept["needs_review"] is False and kept["duration_seconds"] == 8 * 3600, "'Está bien' confirms it as 8 h")

        # "Corregir" abre el registro a mano encima; guardar 3 h la confirma
        await b.js(f"document.querySelector('.notice-item[data-session-id=\"{first['id']}\"] .notice-fix').click()")
        await b.wait_for("!document.getElementById('logTimeModal').classList.contains('hidden')")
        # Guardar se habilita cuando llegan las tareas (si no, perdía su tarea)
        await b.wait_for("!document.querySelector('#logTimeForm button[type=submit]').disabled")
        await b.js("""(() => {
            const h = document.getElementById('logTimeHours'); h.value = '3'; h.dispatchEvent(new Event('input', {bubbles: true}));
            const m = document.getElementById('logTimeMinutes'); m.value = '0'; m.dispatchEvent(new Event('input', {bubbles: true}));
            document.getElementById('logTimeForm').requestSubmit();
        })()""")
        await wait_api("/api/pomodoro/review", lambda body: body["total"] == 0)
        await b.wait_for("document.getElementById('bellCount').hidden")
        _, s1 = call("GET", "/api/pomodoro", expect=200)
        fixed = next(s for s in s1["sessions"] if s["id"] == first["id"])
        check(fixed["needs_review"] is False and fixed["duration_seconds"] == 3 * 3600 and fixed["task_id"] == task["id"],
              f"correcting it saves the real time, keeps its task and clears the notice ({fixed['duration_seconds']}, {fixed['task_id']})")
        # Desde la 1.26 lo resuelto queda en "Hechos", y ya no cuenta en el círculo
        listed = await b.js("document.getElementById('noticesList').textContent")
        check("Pendientes" not in listed and listed.count("Registro de tiempo confirmado") == 2
              and await b.js("document.getElementById('bellCount').hidden"),
              f"both move to Hechos and the bell has no number ({listed[:80]})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_notices():
    asyncio.run(main())
