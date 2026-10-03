"""Plan maker (épica 24, Fase 2): la casilla en Mi perfil y el costeo en la ficha."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import api
from api import login, wait_api
from cdp import Browser

BASE = api.BASE
ROOT = Path(__file__).resolve().parents[2]
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
MAKER_SHOWN = "!document.getElementById('moduleMakerOption').hidden"


def grant(email):
    """scripts/grant_module.py contra la base de esta prueba (conftest: <nombre>.db)."""
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_maker.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "maker"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, projects = api.call("GET", "/api/projects", expect=200)
    ht = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    _, summ = api.call("GET", "/api/projects/summary", expect=200)
    seconds = next(s for s in summ["summaries"] if s["project_id"] == ht["id"])["total_seconds"]
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def open_profile():
        # Los módulos viven en ⚙️ Configuración
        await b.js("openSettings('modules')")
        await b.wait_for("!document.getElementById('habitsSetupModal').classList.contains('hidden')")

    async def open_overview():
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for("document.querySelectorAll('.project-card').length > 0")
        await b.js("[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent.includes('Habit Tracker')).querySelector('.project-main').click()")
        await b.wait_for("document.querySelectorAll('#overviewBody .report-card').length >= 2")

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.setItem('projects_view', 'list');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Sin acceso: ni la casilla ni el costeo
        await open_profile()
        check(not await b.js(MAKER_SHOWN), "no Maker checkbox without access")
        check(await b.js("document.getElementById('planBadge').hidden"), "no MKR badge without the plan")
        await b.js("document.getElementById('settingsClose').click()")
        await open_overview()
        check(not await b.js("!!document.querySelector('.costing-card')"), "no costing in the overview without the plan")
        await b.js("document.getElementById('closeOverviewBtn').click()")

        # Con acceso: aparece la casilla; al encenderla, el costeo
        grant("yoshi@test.com")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await open_profile()
        st = await b.js(f"({{shown: {MAKER_SHOWN}, checked: document.getElementById('moduleMaker').checked}})")
        check(st == {"shown": True, "checked": False}, f"with access the checkbox shows, off ({st})")
        await b.js("document.getElementById('moduleMaker').click()")
        me = await wait_api("/api/auth/me", lambda body: body["modules"]["maker"]["enabled"])
        check(me["modules"]["maker"]["enabled"], "turning it on is saved in the account")
        await b.wait_for("!document.getElementById('moduleStatus').hidden")
        status = await b.js("document.getElementById('moduleStatus').textContent")
        check("ficha de un proyecto" in status, f"Configuración says where the new feature is ({status})")
        await b.js("document.getElementById('settingsClose').click()")
        await asyncio.sleep(0.3)

        # La etiqueta MKR, pegada al nombre y un poco abajo (subíndice)
        st = await b.js("""(() => {
            const badge = document.getElementById('planBadge');
            const name = document.getElementById('userEmail').getBoundingClientRect();
            const r = badge.getBoundingClientRect();
            return {shown: !badge.hidden && r.width > 0, text: badge.textContent,
                    gap: Math.round(r.left - name.right), lower: r.bottom > name.bottom};
        })()""")
        check(st["shown"] and st["text"] == "MKR" and 0 <= st["gap"] <= 6 and st["lower"],
              f"MKR badge right after the name, as a subscript ({st})")
        await b.viewport(1280, 800)
        await b.shot("maker_badge_light", full=False)
        await b.js("document.documentElement.setAttribute('data-theme', 'dark')")
        await asyncio.sleep(0.2)
        await b.shot("maker_badge_dark", full=False)
        await b.js("document.documentElement.setAttribute('data-theme', 'light')")
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        check(not await b.js("document.getElementById('planBadge').hidden"), "the badge is there after a reload")

        await open_overview()
        check(await b.js("!!document.querySelector('.costing-card')"), "the overview now has Costeo")
        check(await b.js("document.querySelector('.costing-badge').hidden"), "not a quote: it already has time")

        # Tarifa: se guarda al cambiar y calcula la mano de obra
        await b.js("""(() => {
            const input = document.querySelector('.costing-card [data-field="hourly_rate_cents"]');
            input.value = '350'; input.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        expected = round(seconds * 35000 / 3600)
        fin = await wait_api(f"/api/projects/{ht['id']}/finance", lambda body: body["hourly_rate_cents"] == 35000)
        check(fin["labor_cents"] == expected, f"rate saved, labor computed ({fin['labor_cents']} == {expected})")
        await b.wait_for("document.querySelector('.costing-labor') !== null")
        labor = await b.js("document.querySelector('.costing-labor').textContent")
        shown = f"{expected / 100:,.2f}"
        check(shown in labor and "mano de obra" in labor, f"the overview shows it ({labor})")

        # Moneda y presupuesto en horas
        await b.js("""(() => {
            const c = document.querySelector('.costing-card [data-field="currency"]');
            c.value = 'USD'; c.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        await wait_api(f"/api/projects/{ht['id']}/finance", lambda body: body["currency"] == "USD")
        await b.js("""(() => {
            const h = document.querySelector('.costing-card [data-field="budget_minutes"]');
            h.value = '10'; h.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        fin = await wait_api(f"/api/projects/{ht['id']}/finance", lambda body: body["budget_minutes"] == 600)
        await b.wait_for("document.querySelectorAll('.costing-result .report-bar-row').length === 1")
        bar = await b.js("document.querySelector('.costing-result .report-bar-row').textContent")
        check(fin["currency"] == "USD" and f"{fin['budget_time_pct']} %" in bar, f"budget in hours shows its progress ({bar})")
        labor = await b.js("document.querySelector('.costing-labor').textContent")
        check("US$" in labor or "USD" in labor, f"money follows the project's currency ({labor})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"no horizontal overflow on a phone ({wide}px)")
        await b.shot("maker_costing_mobile", full=False)

        # Lo guardado vuelve al reabrir la ficha
        await b.js("document.getElementById('closeOverviewBtn').click()")
        await open_overview()
        st = await b.js("""({rate: document.querySelector('.costing-card [data-field="hourly_rate_cents"]').value,
            cur: document.querySelector('.costing-card [data-field="currency"]').value,
            hours: document.querySelector('.costing-card [data-field="budget_minutes"]').value})""")
        check(st == {"rate": "350.00", "cur": "USD", "hours": "10"}, f"reopening shows what was saved ({st})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_maker():
    asyncio.run(main())
