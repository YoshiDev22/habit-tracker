"""Grupos de proyectos (1.34): the Lista and Organizar show each group with its projects
under it, the project form picks the group, and filtering the board by a group
includes its projects."""
import asyncio
import json

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    token, _ = seed()
    _, listing = call("GET", "/api/projects", expect=200)
    ht = next(p for p in listing["projects"] if not p["is_system"])
    _, group = call("POST", "/api/projects", {"name": "Emprendimiento", "color": "#2ecc71"}, expect=201)
    call("PATCH", f"/api/projects/{ht['id']}", {"parent_id": group["id"]}, expect=200)
    _, campaign = call("POST", "/api/projects", {"name": "Campaña", "parent_id": group["id"]}, expect=201)
    _, ad = call("POST", "/api/tasks", {"title": "Anuncio de la campaña", "project_id": campaign["id"]}, expect=201)
    _, loose = call("POST", "/api/projects", {"name": "Suelto"}, expect=201)
    _, own = call("POST", "/api/tasks", {"title": "Tarea suelta", "project_id": loose["id"]}, expect=201)

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/api/health")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.setItem('projects_view', 'list');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for("document.querySelectorAll('#projectsList .project-card').length >= 4")

        # --- Lista: the group, then its projects indented
        cards = await b.js("""[...document.querySelectorAll('#projectsList .project-card')].map(c => ({
            id: Number(c.dataset.projectId), inGroup: c.classList.contains('in-group'),
            group: (c.querySelector('.project-group-meta') || {}).textContent || null}))""")
        ids = [c["id"] for c in cards]
        g = ids.index(group["id"])
        check(sorted(ids[g + 1:g + 3]) == sorted([ht["id"], campaign["id"]])
              and all(c["inGroup"] for c in cards[g + 1:g + 3]) and not cards[g]["inGroup"],
              f"Lista: the group's projects come right under it, indented ({cards})")
        check(cards[g]["group"] and cards[g]["group"].startswith("Grupo · 2 proyectos"),
              f"Lista: the group says how many projects it has ({cards[g]['group']})")
        check(not next(c for c in cards if c["id"] == loose["id"])["inGroup"], "a project without group is not indented")
        await asyncio.sleep(0.6)   # the swipe between tabs ends
        await b.shot("project_groups_list", full=False)

        # --- The form: a member shows its group; a group cannot go into another
        form = await b.js(f"""(() => {{
            openEditProjectModal(projectsState.projects.find(p => p.id === {campaign['id']}));
            const s = document.getElementById('projectParent');
            const member = {{value: s.value, options: [...s.options].map(o => o.value)}};
            hideModal(projectModal);
            openEditProjectModal(projectsState.projects.find(p => p.id === {group['id']}));
            const grp = {{disabled: s.disabled, hint: document.getElementById('projectParentHint').textContent}};
            hideModal(projectModal);
            return {{member, grp}};
        }})()""")
        check(form["member"]["value"] == str(group["id"]), f"form: a project shows its group ({form['member']})")
        check(str(ht["id"]) not in form["member"]["options"] and str(campaign["id"]) not in form["member"]["options"],
              f"form: projects inside a group are not offered as groups ({form['member']['options']})")
        check(form["grp"]["disabled"] and "Es un grupo (2 proyectos)" in form["grp"]["hint"],
              f"form: a group cannot go into another ({form['grp']})")

        # --- Putting a project into the group from the form
        await b.js(f"""(() => {{
            openEditProjectModal(projectsState.projects.find(p => p.id === {loose['id']}));
            document.getElementById('projectParent').value = '{group['id']}';
            document.getElementById('projectForm').requestSubmit();
        }})()""")
        await b.wait_for(f"(projectsState.projects.find(p => p.id === {loose['id']}) || {{}}).parent_id",
                         lambda v: v == group["id"])
        _, saved = call("GET", f"/api/projects/{loose['id']}", expect=200)
        check(saved["parent_id"] == group["id"], f"form: saving puts the project in the group ({saved['parent_id']})")

        # --- Board: filtering by the group includes its projects' cards
        await b.js("document.querySelector('[data-projects-view=board]').click()")
        await asyncio.sleep(1.2)
        shown = await b.js(f"""(() => {{
            boardState.filterProjects.clear();
            boardState.filterProjects.add({group['id']});
            return filteredTasks().map(t => t.id);
        }})()""")
        check(ad["id"] in shown and own["id"] in shown,
              f"board: the group's filter shows its projects' tasks ({ad['id']}, {own['id']} in {shown})")
        chip = await b.js(f"(document.querySelector('[data-filter-project=\"{group['id']}\"]') || {{}}).title || null")
        check(chip and chip.startswith("Grupo: incluye sus 3"), f"board: the group has its chip, with a hint ({chip})")
        await b.js("boardState.filterProjects.clear(); renderBoard()")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_project_groups():
    asyncio.run(main())
