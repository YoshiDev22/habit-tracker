import asyncio
import json
import sys
from datetime import date, datetime, timedelta, timezone

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

H = 3600


def log(project_id, task_id, secs):
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)
    call("POST", "/api/pomodoro", {
        "project_id": project_id, "task_id": task_id, "session_date": date.today().isoformat(),
        "started_at": (now - timedelta(seconds=secs)).isoformat(), "ended_at": now.isoformat(),
        "duration_seconds": secs, "mode": "focus",
    }, expect=201)


def totals():
    _, s = call("GET", "/api/projects/summary", expect=200)
    return {x["name"]: x["total_seconds"] for x in s["summaries"]}


async def main():
    token, col = seed()
    _, curso = call("POST", "/api/projects", {"name": "Curso"}, expect=201)
    _, t1 = call("POST", "/api/tasks", {"project_id": curso["id"], "title": "Cap 1"}, expect=201)
    log(curso["id"], t1["id"], H)
    _, desc = call("POST", "/api/projects", {"name": "Descartado"}, expect=201)
    _, t2 = call("POST", "/api/tasks", {"project_id": desc["id"], "title": "Idea mala"}, expect=201)
    log(desc["id"], t2["id"], 2 * H)
    call("POST", "/api/projects", {"name": "Temporal"}, expect=201)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def js(expr, wait=0.6):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    def card(name):
        return f"[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent === {json.dumps(name)})"

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.setItem('projects_view', 'list');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)

        menus = await b.js(f"({{sin: getComputedStyle({card('Sin asignar')}.querySelector('.project-menu')).visibility, ht: getComputedStyle({card('Habit Tracker')}.querySelector('.project-menu')).visibility}})")
        check(menus == {"sin": "hidden", "ht": "visible"}, f"Sin asignar has no ⋯ menu ({menus})")

        # Row at the very bottom of the window: the menu must open upward
        await js(f"{card('Temporal')}.scrollIntoView({{block: 'end'}})", wait=0.4)
        await js(f"{card('Temporal')}.querySelector('.project-menu').click()")
        m = await b.js("(() => { const m = document.querySelector('.project-menu-popover'); const r = m.getBoundingClientRect(); return {open: !m.classList.contains('hidden'), items: [...m.querySelectorAll('button')].map(b => b.textContent.trim()), inView: r.right <= innerWidth && r.left >= 0 && r.top >= 0 && r.bottom <= innerHeight}; })()")
        check(m["open"] and m["items"] == ["📦 Archivar", "🗑️ Eliminar…"] and m["inView"], f"⋯ opens a small menu ({m})")
        await b.shot("menu_open", full=False)
        await js("document.querySelector('.app-brand').click()")
        check(await b.js("document.querySelector('.project-menu-popover').classList.contains('hidden')"), "clicking outside closes the menu")

        await js(f"{card('Temporal')}.querySelector('.project-menu').click()")
        await js("document.querySelector('[data-project-action=\"archive\"]').click()", wait=1.5)
        _, pl = call("GET", "/api/projects?include_inactive=true", expect=200)
        tmp = next(p for p in pl["projects"] if p["name"] == "Temporal")
        gone = await b.js(f"!{card('Temporal')}")
        check(not tmp["is_active"] and gone, "Archivar hides the project, no confirm needed")

        # Delete keeping time
        await js(f"{card('Curso')}.querySelector('.project-menu').click()")
        await js("document.querySelector('[data-project-action=\"delete\"]').click()")
        d = await b.js("({title: document.getElementById('projectDeleteTitle').textContent, msg: document.getElementById('projectDeleteMessage').textContent, opt: document.getElementById('projectDeleteTimeLabel').textContent, btn: document.getElementById('confirmProjectDeleteBtn').textContent})")
        check(d == {"title": '¿Eliminar "Curso"?', "msg": "Su tarea y su tiempo pasarán a Sin asignar.",
                    "opt": "Borrar también su tiempo registrado (1h 0m)", "btn": "Eliminar"}, f"delete confirm explains what happens ({d})")
        await js("(() => { const c = document.getElementById('projectDeleteTime'); c.checked = true; c.dispatchEvent(new Event('change')); })()", wait=0.2)
        btn = await b.js("document.getElementById('confirmProjectDeleteBtn').textContent")
        await b.shot("delete_confirm", full=False)
        await js("(() => { const c = document.getElementById('projectDeleteTime'); c.checked = false; c.dispatchEvent(new Event('change')); })()", wait=0.2)
        check(btn == "Eliminar proyecto y tiempo", "ticking the box renames the button")
        before = totals()["Sin asignar"]
        await js("document.getElementById('confirmProjectDeleteBtn').click()", wait=1.5)
        _, tl = call("GET", "/api/tasks", expect=200)
        moved = next(t for t in tl["tasks"] if t["title"] == "Cap 1")
        un = next(p for p in pl["projects"] if p["is_system"])
        check(moved["project_id"] == un["id"] and totals()["Sin asignar"] == before + H, "default delete: task and 1h move to Sin asignar")

        # Cancel
        await js(f"{card('Descartado')}.querySelector('.project-menu').click()")
        await js("document.querySelector('[data-project-action=\"delete\"]').click()")
        await js("document.getElementById('cancelProjectDeleteBtn').click()", wait=0.8)
        check("Descartado" in totals(), "Cancelar keeps the project")

        # Delete with its time
        await js(f"{card('Descartado')}.querySelector('.project-menu').click()")
        await js("document.querySelector('[data-project-action=\"delete\"]').click()")
        before = totals()["Sin asignar"]
        await js("(() => { const c = document.getElementById('projectDeleteTime'); c.checked = true; c.dispatchEvent(new Event('change')); })()", wait=0.2)
        await js("document.getElementById('confirmProjectDeleteBtn').click()", wait=1.5)
        _, tl = call("GET", "/api/tasks", expect=200)
        kept = next(t for t in tl["tasks"] if t["title"] == "Idea mala")
        check("Descartado" not in totals() and kept["project_id"] == un["id"] and totals()["Sin asignar"] == before,
              "delete with time: task kept in Sin asignar, its 2h removed")
        sin = await b.js(f"{card('Sin asignar')}.querySelector('.project-meta').textContent")
        check("4 tareas" in sin, f"list refreshed: Sin asignar now has the moved tasks ({sin})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_delete():
    asyncio.run(main())
