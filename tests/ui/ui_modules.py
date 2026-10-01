"""Apagar y encender el módulo Hábitos desde Mi perfil (épica 24, Fase 1)."""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
TABS = "[...document.querySelectorAll('.tab-btn')].filter(t => t.offsetWidth > 0).map(t => t.id)"
CARD_TITLES = "[...document.querySelectorAll('#reportsBody .report-card-title')].map(e => e.textContent)"
HABIT_REQUESTS = "performance.getEntriesByType('resource').filter(e => e.name.includes('/api/habits')).length"


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def toggle_habits():
        await b.js("document.getElementById('userEmail').click()")
        await asyncio.sleep(0.4)
        await b.js("document.getElementById('moduleHabits').click()")

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('last_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        check(await b.js(TABS) == ["tabCalendar", "tabProjects", "tabReports"], "three tabs by default")

        # Apagar: la casilla está marcada y al tocarla se va el Calendario
        await b.js("document.getElementById('userEmail').click()")
        await asyncio.sleep(0.4)
        check(await b.js("document.getElementById('moduleHabits').checked") is True, "Mi perfil shows Hábitos on")
        await b.shot("modules_profile", full=False)
        await b.js("document.getElementById('moduleHabits').click()")
        ok = await b.wait_for("document.getElementById('tabCalendar').hidden")
        st = await b.js(f"({{tabs: {TABS}, view: currentViewId, gear: document.getElementById('settingsBtn').hidden}})")
        check(ok and st == {"tabs": ["tabProjects", "tabReports"], "view": "projects", "gear": True},
              f"turning it off hides Calendario and the habits gear ({st})")
        _, me = api.call("GET", "/api/auth/me", expect=200)
        check(me["modules"]["habits"]["enabled"] is False, "saved in the account")
        await b.js("document.querySelector('#profileModal [data-close-modal]').click()")
        await asyncio.sleep(0.3)

        # Reportes sin la tarjeta de hábitos, y sin pedirla
        await b.js("document.getElementById('tabReports').click()")
        await b.wait_for(f"{CARD_TITLES}.length >= 3")
        titles = await b.js(CARD_TITLES)
        check("Hábitos" not in titles, f"Reportes has no habits card ({titles})")

        # Al recargar sigue apagado y no se pide nada de hábitos
        await b.goto(BASE + "/", wait=3.0)
        st = await b.js(f"({{tabs: {TABS}, view: currentViewId, habitReqs: {HABIT_REQUESTS},"
                        " missed: !document.getElementById('missedDayModal').classList.contains('hidden'),"
                        " setup: !document.getElementById('habitsSetupModal').classList.contains('hidden')})")
        check(st["tabs"] == ["tabProjects", "tabReports"] and st["view"] == "reports",
              f"stays off after a reload, on the last tab ({st})")
        check(st["habitReqs"] == 0 and not st["missed"] and not st["setup"],
              f"no habit requests or prompts while off ({st})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"two tabs fit the phone ({wide}px)")
        await b.shot("modules_off", full=False)

        # Encender: vuelve el Calendario con sus datos, y la tarjeta de Reportes
        await toggle_habits()
        ok = await b.wait_for("!document.getElementById('tabCalendar').hidden")
        await b.js("document.querySelector('#profileModal [data-close-modal]').click()")
        await b.wait_for(f"{CARD_TITLES}.includes('Hábitos')")
        check(ok and "Hábitos" in await b.js(CARD_TITLES), "turning it on brings back the tab and the habits card")
        await b.js("document.getElementById('tabCalendar').click()")
        await b.wait_for("document.querySelectorAll('#daysGrid .day-cell').length > 0")
        st = await b.js("({cells: document.querySelectorAll('#daysGrid .day-cell').length,"
                        " legend: document.querySelectorAll('.legend-item, .habit-legend-item').length,"
                        " gear: document.getElementById('settingsBtn').hidden})")
        check(st["cells"] >= 28 and not st["gear"], f"the calendar is back with its data ({st})")

        # Cerrar sesión con el módulo apagado deja el Calendario para quien entre
        await toggle_habits()
        await b.wait_for("document.getElementById('tabCalendar').hidden")
        await b.js("document.querySelector('#profileModal [data-close-modal]').click()")
        await b.js("handleLogout()")
        await asyncio.sleep(1.0)
        st = await b.js("({hidden: document.getElementById('tabCalendar').hidden, view: currentViewId})")
        check(st == {"hidden": False, "view": "calendar"}, f"logout shows Calendario again ({st})")
        api.call("PUT", "/api/auth/me/modules/habits", {"enabled": True}, expect=200)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_modules():
    asyncio.run(main())
