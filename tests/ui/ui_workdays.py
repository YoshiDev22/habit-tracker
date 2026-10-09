"""⚙️ Configuración › Días y horario (épica 30, Fase 3): huso, país, festivos y días libres."""
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
        # Limpio: el navegador se reusa entre pruebas, y otra en el mismo puerto
        # pudo dejar festivos (vacíos, sin internet) en work_calendar_cache
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Al entrar sin huso guardado, se guarda el del navegador
        zone = await b.js("Intl.DateTimeFormat().resolvedOptions().timeZone")
        settings = await wait_api("/api/days/settings", lambda body: body["configured"])
        check(settings["configured"] and settings["timezone"] == zone,
              f"the browser's time zone is saved on first visit ({settings}, {zone})")

        await b.js("openSettings('days')")
        await b.wait_for("document.querySelectorAll('#workOfficialDays .work-day').length > 0")
        st = await b.js("""({tz: document.getElementById('workTimezone').value, country: document.getElementById('workCountry').value,
            official: document.getElementById('workOfficialDays').textContent})""")
        check(st["tz"] == zone and st["country"] == "MX" and "Independencia" in st["official"],
              f"shows the zone, the country and the official holidays ({st})")

        check(await b.js("document.querySelector('#workOfficialDays .work-rest').checked") is True,
              "an official holiday is a rest day by default")

        # En el calendario: 🎉 en el festivo (su mes) y en el popover
        mark = await b.js(f"""(() => {{
            currentDate = new Date({year}, 8, 1); renderCalendar();
            const cell = [...document.querySelectorAll('#daysGrid .day-cell')].find(c => c.querySelector('.day-holiday'));
            return cell ? cell.textContent : null;
        }})()""")
        check(mark is not None and "16" in mark, f"the calendar marks the holiday with 🎉 ({mark})")

        # Desmarcar "Descanso" lo vuelve laboral; marcarlo de nuevo quita esa marca
        await b.js("document.querySelector('#workOfficialDays .work-rest').click()")
        days = await wait_api(f"/api/days?year={year}", lambda body: body["official"][0]["observed"] is False)
        check(days["official"][0]["observed"] is False, "unchecking 'Descanso' marks the holiday as a workday")
        first_ok = await b.wait_for("document.querySelector('#workOfficialDays .work-day').classList.contains('worked')")
        check(first_ok and await b.wait_for("!document.querySelector('#daysGrid .day-holiday')"), "and the 🎉 leaves the calendar")
        await b.js("document.querySelector('#workOfficialDays .work-rest').click()")
        days = await wait_api(f"/api/days?year={year}", lambda body: body["official"][0]["observed"] is True)
        check(days["own"] == [], "checking it again removes the mark")

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
        removed = await wait_api(f"/api/days?year={year}", lambda body: body["own"] == [])
        check(removed["own"] == [], "and removed")

        # Días de descanso: se guardan al tocarlos, sin "Guardar Hábitos"
        await b.js("document.querySelector('#restDaysOptions input[value=\"6\"]').click()")
        me = await wait_api("/api/auth/me", lambda body: 6 in body["rest_days"])
        check(6 in me["rest_days"], f"a rest day is saved when ticked ({me['rest_days']})")
        await b.wait_for("document.getElementById('restDaysStatus').textContent === 'Guardado ✓'")
        await b.js("document.querySelector('#restDaysOptions input[value=\"6\"]').click()")
        await wait_api("/api/auth/me", lambda body: 6 not in body["rest_days"])

        # Guardado en el dispositivo: al reabrir no se piden; ↻ sí
        cached = await b.js("JSON.parse(localStorage.getItem('work_calendar_cache')).years[String(new Date().getFullYear())].official.length")
        check(cached == 1, f"the year's holidays are kept on this device ({cached})")
        await b.js("document.getElementById('settingsClose').click()")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("""window._daysFetches = 0; const f = window.fetch;
            window.fetch = (u, o) => { if (String(u).startsWith('/api/days?')) window._daysFetches++; return f(u, o); };""")
        await b.js("document.getElementById('settingsBtn').click()")
        await b.wait_for("!document.getElementById('habitsSetupModal').classList.contains('hidden')")
        st = await b.js("({menu: !document.getElementById('settingsMenu').hidden, title: document.getElementById('setupTitle').textContent})")
        # Esta cuenta no tiene hábitos: abre la bienvenida en Hábitos, y ‹ lleva al menú
        check(st == {"menu": False, "title": "¡Bienvenido! 👋"}, f"with no habits the gear opens the welcome on Hábitos ({st})")
        await b.js("document.getElementById('settingsBack').click()")
        st = await b.js("({menu: !document.getElementById('settingsMenu').hidden, title: document.getElementById('setupTitle').textContent})")
        check(st == {"menu": True, "title": "Configuración"}, f"‹ shows the menu ({st})")
        await b.shot("settings_menu", full=False)
        await b.js("document.querySelector('#settingsMenu [data-open=days]').click()")
        st = await b.js("({active: document.querySelector('[data-section=days]').classList.contains('active'), menu: !document.getElementById('settingsMenu').hidden,"
                        " title: document.getElementById('setupTitle').textContent, back: !document.getElementById('settingsBack').hidden,"
                        " n: document.querySelectorAll('#workOfficialDays .work-day').length, fetches: window._daysFetches})")
        check(st == {"active": True, "menu": False, "title": "Días y horario", "back": True, "n": 1, "fetches": 0},
              f"its row slides to the page, with the saved holidays and without asking ({st})")
        # ‹ y Escape vuelven al menú; Escape desde el menú cierra
        await b.js("document.getElementById('settingsBack').click()")
        check(await b.js("!document.getElementById('settingsMenu').hidden && document.getElementById('settingsBack').hidden"), "‹ goes back to the menu")
        await b.js("document.querySelector('#settingsMenu [data-open=days]').click()")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
        check(await b.js("!document.getElementById('settingsMenu').hidden"), "Escape goes back to the menu")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
        check(await b.wait_for("document.getElementById('habitsSetupModal').classList.contains('hidden')"), "and from the menu it closes")
        await b.js("openSettings('days')")
        await b.js("document.getElementById('workRefresh').click()")
        check(await b.wait_for("window._daysFetches === 1"), "↻ asks for them again")

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
