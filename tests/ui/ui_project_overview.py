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
        await b.goto(BASE + "/")
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
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_project_overview():
    asyncio.run(main())
