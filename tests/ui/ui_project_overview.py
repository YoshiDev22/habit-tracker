"""Ficha de proyecto (épica 24, Fase 1): desde la Lista y desde Organizar."""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
OPEN = "!document.getElementById('projectOverviewModal').classList.contains('hidden')"
STATE = """({title: document.getElementById('overviewTitle').textContent,
    stats: [...document.querySelectorAll('#overviewBody .report-stat-value, #overviewBody .report-stats > * > :first-child')].map(e => e.textContent),
    cards: [...document.querySelectorAll('#overviewBody .report-card-title')].map(e => e.textContent),
    taskRows: document.querySelectorAll('#overviewBody .report-card:nth-of-type(2) .report-bar-row').length,
    edit: !document.getElementById('overviewEditBtn').hidden})"""


def fmt(seconds):
    hours, minutes = seconds // 3600, seconds % 3600 // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, summ = api.call("GET", "/api/projects/summary", expect=200)
    ht = next(s for s in summ["summaries"] if s["name"] == "Habit Tracker")
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/api/health")   # mismo origen, sin arrancar la app
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.setItem('projects_view', 'list');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for("document.querySelectorAll('.project-card').length > 0")

        # Desde la Lista: tocar el proyecto abre su ficha, con el total de la Lista
        await b.js("[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent.includes('Habit Tracker')).querySelector('.project-main').click()")
        await b.wait_for("document.querySelectorAll('#overviewBody .report-card').length >= 2")
        st = await b.js(STATE)
        text = await b.js("document.getElementById('overviewBody').textContent")
        check(await b.js(OPEN) and "Habit Tracker" in st["title"], f"tapping the project opens its overview ({st['title']})")
        check(fmt(ht["total_seconds"]) in text, f"same total as the List ({fmt(ht['total_seconds'])})")
        check(f"{ht['task_done']} de {ht['task_total']}" in text, "done vs total tasks")
        check("Por tarea" in st["cards"], f"time per task ({st['cards']})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"no horizontal overflow on a phone ({wide}px)")
        await b.shot("project_overview_mobile", full=False)

        # ✎ Editar lleva al formulario del proyecto
        check(st["edit"], "an active project can be edited from its overview")
        await b.js("document.getElementById('overviewEditBtn').click()")
        await asyncio.sleep(0.5)
        st = await b.js("({overview: " + OPEN + ", form: !document.getElementById('projectModal').classList.contains('hidden'),"
                        " name: document.getElementById('projectName').value})")
        check(not st["overview"] and st["form"] and st["name"] == "Habit Tracker", f"Editar opens the project form ({st})")
        await b.js("document.getElementById('closeProjectModalBtn').click()")
        await asyncio.sleep(0.4)

        # Desde Organizar, encima de ese modal; Escape cierra solo la ficha
        await b.viewport(1280, 900)
        await b.js("document.querySelector('[data-projects-view=\"board\"]').click()")
        await asyncio.sleep(0.6)
        await b.js("document.getElementById('boardConfigBtn').click()")
        await b.wait_for("document.querySelectorAll('.config-overview-project').length > 0")
        await b.js("document.querySelector('.config-overview-project').click()")
        await b.wait_for("document.querySelectorAll('#overviewBody .report-card').length >= 1")
        on_top = await b.js("""(() => {
            const r = document.querySelector('#projectOverviewModal .modal-content').getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 20);
            return !!hit && !!hit.closest('#projectOverviewModal');
        })()""")
        check(on_top, "the overview opens on top of Organizar")
        await b.shot("project_overview_desktop", full=False)
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        await asyncio.sleep(0.4)
        st = await b.js("({overview: " + OPEN + ", config: !document.getElementById('boardConfigModal').classList.contains('hidden')})")
        check(st == {"overview": False, "config": True}, f"Escape closes only the overview ({st})")

        # Desde Organizar también se edita (ahí se elige el grupo): el formulario
        # sale encima, Escape cierra solo él, y guardar repinta Organizar
        await b.js("document.querySelector('.config-overview-project').click()")
        await b.wait_for("!document.getElementById('overviewEditBtn').hidden")
        await b.js("document.getElementById('overviewEditBtn').click()")
        await b.wait_for("!document.getElementById('projectModal').classList.contains('hidden')")
        on_top = await b.js("""(() => {
            const r = document.querySelector('#projectModal .modal-content').getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 20);
            return !!hit && !!hit.closest('#projectModal');
        })()""")
        check(on_top, "Editar from Organizar opens the project form on top of it")
        check(await b.js("!document.getElementById('projectParentGroup').hidden"),
              "the form opened from Organizar offers Grupo")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        await asyncio.sleep(0.4)
        st = await b.js("({form: !document.getElementById('projectModal').classList.contains('hidden'),"
                        " config: !document.getElementById('boardConfigModal').classList.contains('hidden')})")
        check(st == {"form": False, "config": True}, f"Escape closes only the project form ({st})")

        # Meter un proyecto en un grupo desde Organizar: la fila queda dentro
        await b.js("apiFetch('/api/projects', {method: 'POST', json: {name: 'Grupo UI', color: '#3498db'}})"
                   ".then(() => loadProjects())")
        await b.wait_for("document.querySelectorAll('#configProjects .config-row').length >= 2")
        rows = await b.js("[...document.querySelectorAll('#configProjects .config-row')].map(r => r.dataset.itemId)")
        check(len(rows) >= 2, f"Organizar lists the new project too ({rows})")
        if len(rows) >= 2:
            child_id, group_id = rows[0], rows[1]
            await b.js(f"document.querySelector('#configProjects .config-row[data-item-id=\"{child_id}\"] .config-overview-project').click()")
            await b.wait_for("!document.getElementById('overviewEditBtn').hidden")
            await b.js("document.getElementById('overviewEditBtn').click()")
            await b.wait_for("!document.getElementById('projectModal').classList.contains('hidden')")
            await b.js(f"document.getElementById('projectParent').value = '{group_id}'")
            await b.js("document.getElementById('saveProjectBtn').click()")
            await b.wait_for("document.getElementById('projectModal').classList.contains('hidden')")
            await b.wait_for(f"!!document.querySelector('#configProjects .config-row.in-group[data-item-id=\"{child_id}\"]')")
            st = await b.js(f"!!document.querySelector('#configProjects .config-row.in-group[data-item-id=\"{child_id}\"]')")
            check(st, "a project put in a group from Organizar shows inside it there")
            await b.js(f"apiFetch('/api/projects/{child_id}', {{method: 'PATCH', json: {{parent_id: null}}}}).then(() => loadProjects())")
            await asyncio.sleep(0.6)
        await b.js("document.getElementById('closeBoardConfigBtn').click()")
        await asyncio.sleep(0.6)

        # Desde una tarjeta del Tablero: 📊 junto al proyecto, encima del detalle
        await b.wait_for("document.querySelectorAll('.board-card').length > 0")
        await b.js("document.querySelector('.board-card').click()")
        await b.wait_for("!document.getElementById('cardModal').classList.contains('hidden')")
        project_name = await b.js("document.getElementById('cardProject').selectedOptions[0].textContent")
        await b.js("document.getElementById('cardProjectOverviewBtn').click()")
        await b.wait_for("document.querySelectorAll('#overviewBody .report-card').length >= 1")
        st = await b.js("""({title: document.getElementById('overviewTitle').textContent,
            edit: !document.getElementById('overviewEditBtn').hidden})""")
        check(project_name in st["title"] and st["edit"],
              f"the card's 📊 opens its project's overview, with Editar ({project_name}, {st})")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        await asyncio.sleep(0.4)
        st = await b.js("({overview: " + OPEN + ", card: !document.getElementById('cardModal').classList.contains('hidden')})")
        check(st == {"overview": False, "card": True}, f"closing it leaves the card open ({st})")

        # ✎ Editar desde la tarjeta: el formulario encima de ella; cerrarlo la deja abierta
        await b.js("document.getElementById('cardProjectOverviewBtn').click()")
        await b.wait_for("!document.getElementById('overviewEditBtn').hidden")
        await b.js("document.getElementById('overviewEditBtn').click()")
        await b.wait_for("!document.getElementById('projectModal').classList.contains('hidden')")
        on_top = await b.js("""(() => {
            const r = document.querySelector('#projectModal .modal-content').getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + 20);
            return !!hit && !!hit.closest('#projectModal');
        })()""")
        check(on_top, "Editar from the card opens the project form on top of it")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        await asyncio.sleep(0.4)
        st = await b.js("({form: !document.getElementById('projectModal').classList.contains('hidden'),"
                        " card: !document.getElementById('cardModal').classList.contains('hidden')})")
        check(st == {"form": False, "card": True}, f"Escape closes only the project form ({st})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_project_overview():
    asyncio.run(main())
