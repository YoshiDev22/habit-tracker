"""Grupos de proyectos (1.34), fase 4: the Costos table shows each group as a subtotal
row with its General and its projects indented under it, and the monthly cost report
adds up each group."""
import asyncio
import datetime as dt
import json

import os
import subprocess
import sys
from pathlib import Path

import api
from api import login
from cdp import Browser
from ui_costs import BASE, CLOSE_WELCOME, ROOT

results = []


def grant(email):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_project_groups_costs.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "maker"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    grant("yoshi@test.com")
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    _, projects = api.call("GET", "/api/projects", expect=200)
    ht = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    _, group = api.call("POST", "/api/projects", {"name": "Taller", "color": "#2ecc71"}, expect=201)
    api.call("PATCH", f"/api/projects/{ht['id']}", {"parent_id": group["id"]}, expect=200)
    _, loose = api.call("POST", "/api/projects", {"name": "Suelto"}, expect=201)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = cats["categories"][0]["id"]
    today = dt.date.today().isoformat()

    def cost(project_id, concept, cents):
        api.call("POST", "/api/costs", {"project_id": project_id, "category_id": cat, "cost_date": today,
                                         "concept": concept, "quantity": 1, "unit_cost_cents": cents}, expect=201)

    cost(group["id"], "Filamento", 30000)
    cost(ht["id"], "Dominio", 25000)
    cost(loose["id"], "Otro", 1000)

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/api/health")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('last_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabCosts').click()")
        rows_js = """[...document.querySelectorAll('.costs-projects tbody tr')].map(r => ({
            id: r.dataset.projectId ? Number(r.dataset.projectId) : null,
            group: r.classList.contains('costs-group-row'), child: r.classList.contains('in-group'),
            name: r.querySelector('.costs-project-name').textContent,
            cost: r.children[4].textContent}))"""
        rows = await b.wait_for(rows_js, lambda v: v and any(r["group"] for r in v))
        g = next(i for i, r in enumerate(rows) if r["group"])
        check(rows[g]["id"] is None and rows[g]["name"].startswith("Taller") and "$550.00" in rows[g]["cost"],
              f"Costos: the group's subtotal row adds its General and its projects ({rows[g]})")
        under = rows[g + 1:g + 3]
        check([r["id"] for r in under] == [group["id"], ht["id"]] and all(r["child"] for r in under)
              and under[0]["name"].startswith("General"),
              f"Costos: General first, then its projects, indented ({under})")
        check(any(r["id"] == loose["id"] and not r["child"] for r in rows), "Costos: a loose project stays as is")
        await asyncio.sleep(0.8)   # the swipe between tabs ends
        await b.shot("project_groups_costs", full=False)

        # Touching the subtotal row does nothing; General is the group itself, for its own costs
        await b.js("document.querySelector('.costs-group-row').click()")
        await asyncio.sleep(0.4)
        await b.js(f"document.querySelector('.costs-projects tr[data-project-id=\"{group['id']}\"]').click()")
        chosen = await b.wait_for("costsState.projectId", lambda v: v == group["id"])
        check(chosen == group["id"], f"Costos: General opens the group's own costs ({chosen})")

        # The monthly cost report: "Por grupo" and each project with its group
        _, rep = api.call("POST", "/api/reports", {"kind": "costs-month",
                                                   "period_start": dt.date.today().replace(day=1).isoformat(),
                                                   "today": today}, expect=200)
        saved = await b.js(f"""(async () => {{
            const report = await apiFetch('/api/reports/{rep['id']}');
            const card = costsBreakdown(report, 'MXN');
            const titles = [...card.querySelectorAll('.saved-chart-title')].map(t => t.textContent);
            const names = [...costsProjectsTable(report.metrics).querySelectorAll('tbody th')].map(t => t.textContent);
            return {{titles, names}};
        }})()""")
        check("Por grupo" in saved["titles"], f"cost report: a 'Por grupo' list ({saved['titles']})")
        check("Habit Tracker (Taller)" in saved["names"] and "Taller (general del grupo)" in saved["names"],
              f"cost report: each project says its group ({saved['names']})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_project_groups_costs():
    asyncio.run(main())
