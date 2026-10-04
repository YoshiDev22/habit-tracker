"""Reportes guardados (épica 30, Fase 4): generar, ver, la lista e imprimir."""
import asyncio
import json
import os
import sqlite3
from pathlib import Path

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
OPEN = "!document.getElementById('savedReportsModal').classList.contains('hidden')"
TITLES = "[...document.querySelectorAll('#savedReportBody .report-card-title')].map(t => t.textContent)"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('last_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabReports').click()")
        await b.wait_for("document.getElementById('savedReportBtn').textContent === 'Generar reporte'")
        check(True, "with no report for this week the button says 'Generar reporte'")

        # Generar el de la semana que se ve
        await b.js("document.getElementById('savedReportBtn').click()")
        await b.wait_for("document.getElementById('savedReportTitle').textContent.startsWith('Reporte semanal')")
        titles = await b.js(TITLES)
        check(titles[:3] == ["Resumen", "Métricas", "¿En qué se fue el tiempo?"] and "Patrones" in titles
              and "Para la próxima semana" in titles and "Cierre" in titles,
              f"the report has the sections of the examples ({titles})")
        st = await b.js("""({rows: document.querySelectorAll('#savedReportBody .saved-metrics tbody tr').length,
            cols: document.querySelectorAll('#savedReportBody .saved-metrics thead th').length,
            bars: document.querySelectorAll('#savedReportBody .chart-bar').length,
            donuts: document.querySelectorAll('#savedReportBody .saved-donut').length,
            closing: [...document.querySelectorAll('.saved-closing-item strong')].map(s => s.textContent),
            title: document.getElementById('savedReportTitle').textContent,
            meta: document.getElementById('savedReportMeta').textContent})""")
        check(st["rows"] >= 7 and st["cols"] == 3 and st["bars"] >= 1 and st["donuts"] == 2,
              f"metrics table against the previous week, day bars and two donuts ({st})")
        check(st["closing"] == ["Bien hecho:", "Tip:"] and st["title"] == "Reporte semanal de tiempo"
              and st["meta"].startswith("Semana del"), f"title, period line and closing boxes ({st})")
        _, lst = call("GET", "/api/reports", expect=200)
        check(len(lst["reports"]) == 1 and lst["reports"][0]["kind"] == "week", f"it is saved ({lst['reports']})")
        st = await b.js("({back: !document.getElementById('savedReportBack').hidden, actions: !document.getElementById('savedReportActions').hidden,"
                        " wide: document.documentElement.scrollWidth})")
        check(not st["back"] and st["actions"] and st["wide"] <= 390, f"no ‹ when opened from the button, fits a phone ({st})")
        await b.shot("saved_report", full=False)

        # Imprimir: solo el reporte, sin botones
        await b.send("Emulation.setEmulatedMedia", media="print")
        st = await b.js("""({app: getComputedStyle(document.querySelector('.app-container')).display,
            modal: getComputedStyle(document.getElementById('savedReportsModal')).display,
            actions: getComputedStyle(document.getElementById('savedReportActions')).display})""")
        check(st == {"app": "none", "modal": "block", "actions": "none"}, f"printing shows only the report ({st})")
        await b.send("Emulation.setEmulatedMedia", media="")

        # Cerrar: ahora el botón abre el guardado
        await b.js("document.getElementById('savedReportClose').click()")
        await b.wait_for("document.getElementById('savedReportBtn').textContent === 'Ver reporte'")
        check(await b.js("!document.body.classList.contains('saved-report-open')"), "closing clears the print mode")

        # Regenerar pone la hora de ahora: se envejece en la base y se comprueba que cambie
        db = sqlite3.connect(Path(os.environ["HABIT_UI_TMP"]) / "test_saved_reports.db")
        db.execute("UPDATE reports SET created_at = '2026-01-01 10:00:00', trigger = 'auto'")
        db.commit()
        db.close()
        await b.js("document.getElementById('savedReportBtn').click()")
        await b.wait_for("document.getElementById('savedReportMeta').textContent.includes('1 ene')")
        meta = await b.js("document.getElementById('savedReportMeta').textContent")
        check("automático" in meta, f"an aged automatic report shows its old time ({meta})")
        await b.js("document.getElementById('savedReportRegenerate').click()")
        # Mientras se genera, la línea queda vacía: se espera la nueva, no solo que se vaya la vieja
        await b.wait_for("document.getElementById('savedReportMeta').textContent.includes('a mano')")
        meta = await b.js("document.getElementById('savedReportMeta').textContent")
        check("a mano" in meta and "1 ene" not in meta, f"regenerating updates the time and says 'a mano' ({meta})")
        status = await b.js("document.getElementById('savedReportStatus').textContent")
        check(status.startswith("Reporte generado ✓"), f"regenerating says it worked ({status})")

        # Un clic dentro de la espera no manda nada: dice cuánto falta
        before = await b.js("document.getElementById('savedReportMeta').textContent")
        await b.js("savedState.readyAt = Date.now() + 20000; document.getElementById('savedReportRegenerate').click()")
        status = await b.js("document.getElementById('savedReportStatus').textContent")
        after = await b.js("document.getElementById('savedReportMeta').textContent")
        check("Espera 20 s" in status and before == after, f"a click during the wait says how long is left ({status})")

        # Imprimir: las gráficas al ancho de una hoja, y de vuelta al terminar
        await b.js("window.dispatchEvent(new Event('beforeprint'))")
        printing = await b.js("document.querySelector('#savedReportBody .report-chart').getAttribute('viewBox')")
        await b.js("window.dispatchEvent(new Event('afterprint'))")
        screen = await b.js("document.querySelector('#savedReportBody .report-chart').getAttribute('viewBox')")
        check(printing.startswith("0 0 680 ") and not screen.startswith("0 0 680 "),
              f"charts are drawn at page width to print ({printing} / {screen})")
        await b.js("document.getElementById('savedReportClose').click()")

        # La lista, y de ahí el reporte con ‹; Escape vuelve a la lista
        await b.js("document.getElementById('savedReportsListBtn').click()")
        await b.wait_for("document.querySelectorAll('#savedReportList .saved-report-row').length === 1")
        await b.js("document.querySelector('#savedReportList .saved-report-row').click()")
        await b.wait_for("document.getElementById('savedReportTitle').textContent.startsWith('Reporte semanal')")
        check(await b.js("!document.getElementById('savedReportBack').hidden"), "opened from the list it has ‹")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
        await b.wait_for("!document.getElementById('savedReportList').hidden")
        check(await b.js(OPEN), "Escape goes back to the list")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
        await b.wait_for(f"!({OPEN})")
        check(True, "and from the list it closes")

        # Mes: genera el suyo; Personalizado no tiene botón
        await b.js("document.querySelector('[data-range=month]').click()")
        await b.wait_for("document.getElementById('savedReportBtn').textContent === 'Generar reporte'")
        await b.js("document.getElementById('savedReportBtn').click()")
        await b.wait_for("document.getElementById('savedReportTitle').textContent.startsWith('Reporte mensual')")
        check(True, "the month report is generated too")
        await b.js("document.getElementById('savedReportClose').click()")
        await b.js("document.querySelector('[data-range=custom]').click()")
        check(await b.js("document.getElementById('savedReportBtn').hidden"), "Personalizado has no report button")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_saved_reports():
    asyncio.run(main())
