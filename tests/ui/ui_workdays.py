"""Mi perfil › Calendario de trabajo (épica 30, Fase 3): huso, país, festivos y días libres."""
import asyncio
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

import api
from api import call, login, wait_api
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def cache_holiday(year, day, name):
    """Las pruebas no salen a internet: el festivo va directo a la caché de esta base."""
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_workdays.db"
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO holiday_cache (country, year, days, fetched_at) VALUES ('MX', ?, ?, '2026-01-01 00:00:00')",
                 (year, json.dumps([{"date": day.isoformat(), "name": name}])))
    conn.commit()
    conn.close()


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    year = dt.date.today().year
    holiday = dt.date(year, 9, 16)
    cache_holiday(year, holiday, "Día de la Independencia")

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Al entrar sin huso guardado, se guarda el del navegador
        zone = await b.js("Intl.DateTimeFormat().resolvedOptions().timeZone")
        settings = await wait_api("/api/days/settings", lambda body: body["configured"])
        check(settings["configured"] and settings["timezone"] == zone,
              f"the browser's time zone is saved on first visit ({settings}, {zone})")

        await b.js("document.getElementById('userEmail').click()")
        await asyncio.sleep(0.4)
        await b.js("document.getElementById('workCalendar').open = true")
        await b.wait_for("document.querySelectorAll('#workOfficialDays .work-day').length > 0")
        st = await b.js("""({tz: document.getElementById('workTimezone').value, country: document.getElementById('workCountry').value,
            official: document.getElementById('workOfficialDays').textContent})""")
        check(st["tz"] == zone and st["country"] == "MX" and "Independencia" in st["official"],
              f"shows the zone, the country and the official holidays ({st})")

        # "Lo trabajo" marca el festivo como laboral; desmarcarlo lo quita
        await b.js("document.querySelector('#workOfficialDays .work-worked').click()")
        days = await wait_api(f"/api/days?year={year}", lambda body: body["official"][0]["observed"] is False)
        check(days["official"][0]["observed"] is False, "'Lo trabajo' marks the holiday as a workday")
        await b.wait_for("document.querySelector('#workOfficialDays .work-day').classList.contains('worked')")
        await b.js("document.querySelector('#workOfficialDays .work-worked').click()")
        days = await wait_api(f"/api/days?year={year}", lambda body: body["official"][0]["observed"] is True)
        check(days["own"] == [], "unchecking it removes the mark")

        # Un día libre propio: se agrega y se quita
        free = dt.date(year, 10, 30).isoformat()
        await b.js(f"""(() => {{
            document.getElementById('workAddDate').value = '{free}';
            document.getElementById('workAddName').value = 'Festivo local';
            document.getElementById('workAddForm').requestSubmit();
        }})()""")
        days = await wait_api(f"/api/days?year={year}", lambda body: len(body["own"]) == 1)
        check(days["own"][0]["date"] == free and days["own"][0]["kind"] == "libre", f"a free day is added ({days['own']})")
        await b.wait_for("document.getElementById('workOwnDays').textContent.includes('Festivo local')")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"fits a phone ({wide}px)")
        await b.shot("work_calendar", full=False)
        await b.js("document.querySelector('#workOwnDays .work-remove').click()")
        await wait_api(f"/api/days?year={year}", lambda body: body["own"] == [])
        check(True, "and removed")

        # El huso se cambia escribiéndolo; uno inválido muestra el motivo
        await b.js("""(() => { const z = document.getElementById('workTimezone'); z.value = 'Marte/Olimpo';
            z.dispatchEvent(new Event('change', {bubbles: true})); })()""")
        await b.wait_for("!document.getElementById('workCalendarError').classList.contains('hidden')")
        err = await b.js("document.getElementById('workCalendarError').textContent")
        check("desconocido" in err, f"an unknown zone is rejected with its reason ({err})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_workdays():
    asyncio.run(main())
