"""Costos (1.24): repartir un gasto entre proyectos y los gastos recurrentes."""
import asyncio
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import api
from api import login
from cdp import Browser

BASE = api.BASE
ROOT = Path(__file__).resolve().parents[2]
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def grant(email):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_cost_splits.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "maker"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def sheet(project):
    return api.call("GET", f"/api/costs?project_id={project['id']}", expect=200)[1]["costs"]


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    grant("yoshi@test.com")
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    _, projects = api.call("GET", "/api/projects", expect=200)
    ht = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    _, tesis = api.call("POST", "/api/projects", {"name": "Tesis"}, expect=201)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    ia = next(c for c in cats["categories"] if c["name"] == "IA")
    today = date.today().isoformat()
    _, cost = api.call("POST", "/api/costs", {"project_id": ht["id"], "category_id": ia["id"], "cost_date": today,
                                              "concept": "Anthropic", "unit_cost_cents": 2000000}, expect=201)

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});"
                   f" localStorage.setItem('costs_project', '{ht['id']}')")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabCosts').click()")
        await b.wait_for(f"document.querySelector('tr.cost-row[data-cost-id=\"{cost['id']}\"]')")

        # Repartir: 65 % Habit Tracker, 35 % Tesis
        await b.js(f"document.querySelector('tr.cost-row[data-cost-id=\"{cost['id']}\"] .cost-split').click()")
        await b.wait_for("!document.getElementById('costSplitModal').classList.contains('hidden')")
        await b.js("""(() => {
            const rows = [...document.querySelectorAll('#costSplitEditor .allocation-row')];
            const byName = name => rows.find(r => r.textContent.includes(name));
            const ht = byName('Habit Tracker'), tesis = byName('Tesis');
            ht.querySelector('.allocation-pct').value = '65';
            const box = tesis.querySelector('input[type=checkbox]');
            box.checked = true; box.dispatchEvent(new Event('change'));
            tesis.querySelector('.allocation-pct').value = '35';
            tesis.querySelector('.allocation-pct').dispatchEvent(new Event('input'));
        })()""")
        total = await b.js("document.querySelector('#costSplitEditor .allocation-sum').textContent")
        check("100 %" in total and "✓" in total, f"the split adds up to 100 % ({total})")
        await b.shot("cost_split_dialog", full=False)
        await b.js("document.getElementById('costSplitSave').click()")
        await b.wait_for("document.getElementById('costSplitModal').classList.contains('hidden')")
        await b.wait_for("document.querySelector('#costsRows .cost-tag.split')")
        st = await b.js("""(() => { const r = document.querySelector('#costsRows tr.cost-row');
            return {tag: r.querySelector('.cost-tag.split').textContent, total: r.querySelector('.col-total').textContent}; })()""")
        check("65 %" in st["tag"] and "13,000.00" in st["total"] and "de $20,000.00" in st["total"],
              f"the row shows its 65 % share of the whole ({st})")
        tesis_rows = sheet(tesis)
        check(len(tesis_rows) == 1 and tesis_rows[0]["total_cents"] == 700000, f"Tesis gets its 35 % ({tesis_rows})")

        # Editar el monto de una parte cambia el gasto entero
        await b.js("""(() => { const i = document.querySelector('#costsRows tr.cost-row [data-field=unit_cost_cents]');
            i.value = '10000'; i.dispatchEvent(new Event('change', {bubbles: true})); })()""")
        await b.wait_for("document.querySelector('#costsRows tr.cost-row .col-total').textContent.includes('6,500.00')")
        check(sheet(tesis)[0]["total_cents"] == 350000, "editing the amount reshares the whole expense")

        # Un recurrente nuevo, repartido igual
        await b.js("document.getElementById('recurringAdd').click()")
        await b.wait_for("!document.getElementById('recurringModal').classList.contains('hidden')")
        await b.js(f"""(() => {{
            const f = document.getElementById('recurringForm').elements;
            f.concept.value = 'Hostinger'; f.unit_cost.value = '250';
            f.category_id.value = '{ia['id']}'; f.start_date.value = '{today}';
            const rows = [...document.querySelectorAll('#recurringAllocations .allocation-row')];
            const tesis = rows.find(r => r.textContent.includes('Tesis'));
            const box = tesis.querySelector('input[type=checkbox]');
            box.checked = true; box.dispatchEvent(new Event('change'));
            rows.find(r => r.textContent.includes('Habit Tracker')).querySelector('.allocation-pct').value = '50';
            tesis.querySelector('.allocation-pct').value = '50';
            document.getElementById('recurringForm').requestSubmit();
        }})()""")
        await b.wait_for("document.querySelectorAll('#recurringList .recurring-item').length === 1")
        item = await b.js("document.querySelector('#recurringList .recurring-item').textContent")
        check("Hostinger" in item and "Cada mes" in item and "Tesis 50 %" in item, f"the recurring cost is listed ({item})")
        await b.wait_for("[...document.querySelectorAll('#costsRows .cost-tag')].some(t => t.textContent === '🔁')")
        check(any(r["recurring_id"] and r["total_cents"] == 12500 for r in sheet(tesis)),
              "today's charge was written into both sheets, split")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"nothing overflows the phone width ({wide})")
        await b.js("window.scrollTo(0, document.querySelector('.costs-sheet-card').getBoundingClientRect().top + window.scrollY - 10)")
        await asyncio.sleep(0.3)
        await b.shot("cost_recurring", full=False)

        # Pausar y dejar de cobrarlo
        await b.js("document.querySelector('#recurringList [data-action=pause]').click()")
        await b.wait_for("document.querySelector('#recurringList .recurring-item.paused')")
        check(True, "pausing marks it as paused")
        await b.js("document.querySelector('#recurringList [data-action=delete]').click()")
        await b.wait_for("!document.getElementById('confirmModal').classList.contains('hidden')")
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for("document.querySelectorAll('#recurringList .recurring-item').length === 0")
        check(all(r["recurring_id"] is None for r in sheet(tesis)), "its charges stay, without the 🔁")

        # Borrar una parte borra el gasto entero
        await b.js(f"document.querySelector('tr.cost-row[data-cost-id=\"{cost['id']}\"] .cost-delete').click()")
        await b.wait_for("!document.getElementById('confirmModal').classList.contains('hidden')")
        msg = await b.js("document.getElementById('confirmModal').textContent")
        check("Tesis" in msg, f"deleting a part warns it goes from Tesis too ({msg.strip()[:120]})")
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for(f"!document.querySelector('tr.cost-row[data-cost-id=\"{cost['id']}\"]')")
        check(not any(r["concept"] == "Anthropic" for r in sheet(tesis)), "and Tesis loses its part")

        # Hacer recurrente un gasto ya anotado: el formulario sale lleno, con el cobro el mes siguiente
        _, dom = api.call("POST", "/api/costs", {"project_id": ht["id"], "category_id": ia["id"], "cost_date": today,
                                                 "concept": "Dominio", "unit_cost_cents": 30000}, expect=201)
        await b.js("loadCostRows()")
        row = f"document.querySelector('tr.cost-row[data-cost-id=\"{dom['id']}\"]')"
        await b.wait_for(f"{row} && {row}.querySelector('.cost-make-recurring')")
        await b.js(f"{row}.querySelector('.cost-make-recurring').click()")
        await b.wait_for("!document.getElementById('recurringModal').classList.contains('hidden')")
        st = await b.js("""(() => { const f = document.getElementById('recurringForm').elements;
            return {title: document.getElementById('recurringTitle').textContent, concept: f.concept.value,
                    cost: f.unit_cost.value, start: f.start_date.value,
                    hint: !document.getElementById('recurringFromHint').hidden}; })()""")
        check(st["title"] == "Hacer recurrente" and st["concept"] == "Dominio" and st["cost"] == "300.00"
              and st["start"] > today and st["hint"], f"the form comes filled in, first charge next month ({st})")
        await b.js("document.getElementById('recurringForm').requestSubmit()")
        await b.wait_for("document.getElementById('recurringModal').classList.contains('hidden')")
        await b.wait_for(f"{row} && {row}.querySelector('.cost-tag') && !{row}.querySelector('.cost-make-recurring')")
        same = [r for r in sheet(ht) if r["concept"] == "Dominio"]
        check(len(same) == 1 and same[0]["recurring_id"], f"the expense is marked 🔁 and not duplicated ({len(same)})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_cost_splits():
    asyncio.run(main())
