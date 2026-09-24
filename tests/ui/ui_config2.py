import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def js(expr, wait=1.0):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    def row_js(container, match):
        return f"""[...document.querySelectorAll('#{container} .config-row')].find(r => r.querySelector('.config-name').value === {json.dumps(match)})"""

    async def set_input(container, match, cls, value):
        await js(f"""(() => {{ const i = {row_js(container, match)}.querySelector('.{cls}'); i.value = {json.dumps(value)}; i.dispatchEvent(new Event('change', {{bubbles: true}})); }})()""")

    def api(path, key):
        _, data = call("GET", path, expect=200)
        return data[key]

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()")
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)

        st = await b.js("({tags: [...document.querySelectorAll('#configTags .config-name')].map(i => i.value), sections: [...document.querySelectorAll('.config-section-title')].map(h => h.textContent.trim().split('\\n')[0])})")
        check(st["tags"] == ["administrativa", "documentación"] and not any("Estados" in s for s in st["sections"]),
              f"Organizar lists tags and has no project-states section ({st})")

        await js("""(() => { const f = document.getElementById('configTagForm'); f.querySelector('input').value = 'examen'; f.requestSubmit(); })()""", wait=1.2)
        await set_input("configTags", "administrativa", "config-name", "admin")
        await set_input("configTags", "admin", "config-color", "#abcdef")
        await js(f"""{row_js('configTags', 'examen')}.querySelector('.config-delete-tag').click()""", wait=0.6)
        await js("document.getElementById('confirmModalConfirmBtn').click()", wait=1.2)
        tags = {t["name"]: t["color"] for t in api("/api/tags", "tags")}
        check(tags == {"admin": "#abcdef", "documentación": "#8e44ad"}, f"tag create / rename / recolor / delete ({tags})")

        await js("document.getElementById('closeBoardConfigBtn').click()", wait=2.0)
        chips = await b.js("[...document.querySelectorAll('.filter-chip')].map(c => c.textContent)")
        check("admin" in chips and "administrativa" not in chips, f"board chips show the renamed tag ({chips})")

        # List view: no state in the summary line, no Estado field in the form
        await js("document.querySelector('[data-projects-view=\"list\"]').click()", wait=0.8)
        meta = await b.js("[...document.querySelectorAll('.project-card')].map(c => c.querySelector('.project-name').textContent + ' | ' + c.querySelector('.project-meta').textContent)")
        check(any(m.startswith("Habit Tracker | 4/5 tareas") for m in meta), f"list summary line has no state ({meta})")
        await js("[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent === 'Habit Tracker').querySelector('.project-main').click()", wait=0.6)
        check(not await b.js("!!document.getElementById('projectStatus')"), "project form has no Estado field")
        await js("document.getElementById('projectName').value = 'Habit Tracker 2'; document.getElementById('projectForm').requestSubmit()", wait=1.5)
        names = [p["name"] for p in api("/api/projects", "projects")]
        check("Habit Tracker 2" in names, "project form still saves")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_config2():
    asyncio.run(main())
