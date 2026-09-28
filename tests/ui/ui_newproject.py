import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Idea suelta'))"
FORM_OPEN = "!document.getElementById('cardNewProjectForm').classList.contains('hidden')"


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def js(expr, wait=0.8):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    def projects():
        _, pl = call("GET", "/api/projects?include_inactive=true", expect=200)
        return {p["name"]: p for p in pl["projects"]}

    def task(title):
        _, tl = call("GET", "/api/tasks", expect=200)
        return next(t for t in tl["tasks"] if t["title"] == title)

    choose_new = "(() => { const s = document.getElementById('cardProject'); s.value = 'new'; s.dispatchEvent(new Event('change')); })()"

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)

        # From the card detail
        await js(f"{CARD}.click()", wait=1.0)
        last = await b.js("[...document.getElementById('cardProject').options].pop().textContent")
        check(last == "＋ Nuevo proyecto…", f"project select ends with '＋ Nuevo proyecto…' ({last})")
        await js(choose_new, wait=0.4)
        st = await b.js(f"({{open: {FORM_OPEN}, focus: document.activeElement.id, select: document.getElementById('cardProject').selectedOptions[0].textContent}})")
        check(st == {"open": True, "focus": "cardNewProjectName", "select": "Sin asignar"},
              f"choosing it opens the inline form, the select keeps the current project ({st})")
        await js("document.getElementById('cardNewProjectCancel').click()", wait=0.3)
        check(not await b.js(FORM_OPEN), "× closes the form")

        await js(choose_new, wait=0.4)
        await js("document.getElementById('cardNewProjectName').value = 'Tesis'; document.getElementById('cardNewProjectColor').value = '#e67e22'; document.getElementById('cardNewProjectForm').requestSubmit()", wait=1.5)
        p = projects().get("Tesis")
        st = await b.js(f"({{open: {FORM_OPEN}, select: document.getElementById('cardProject').selectedOptions[0].textContent, modal: !document.getElementById('cardModal').classList.contains('hidden')}})")
        check(p is not None and p["color"] == "#e67e22" and task("Idea suelta sin proyecto")["project_id"] == p["id"]
              and st == {"open": False, "select": "Tesis", "modal": True},
              f"Crear makes the project, assigns it to the task, and stays in the card ({st})")
        await b.shot("newproject_card", full=False)

        await js(choose_new, wait=0.4)
        await js("document.getElementById('cardNewProjectName').value = 'Habit Tracker'; document.getElementById('cardNewProjectForm').requestSubmit()", wait=1.2)
        err = await b.js("(() => { const e = document.getElementById('cardNewProjectError'); return e.classList.contains('hidden') ? '' : e.textContent; })()")
        check("Ya existe" in err and await b.js(FORM_OPEN), f"a duplicate name shows the error in place ({err})")
        await js("document.getElementById('closeCardModalBtn').click()", wait=1.5)
        chips = await b.js("[...document.querySelectorAll('.filter-chip')].map(c => c.textContent)")
        check("Tesis" in chips, f"the board filters include the new project ({chips})")

        # From Organizar
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)
        names = await b.js("[...document.querySelectorAll('#configProjects .config-name')].map(i => i.value)")
        check(names == ["Habit Tracker", "Tesis"], f"Organizar lists projects, without 'Sin asignar' ({names})")
        await js("(() => { document.getElementById('configProjectColor').value = '#9b59b6'; const f = document.getElementById('configProjectForm'); f.querySelector('input[type=text]').value = 'Curso Python'; f.requestSubmit(); })()", wait=1.5)
        check(projects().get("Curso Python", {}).get("color") == "#9b59b6", "create a project from Organizar with its colour")
        await js("(() => { const r = [...document.querySelectorAll('#configProjects .config-row')].find(r => r.querySelector('.config-name').value === 'Tesis'); const i = r.querySelector('.config-name'); i.value = 'Tesis 2026'; i.dispatchEvent(new Event('change', {bubbles: true})); })()", wait=1.2)
        check("Tesis 2026" in projects(), "rename a project from Organizar")
        await js("[...document.querySelectorAll('#configProjects .config-row')].find(r => r.querySelector('.config-name').value === 'Curso Python').querySelector('.config-archive-project').click()", wait=1.5)
        check(projects()["Curso Python"]["is_active"] is False, "Archivar archives it")
        names = await b.wait_for("[...document.querySelectorAll('#configProjects .config-name')].map(i => i.value)",
                                 lambda v: v == ["Habit Tracker", "Tesis 2026"])
        check(names == ["Habit Tracker", "Tesis 2026"], f"the archived one leaves the list ({names})")
        archived = await b.js("[...document.querySelectorAll('#configArchivedProjects .config-name')].map(e => e.textContent)")
        check(archived == ["Archivado", "Curso Python"], f"archived projects are listed under 'Archivados' ({archived})")
        await b.shot("newproject_archived", full=False)
        await js("[...document.querySelectorAll('#configArchivedProjects .config-row')].find(r => r.textContent.includes('Curso Python')).querySelector('.config-restore-project').click()", wait=0)
        names = await b.wait_for("[...document.querySelectorAll('#configProjects .config-name')].map(i => i.value)",
                                 lambda v: v == ["Curso Python", "Habit Tracker", "Tesis 2026"])
        check(projects()["Curso Python"]["is_active"] and names == ["Curso Python", "Habit Tracker", "Tesis 2026"]
              and await b.js("[...document.querySelectorAll('#configArchivedProjects .config-name')].map(e => e.textContent)") == ["Archivado"],
              f"Restaurar brings it back to the active list ({names})")
        await js("document.getElementById('closeBoardConfigBtn').click()", wait=1.5)
        await js("document.querySelector('[data-projects-view=\"list\"]').click()", wait=0.8)
        listed = await b.js("[...document.querySelectorAll('.project-card .project-name')].map(e => e.textContent)")
        check("Curso Python" in listed, f"a restored project shows in the list view again ({listed})")
        await js("document.querySelector('[data-projects-view=\"board\"]').click()", wait=0.3)
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)
        width = await b.js("document.querySelector('#configProjectForm input[type=color]').getBoundingClientRect().width")
        check(width <= 40, f"the colour picker keeps its size ({width}px)")
        await b.shot("newproject_config", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_newproject():
    asyncio.run(main())
