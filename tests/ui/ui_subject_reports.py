"""Reportes de hábitos (en Reportes) y de costos (en la pestaña Costos), 1.23:
cada uno con su botón, su forma en el modal y su contador de IA."""
import asyncio
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
TITLE = "document.getElementById('savedReportTitle').textContent"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def grant(email, module):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_subject_reports.db"
    conn = sqlite3.connect(db)
    user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    conn.execute("INSERT INTO user_modules (user_id, module, allowed, enabled) VALUES (?, ?, 1, 1)", (user_id, module))
    conn.commit()
    conn.close()


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    today = date.today().isoformat()
    # Algo de esta semana en hábitos y en costos (los datos del fixture son de ayer)
    _, defs = api.call("GET", "/api/habits/definitions", expect=200)
    if not defs["habits"]:
        api.call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "icon": "📚"}, expect=201)
        _, defs = api.call("GET", "/api/habits/definitions", expect=200)
    key = defs["habits"][0]["key"]
    api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": key, "done": True}, expect=200)
    grant("yoshi@test.com", "maker")
    _, projects = api.call("GET", "/api/projects", expect=200)
    project = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    api.call("PUT", f"/api/projects/{project['id']}/finance", {"hourly_rate_cents": 20000, "budget_cents": 500000}, expect=200)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    api.call("POST", "/api/costs", {"project_id": project["id"], "category_id": cats["categories"][0]["id"],
                                    "cost_date": today, "concept": "Dominio", "unit_cost_cents": 25000}, expect=201)

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Reportes: un botón por tema
        await b.js("document.getElementById('tabReports').click()")
        await b.wait_for("document.getElementById('savedHabitsReportBtn').textContent === 'Generar reporte de hábitos'")
        check(not await b.js("document.getElementById('savedHabitsReportBtn').hidden"), "Reportes has a habits report button")
        await b.js("document.getElementById('savedHabitsReportBtn').click()")
        await b.wait_for(f"{TITLE} === 'Reporte semanal de hábitos'", timeout=15)
        st = await b.js("({cards: [...document.querySelectorAll('#savedReportBody .report-card-title')].map(t => t.textContent),"
                        " charts: document.querySelectorAll('#savedReportBody svg.report-chart').length,"
                        " donuts: document.querySelectorAll('#savedReportBody .saved-donut').length,"
                        " rows: document.querySelectorAll('#savedReportBody .saved-metrics tbody tr').length,"
                        " tiles: document.querySelectorAll('#savedReportBody .report-stat').length,"
                        " summary: document.querySelector('#savedReportBody .saved-report-text').textContent})")
        check(st["cards"][:3] == ["Resumen", "Métricas", "¿Cómo te fue con cada hábito?"] and st["charts"] == 1
              and st["donuts"] >= 1 and st["rows"] >= 6 and st["tiles"] == 0 and "%" in st["summary"],
              f"the habits report looks like the time one: metrics table, day bars and donuts ({st})")
        await b.shot("subject_habits_report", full=False)
        await b.js("document.getElementById('savedReportClose').click()")
        await b.wait_for("document.getElementById('savedHabitsReportBtn').textContent === 'Ver reporte de hábitos'")
        check(await b.js("document.getElementById('savedReportBtn').textContent") == "Generar reporte de tiempo",
              "the time report of the same week is still to generate")

        # La lista de Reportes no trae los de costos, y la de Costos solo trae esos
        await b.js("document.getElementById('savedReportsListBtn').click()")
        await b.wait_for("document.querySelectorAll('#savedReportList .saved-report-row').length > 0")
        rows = await b.js("[...document.querySelectorAll('#savedReportList .saved-report-row small')].map(s => s.textContent)")
        check(rows and all("hábitos" in r or "tiempo" in r for r in rows), f"the Reportes list has time and habits reports ({rows})")
        await b.js("document.getElementById('savedReportClose').click()")

        # Costos: el reporte del mes, con su propio contador de IA
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("goToView('costs')")
        await b.wait_for("document.getElementById('costsReportBtn').textContent === 'Generar reporte'")
        await b.js("document.getElementById('costsReportBtn').click()")
        await b.wait_for(f"{TITLE} === 'Reporte mensual de costos'", timeout=15)
        st = await b.js("({cards: [...document.querySelectorAll('#savedReportBody .report-card-title')].map(t => t.textContent),"
                        " text: document.getElementById('savedReportBody').textContent,"
                        " columns: document.querySelectorAll('#savedReportBody .costs-breakdown').length,"
                        " donuts: document.querySelectorAll('#savedReportBody .saved-donut').length,"
                        " tiles: document.querySelectorAll('#savedReportBody .report-stat').length})")
        check(st["cards"][:4] == ["Resumen", "Métricas", "¿En qué se fue el dinero?", "Por proyecto"]
              and st["columns"] == 1 and st["donuts"] >= 1 and st["tiles"] == 0
              and "Habit Tracker" in st["text"] and "Gastos más grandes" in st["text"],
              f"the costs report looks like the time one: metrics, columns, donuts and projects ({st['cards']}, {st['columns']}, {st['donuts']})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"nothing overflows the phone width ({wide})")
        await b.shot("subject_costs_report", full=False)

        # Con el tema oscuro, al imprimir sale en claro (los cuadros negros del PDF)
        await b.js("document.documentElement.dataset.theme = 'dark'; renderForPrint(true)")
        await b.send("Emulation.setEmulatedMedia", media="print")
        bg = await b.js("getComputedStyle(document.querySelector('#savedReportBody .report-card')).backgroundColor")
        text = await b.js("getComputedStyle(document.querySelector('#savedReportBody .saved-report-text')).color")
        light = lambda c: sum(float(x) for x in c[c.index("(") + 1:c.index(")")].replace(",", " ").replace("/", " ").split()[:3]) > 600
        check(light(bg) and not light(text), f"printed in dark mode, cards are light with dark text ({bg}, {text})")
        await b.shot("subject_costs_print_dark")
        await b.send("Emulation.setEmulatedMedia", media="")
        await b.js("renderForPrint(false); document.documentElement.dataset.theme = 'light'")
        await b.js("""(() => {
            const real = window.apiFetch;
            window.apiFetch = (path, options) => path === '/api/reports/ai-usage?subject=costs'
                ? Promise.resolve({pool: 'costs', configured: true, limit: 10, used_today: 1, remaining: 9})
                : real(path, options);
            currentUser.modules.ai = {enabled: true, allowed: true};
        })()""")
        await b.js("refreshAiUsage('costs')")
        await b.wait_for("!document.getElementById('savedReportAiUsage').hidden")
        text = await b.js("document.getElementById('savedReportAiUsage').textContent")
        check(text == "IA: te quedan 9 de 10 textos hoy (reportes de costos).", f"costs has its own AI counter ({text})")
        await b.js("document.getElementById('savedReportClose').click()")
        await b.js("document.getElementById('costsReportsListBtn').click()")
        await b.wait_for("document.querySelectorAll('#savedReportList .saved-report-row').length > 0")
        rows = await b.js("[...document.querySelectorAll('#savedReportList .saved-report-row small')].map(s => s.textContent)")
        check(rows and all("costos" in r for r in rows), f"the Costos list has only cost reports ({rows})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_subject_reports():
    asyncio.run(main())
