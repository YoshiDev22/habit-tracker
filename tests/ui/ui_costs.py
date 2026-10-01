"""Pestaña Costos (plan Maker, épica 24 Fase 3): resumen, hoja, pegar de una hoja y categorías."""
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
TABS = "[...document.querySelectorAll('.tab-btn')].filter(t => t.offsetWidth > 0).map(t => t.id)"
# Lo que se copia de Excel o Google Sheets: filas con tabuladores, con encabezado
PASTED = ("Fecha\tConcepto\tCategoría\tCantidad\tCosto unitario\n"
          "28/09/2026\tTornillos M3\tMaterial\t100\t$1.50\n"
          "29/09/2026\tHosting anual\tHosting\t1\t1,200.00\n"
          "\tSin precio\tOtro\t\t\n"
          "fecha mala\tRoto\tOtro\t1\t10")


def grant(email):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_costs.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "maker"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    grant("yoshi@test.com")
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    _, projects = api.call("GET", "/api/projects", expect=200)
    ht = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    api.call("PUT", f"/api/projects/{ht['id']}/finance", {"hourly_rate_cents": 30000, "budget_cents": 500000}, expect=200)
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def costs_of():
        return api.call("GET", f"/api/costs?project_id={ht['id']}", expect=200)[1]

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('last_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        tabs = await b.js(TABS)
        wide = await b.js("document.documentElement.scrollWidth")
        check(tabs == ["tabCalendar", "tabProjects", "tabReports", "tabCosts"], f"Costos is the fourth tab with Maker on ({tabs})")
        check(wide <= 390, f"four tabs fit a phone ({wide}px)")

        await b.js("document.getElementById('tabCosts').click()")
        await b.wait_for("document.querySelectorAll('.costs-projects tbody tr').length > 0")
        st = await b.js("""({rows: [...document.querySelectorAll('.costs-projects tbody tr')].map(r => r.cells[0].textContent),
            project: document.getElementById('costsProject').selectedOptions[0].textContent})""")
        check(any("Habit Tracker" in r for r in st["rows"]) and not any("Sin asignar" in r for r in st["rows"]),
              f"summary lists the projects, not Sin asignar ({st['rows']})")

        # Elegir el proyecto tocando su fila del resumen
        await b.js(f"document.querySelector('.costs-projects tr[data-project-id=\"{ht['id']}\"]').click()")
        await b.wait_for(f"document.getElementById('costsProject').value === '{ht['id']}'")
        check(True, "tapping a summary row picks its project for the sheet")

        # Una fila nueva: se crea al tener concepto, y el costo se guarda celda por celda
        await b.js("document.getElementById('costsAddRow').click()")
        await b.js("""(() => {
            const row = document.querySelector('#costsRows tr');
            const set = (f, v) => { const i = row.querySelector(`[data-field="${f}"]`); i.value = v; i.dispatchEvent(new Event('change', {bubbles: true})); };
            set('concept', 'Base de madera');
        })()""")
        data = await wait_api(f"/api/costs?project_id={ht['id']}", lambda body: len(body["costs"]) == 1)
        check(data["costs"][0]["concept"] == "Base de madera", "a new row is created once it has a concept")
        await b.js("""(() => {
            const row = document.querySelector('#costsRows tr[data-cost-id]');
            const i = row.querySelector('[data-field="unit_cost_cents"]'); i.value = '250.50';
            i.dispatchEvent(new Event('change', {bubbles: true}));
            const q = row.querySelector('[data-field="quantity"]'); q.value = '2';
            q.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        data = await wait_api(f"/api/costs?project_id={ht['id']}", lambda body: body["total_cents"] == 50100)
        check(data["total_cents"] == 50100, f"each cell saves: 2 × 250.50 = 501.00 ({data['total_cents']})")
        await b.wait_for("document.getElementById('costsTotal').textContent.includes('501')")

        # Pegar filas de una hoja: vista previa, filas malas marcadas, categoría nueva
        await b.js(f"""(() => {{
            const dt = new DataTransfer();
            dt.setData('text/plain', {json.dumps(PASTED)});
            document.querySelector('#costsRows [data-field="concept"]').dispatchEvent(
                new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}}));
        }})()""")
        await b.wait_for("!document.getElementById('costsImportModal').classList.contains('hidden')")
        st = await b.js("""({summary: document.getElementById('costsImportSummary').textContent,
            invalid: document.querySelectorAll('#costsImportRows tr.invalid').length,
            newCat: document.getElementById('costsImportNewCatsLabel').textContent,
            newCatShown: !document.getElementById('costsImportNewCatsOption').classList.contains('hidden')})""")
        check("3 de 4" in st["summary"] and st["invalid"] == 1, f"preview: the bad date is flagged ({st['summary']})")
        check(st["newCatShown"] and "Hosting" in st["newCat"], f"offers to create the unknown category ({st['newCat']})")
        await b.shot("costs_paste_preview", full=False)
        await b.js("document.getElementById('costsImportConfirm').click()")
        data = await wait_api(f"/api/costs?project_id={ht['id']}", lambda body: len(body["costs"]) == 4)
        concepts = {c["concept"]: c for c in data["costs"]}
        check(set(concepts) == {"Base de madera", "Tornillos M3", "Hosting anual", "Sin precio"},
              f"the valid rows were added ({sorted(concepts)})")
        check(concepts["Tornillos M3"]["total_cents"] == 15000 and concepts["Hosting anual"]["unit_cost_cents"] == 120000
              and concepts["Tornillos M3"]["cost_date"] == "2026-09-28", "money and dates parsed like a Mexican sheet")
        _, cats = api.call("GET", "/api/costs/categories", expect=200)
        check("Hosting" in [c["name"] for c in cats["categories"]], "the new category was created")

        # El resumen cuadra con la API, margen incluido
        _, sm = api.call("GET", "/api/costs/summary", expect=200)
        row = next(r for r in sm["projects"] if r["project_id"] == ht["id"])
        await b.wait_for(f"document.querySelector('.costs-projects tr[data-project-id=\"{ht['id']}\"]').textContent.includes('{row['margin_cents'] // 100:,}')")
        text = await b.js(f"document.querySelector('.costs-projects tr[data-project-id=\"{ht['id']}\"]').textContent")
        check(f"{row['total_cost_cents'] / 100:,.2f}" in text, f"summary row shows cost and margin ({text})")

        # Una categoría con gastos no se borra: el motivo se ve tal cual
        await b.js("document.getElementById('costsCategories').open = true")
        await asyncio.sleep(0.3)
        await b.js("[...document.querySelectorAll('#costsCategoryList .config-row')].find(r => r.querySelector('.config-name').value === 'Material').querySelector('.cost-cat-delete').click()")
        await b.wait_for("!document.getElementById('costsCategoryError').classList.contains('hidden')")
        err = await b.js("document.getElementById('costsCategoryError').textContent")
        check("gasto" in err, f"a category with costs is not deleted ({err})")

        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"the page itself never scrolls sideways ({wide}px)")

        await b.js("window.scrollTo(0, 0)")
        await b.shot("costs_mobile_top", full=False)
        st = await b.js("""({left: Math.round(document.querySelector('.costs-summary').getBoundingClientRect().left),
            scroll: document.getElementById('viewsViewport').scrollLeft})""")
        check(st["left"] >= 0 and st["scroll"] == 0, f"the Costs view is not shifted sideways ({st})")
        await b.js("window.scrollTo(0, document.querySelector('.costs-sheet-card').getBoundingClientRect().top + window.scrollY)")
        await asyncio.sleep(0.3)
        await b.shot("costs_mobile_sheet", full=False)

        # Recargar en Costos vuelve a Costos
        await b.goto(BASE + "/", wait=3.0)
        await b.js(CLOSE_WELCOME)
        check(await b.js("currentViewId") == "costs", "reload stays on Costos")

        # Escritorio: la app se ensancha mientras se ve Costos
        await b.viewport(1280, 900)
        await asyncio.sleep(0.5)
        st = await b.js("({wide: document.body.classList.contains('costs-wide'), w: Math.round(document.querySelector('.app-container').getBoundingClientRect().width)})")
        check(st["wide"] and st["w"] > 900, f"desktop widens the app for the sheet ({st})")
        await b.shot("costs_desktop", full=False)
        await b.js("window.scrollTo(0, document.querySelector('.costs-sheet-card').getBoundingClientRect().top + window.scrollY)")
        await asyncio.sleep(0.3)
        await b.shot("costs_desktop_sheet", full=False)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(0.4)
        check(not await b.js("document.body.classList.contains('costs-wide')"), "leaving Costos narrows it back")

        # Apagar Maker quita la pestaña sin borrar nada
        api.call("PUT", "/api/auth/me/modules/maker", {"enabled": False}, expect=200)
        await b.goto(BASE + "/", wait=3.0)
        await b.js(CLOSE_WELCOME)
        st = await b.js(f"({{tabs: {TABS}, view: currentViewId}})")
        check("tabCosts" not in st["tabs"] and st["view"] != "costs", f"Maker off hides Costos ({st})")
        api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
        check(len((await costs_of())["costs"]) == 4, "and keeps the costs")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_costs():
    asyncio.run(main())
