"""Grupos de proyectos (1.34): the Lista and Organizar show each group with its projects
under it, the project form picks the group, and filtering the board by a group
includes its projects."""
import asyncio
import csv
import datetime as dt
import io
import json

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []
LOCAL_OFFSET_H = round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600)
YESTERDAY = dt.date.today() - dt.timedelta(days=1)


def log(project_id, task_id, hour, minutes):
    """Time yesterday, like the fixture's"""
    start = dt.datetime.combine(YESTERDAY, dt.time(hour)) - dt.timedelta(hours=LOCAL_OFFSET_H)
    call("POST", "/api/pomodoro", {
        "project_id": project_id, "task_id": task_id, "session_date": YESTERDAY.isoformat(),
        "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=minutes)).isoformat(),
        "duration_seconds": minutes * 60, "planned_seconds": 0, "mode": "focus",
        "was_completed": True, "source": "manual"}, expect=201)


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
    # Reportes: time in the group itself (its "General"), in a member and in a loose project
    _, other = call("POST", "/api/projects", {"name": "Otro suelto"}, expect=201)
    log(group["id"], None, 5, 30)
    log(campaign["id"], ad["id"], 6, 60)
    log(other["id"], None, 7, 45)

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

        # --- Card: project and subproject from the card itself
        await b.js(f"openCardModal({ad['id']})")
        await b.wait_for("!document.getElementById('cardModal').classList.contains('hidden')")
        opts = await b.js("[...document.getElementById('cardProject').options].map(o => o.textContent)")
        gi = opts.index("Emprendimiento") if "Emprendimiento" in opts else -1
        check(gi >= 0 and any(o.endswith("↳ Campaña") for o in opts[gi + 1:gi + 4]),
              f"card: the Proyecto select lists each subproject under its group ({opts})")
        await b.js("const s = document.getElementById('cardProject'); s.value = 'new';"
                   " s.dispatchEvent(new Event('change', {bubbles: true}))")
        await b.wait_for("!document.getElementById('cardNewProjectForm').classList.contains('hidden')")
        preset = await b.js("document.getElementById('cardNewProjectParent').value")
        check(preset == str(group["id"]), f"card: a new project starts inside the task's group ({preset})")
        await b.js("document.getElementById('cardNewProjectName').value = 'Landing'")
        await b.js("document.getElementById('cardNewProjectForm').requestSubmit()")
        await b.wait_for("document.getElementById('cardNewProjectForm').classList.contains('hidden')")
        await asyncio.sleep(0.6)
        _, projs = call("GET", "/api/projects", expect=200)
        landing = next((p for p in projs["projects"] if p["name"] == "Landing"), None)
        check(landing and landing["parent_id"] == group["id"],
              f"card: the new subproject is inside the group ({landing})")
        task_project = await b.js(f"boardState.tasks.find(t => t.id === {ad['id']}).project_id")
        check(landing and task_project == landing["id"],
              f"card: the task goes to the new subproject ({task_project})")
        call("PATCH", f"/api/tasks/{ad['id']}", {"project_id": campaign["id"]}, expect=200)
        await b.js("closeCardModal()")
        await asyncio.sleep(0.4)

        # --- Reportes: the group with its subtotal and its projects under it
        await b.js("goToView('reports')")
        await asyncio.sleep(0.6)
        await b.js(f"setRange('custom', dateFromKey('{YESTERDAY}'), dateFromKey('{YESTERDAY}'))")
        card_js = """(() => {
            const card = [...document.querySelectorAll('.report-card')]
                .find(c => c.querySelector('.report-card-title').textContent === 'Por proyecto');
            return card ? [...card.querySelectorAll('.report-bar-row')].map(r => ({
                name: r.querySelector('.report-bar-name').firstChild.nextSibling.textContent,
                group: r.classList.contains('is-group'), child: r.classList.contains('in-group')})) : null;
        })()"""
        rows = await b.wait_for(card_js, lambda v: v and any(r["group"] for r in v))
        g = next(i for i, r in enumerate(rows) if r["group"])
        children = []
        for r in rows[g + 1:]:
            if not r["child"]:
                break
            children.append(r["name"])
        check(rows[g]["name"] == "Emprendimiento" and "General" in children and "Campaña" in children
              and ht["name"] in children, f"Reportes: the group, then General and its projects indented ({rows})")
        check(any(r["name"] == "Otro suelto" and not r["child"] for r in rows), "Reportes: a loose project stays as is")
        await b.js("""(() => {
            const card = [...document.querySelectorAll('.report-card')]
                .find(c => c.querySelector('.report-card-title').textContent === 'Por proyecto');
            window.scrollTo(0, card.getBoundingClientRect().top + window.scrollY - 20);
        })()""")
        await asyncio.sleep(0.3)
        await b.shot("project_groups_reports", full=False)

        # Copiar para IA: the group table adds up with the project table and the total
        ai = await b.js(r"""(async () => {
            const text = buildAiSummary(await fetchReportData());
            const table = title => {
                const part = (text.split(`### ${title}\n`)[1] || '').split('\n#')[0];
                return part.split('\n').filter(l => /^\| (?!---|Grupo \||Proyecto \|)/.test(l))
                    .map(l => l.split('|').slice(1, -1).map(c => c.trim()));
            };
            return {total: Number(text.match(/- Total: .* \((\d+) min\)/)[1]),
                    groups: table('Por grupo'), projects: table('Por proyecto')};
        })()""")
        grp = next((r for r in ai["groups"] if r[0] == "Emprendimiento"), None)
        mine = [r for r in ai["projects"] if r[1] == "Emprendimiento"]
        check(grp is not None and int(grp[1]) == sum(int(r[2]) for r in mine) and "General" in grp[3],
              f"Copiar para IA: the group's subtotal is the sum of its rows ({grp}, {mine})")
        check(sum(int(r[2]) for r in ai["projects"]) == ai["total"]
              and sum(int(r[3]) for r in ai["projects"]) == 100
              and any(r[0] == "General (del grupo)" for r in mine),
              f"Copiar para IA: projects still add up to the total and 100 % ({ai['projects']})")

        # The saved report: "Por grupo" under the donuts, with what made each group
        monday = YESTERDAY - dt.timedelta(days=YESTERDAY.weekday())
        _, rep = call("POST", "/api/reports", {"kind": "week", "period_start": monday.isoformat(),
                                               "today": dt.date.today().isoformat()})
        saved = await b.js(f"""(async () => {{
            const card = whereTimeWent(await apiFetch('/api/reports/{rep['id']}'));
            const titles = [...card.querySelectorAll('.saved-chart-title')].map(t => t.textContent);
            const list = card.querySelectorAll('.report-bars')[0];
            const row = list && list.querySelector('.report-bar-row');
            return {{titles, name: row && row.querySelector('.report-bar-name').textContent}};
        }})()""")
        check("Por grupo" in saved["titles"] and saved["name"].startswith("Emprendimiento")
              and "Campaña" in saved["name"] and "general" in saved["name"],
              f"saved report: the group with its projects ({saved})")

        # CSV: the Grupo column
        await b.js("window.__csv = null; downloadText = (name, text, type) => { window.__csv = {name, text, type}; };")
        await b.js("document.getElementById('reportsExport').click()")
        got = await b.wait_for("window.__csv", lambda v: v)
        rows = list(csv.reader(io.StringIO(got["text"].lstrip("\ufeff"))))
        col = rows[0].index("Grupo")
        by_project = {r[6]: r[col] for r in rows[1:]}
        check(rows[0][col - 1] == "Proyecto" and by_project.get("Campaña") == "Emprendimiento"
              and by_project.get("Emprendimiento") == "Emprendimiento" and by_project.get("Otro suelto") == "",
              f"CSV: each row says its group ({by_project})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_project_groups():
    asyncio.run(main())
