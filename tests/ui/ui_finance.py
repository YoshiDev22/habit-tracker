"""Finanzas (épica 37, fase 1): el módulo, "¿Cada cuándo cobras?", la alta rápida,
una transferencia que no es gasto, pegar un estado de cuenta con repetidos,
un fijo desde Organizar y Configuración › Finanzas."""
import asyncio
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import api
from api import login, wait_api
from cdp import Browser

BASE = api.BASE
ROOT = Path(__file__).resolve().parents[2]
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
TODAY = date.today().isoformat()


def grant(email):
    """scripts/grant_module.py contra la base de esta prueba (conftest: <nombre>.db)."""
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_finance.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "finance"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def summary():
    return api.call("GET", "/api/finance/summary", expect=200)[1]


def transactions():
    return api.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"]


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    grant("yoshi@test.com")
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        # La consola de Windows (cp1252) no imprime ★, ⇄ ni el signo menos de los montos
        encoding = sys.stdout.encoding or "utf-8"
        label = label.encode(encoding, "replace").decode(encoding)
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def set_value(selector, value):
        await b.js(f"""(() => {{
            const input = document.querySelector({json.dumps(selector)});
            input.value = {json.dumps(value)};
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
        }})()""")

    async def select_by_text(selector, text):
        await b.js(f"""(() => {{
            const select = document.querySelector({json.dumps(selector)});
            const option = [...select.options].find(o => o.textContent.startsWith({json.dumps(text)}));
            select.value = option.value;
            select.dispatchEvent(new Event('change', {{bubbles: true}}));
        }})()""")

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/api/health")   # mismo origen, sin arrancar la app
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Sin encender: ni la pestaña ni su página de Configuración
        check(await b.js("document.getElementById('tabFinance').hidden"), "no Finanzas tab while the module is off")
        await b.js("openSettings('modules')")
        await b.wait_for("!document.getElementById('moduleFinanceOption').hidden")
        check(await b.js("document.getElementById('settingsFinanceItem').hidden"), "no Finanzas row in Configuración yet")
        await b.js("document.getElementById('moduleFinance').click()")
        me = await wait_api("/api/auth/me", lambda body: body["modules"]["finance"]["enabled"])
        check(me["modules"]["finance"]["enabled"], "turning it on is saved in the account")
        await b.wait_for("!document.getElementById('tabFinance').hidden")
        check(not await b.js("document.getElementById('settingsFinanceItem').hidden"), "Configuración gets its Finanzas row")
        await b.js("document.getElementById('settingsClose').click()")

        # La pestaña: primero pregunta cada cuándo cobra
        await b.js("document.getElementById('tabFinance').click()")
        await b.wait_for("!document.getElementById('financeAsk').hidden")
        tabs = await b.js("[...document.querySelectorAll('.tab-btn')].filter(t => !t.hidden).map(t => t.textContent)")
        check(tabs[-2:] == ["Finanzas", "Reportes"], f"Finanzas sits right before Reportes ({tabs})")
        await b.shot("finance_ask", full=False)
        await b.js("document.querySelector('#financeAsk [data-period=\"biweekly\"]').click()")
        await wait_api("/api/finance/settings", lambda body: body["period"] == "biweekly")
        await b.wait_for("document.getElementById('financeAsk').hidden")
        label = await b.js("document.getElementById('financePeriodLabel').textContent")
        s = summary()
        start, end = date.fromisoformat(s["date_from"]), date.fromisoformat(s["date_to"])
        check(label.startswith(f"{start.day}–{end.day} "), f"the period is the biweekly one ({label})")
        check(await b.js("document.getElementById('financeNext').disabled"), "no going into the future")

        # Alta rápida: un gasto en efectivo, con su categoría
        await b.js("document.getElementById('financeAddBtn').click()")
        await b.wait_for("!document.getElementById('financeTxModal').classList.contains('hidden')")
        check(await b.js("document.activeElement.id") == "financeTxAmount", "the amount gets the focus")
        await set_value("#financeTxAmount", "230")
        await set_value("#financeTxConcept", "Tacos")
        await select_by_text("#financeTxCategory", "Comer fuera")
        await b.js("document.getElementById('financeTxSave').click()")
        await b.wait_for("document.querySelectorAll('.finance-tx').length === 1")
        row = await b.js("document.querySelector('.finance-tx').textContent")
        check("Tacos" in row and "Comer fuera" in row and "230.00" in row, f"the list shows it ({row})")

        # Una tarjeta, y su pago: es transferencia, no gasto
        api.call("POST", "/api/finance/accounts", {"name": "Tarjeta", "kind": "credit", "last4": "1234"}, expect=201)
        await b.js("loadFinance()")   # la creó la API: la pantalla la conoce al recargar
        await b.wait_for("financeState.accounts.length === 2")
        await b.js("document.getElementById('financeAddBtn').click()")
        await b.wait_for("!document.getElementById('financeTxModal').classList.contains('hidden')")
        await b.js("document.querySelector('#financeTxKind [data-kind=\"transfer\"]').click()")
        st = await b.js("""({cat: document.getElementById('financeTxCategoryField').hidden,
            to: document.getElementById('financeTxTo').selectedOptions[0].textContent,
            hint: !document.getElementById('financeTxHint').hidden})""")
        check(st["cat"] and st["to"].startswith("Tarjeta") and st["hint"],
              f"a transfer has no category, goes to the card and explains the payment ({st})")
        await set_value("#financeTxAmount", "1,500.50")
        await set_value("#financeTxConcept", "Pago de la tarjeta")
        await asyncio.sleep(0.4)   # que termine de aparecer el modal
        await b.shot("finance_transfer", full=False)
        await b.js("document.getElementById('financeTxSave').click()")
        await b.wait_for("document.querySelectorAll('.finance-tx').length === 2")
        s = summary()
        check(s["totals"][0]["expense_cents"] == 23000, f"the card payment is not an expense ({s['totals']})")
        stats = await b.js("[...document.querySelectorAll('#financeSummary .report-stat-value')].map(v => v.textContent)")
        check("230.00" in stats[0], f"Gastado shows only the tacos ({stats})")

        # Editar: tocar la fila
        await b.js("[...document.querySelectorAll('.finance-tx')].find(t => t.textContent.includes('Tacos')).click()")
        await b.wait_for("document.getElementById('financeTxTitle').textContent === 'Editar movimiento'")
        check(await b.js("document.getElementById('financeTxAmount').value") == "230.00", "editing shows the amount")
        await set_value("#financeTxAmount", "250")
        await b.js("document.getElementById('financeTxSave').click()")
        txs = await wait_api("/api/finance/transactions",
                             lambda body: any(t["amount_cents"] == 25000 for t in body["transactions"]))
        check(any(t["concept"] == "Tacos" and t["amount_cents"] == 25000 for t in txs["transactions"]), "the edit is saved")

        # Sin red: guardar avisa, el formulario se queda con lo escrito y nada se pierde
        await b.js("document.getElementById('financeAddBtn').click()")
        await b.wait_for("!document.getElementById('financeTxModal').classList.contains('hidden')")
        await set_value("#financeTxAmount", "45")
        await set_value("#financeTxConcept", "Café")
        await b.js("window.__fetch = window.fetch; window.fetch = () => Promise.reject(new TypeError('Failed to fetch'))")
        await b.js("document.getElementById('financeTxSave').click()")
        await b.wait_for("!document.getElementById('financeTxError').classList.contains('hidden')")
        st = await b.js("""({open: !document.getElementById('financeTxModal').classList.contains('hidden'),
            amount: document.getElementById('financeTxAmount').value,
            concept: document.getElementById('financeTxConcept').value,
            save: !document.getElementById('financeTxSave').disabled})""")
        check(st == {"open": True, "amount": "45", "concept": "Café", "save": True},
              f"offline, saving warns and keeps what was typed ({st})")
        await b.js("window.fetch = window.__fetch")
        await b.js("document.getElementById('financeTxSave').click()")
        await b.wait_for("document.getElementById('financeTxModal').classList.contains('hidden')")
        cafe = [t for t in transactions() if t["concept"] == "Café"]
        check(len(cafe) == 1 and cafe[0]["amount_cents"] == 4500, f"back online, it saves once ({len(cafe)})")
        api.call("DELETE", f"/api/finance/transactions/{cafe[0]['id']}", expect=204)
        await b.js("loadFinance()")
        await b.wait_for("![...document.querySelectorAll('.finance-tx')].some(t => t.textContent.includes('Café'))")

        # Pegar un estado de cuenta: los tacos ya están, la farmacia no
        text = f"Fecha\tConcepto\tCargo\tAbono\n{TODAY}\tTacos\t250.00\t\n{TODAY}\tFarmacia\t120.50\t\n"
        await b.js(f"""(() => {{
            const dt = new DataTransfer();
            dt.setData('text/plain', {json.dumps(text)});
            document.querySelector('.finance-list-card').dispatchEvent(
                new ClipboardEvent('paste', {{clipboardData: dt, bubbles: true, cancelable: true}}));
        }})()""")
        await b.wait_for("!document.getElementById('financeImportModal').classList.contains('hidden')")
        await select_by_text("#financeImportAccount", "Efectivo")
        await b.wait_for("document.querySelectorAll('#financeImportRows tr.duplicate').length === 1")
        st = await b.js("""({summary: document.getElementById('financeImportSummary').textContent,
            dupes: !document.getElementById('financeImportDupesOption').classList.contains('hidden'),
            category: document.querySelectorAll('#financeImportRows tr')[0].children[3].textContent})""")
        check(st["summary"].startswith("1 de 2") and st["dupes"], f"the repeated row is marked and skipped ({st})")
        check(st["category"] == "Comer fuera", f"the category is guessed from the concept ({st['category']})")
        await b.shot("finance_import", full=False)
        await b.js("document.getElementById('financeImportConfirm').click()")
        await b.wait_for("document.getElementById('financeImportModal').classList.contains('hidden')")
        concepts = sorted(t["concept"] for t in transactions())
        check(concepts == ["Farmacia", "Pago de la tarjeta", "Tacos"], f"only the new one was added ({concepts})")

        # Organizar › Fijos: la renta se anota sola hoy
        await b.js("document.getElementById('financeOrganize').click()")
        await b.wait_for("!document.getElementById('financeConfigModal').classList.contains('hidden')")
        await b.js("document.querySelector('#financeConfigMenu [data-open=\"fixed\"]').click()")
        await b.wait_for("document.getElementById('financeConfigTitle').textContent === 'Fijos'")
        await b.wait_for("document.querySelectorAll('#financeFixedCategory option').length > 1")
        await set_value("#financeFixedConcept", "Renta")
        await set_value("#financeFixedAmount", "8000")
        await select_by_text("#financeFixedCategory", "Casa y servicios")
        await b.js("document.getElementById('financeFixedSave').click()")
        await b.wait_for("document.querySelectorAll('#financeFixedList .recurring-item').length === 1")
        fixed = await b.js("document.querySelector('#financeFixedList .recurring-item').textContent")
        check("Renta" in fixed and "cada mes" in fixed, f"the fixed charge is listed ({fixed})")
        # Cuentas: la tarjeta con sus últimos 4
        await b.js("document.getElementById('financeConfigBack').click()")
        await b.js("document.querySelector('#financeConfigMenu [data-open=\"accounts\"]').click()")
        await b.wait_for("document.querySelectorAll('#financeAccountList .config-row').length === 2")
        accounts = await b.js("[...document.querySelectorAll('#financeAccountList .config-row')].map(r => r.textContent)")
        check(any("•1234" in a for a in accounts), f"the card shows only its last 4 digits ({accounts})")
        await asyncio.sleep(0.4)   # la página entra deslizándose: medir cuando ya llegó
        wide = await b.js("(() => { const c = document.querySelector('#financeConfigModal .modal-content'); return [c.scrollWidth, c.clientWidth]; })()")
        check(wide[0] <= wide[1], f"Organizar has no sideways scroll on a phone ({wide})")
        await b.shot("finance_accounts", full=False)
        await b.js("document.getElementById('financeConfigClose').click()")
        await b.wait_for("[...document.querySelectorAll('.finance-tx')].some(t => t.textContent.includes('🔁 Renta'))")
        check(True, "the fixed charge shows in the list with its repeat mark")

        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"no horizontal overflow on a phone ({wide}px)")
        await b.shot("finance_mobile_light")
        await b.js("document.documentElement.setAttribute('data-theme', 'dark')")
        await asyncio.sleep(0.2)
        await b.shot("finance_mobile_dark")
        await b.js("document.documentElement.setAttribute('data-theme', 'light')")

        # Configuración › Finanzas: cambiar a mes
        await b.js("openSettings('finance')")
        await b.wait_for("document.querySelector('#financePeriodToggle [data-period=\"biweekly\"]').getAttribute('aria-pressed') === 'true'")
        await b.js("document.querySelector('#financePeriodToggle [data-period=\"month\"]').click()")
        await wait_api("/api/finance/settings", lambda body: body["period"] == "month")
        await b.js("document.getElementById('settingsClose').click()")
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                  "noviembre", "diciembre"]
        expected = f"{months[date.today().month - 1].capitalize()} {date.today().year}"
        label = await b.wait_for("document.getElementById('financePeriodLabel').textContent", lambda t: t == expected)
        check(label == expected, f"the label follows the new period ({label})")

        # Apagarlo: la pestaña se va, los datos se quedan
        await b.js("openSettings('modules')")
        await b.js("document.getElementById('moduleFinance').click()")
        await wait_api("/api/auth/me", lambda body: not body["modules"]["finance"]["enabled"])
        await b.wait_for("document.getElementById('tabFinance').hidden")
        check(await b.js("document.getElementById('tabFinance').hidden"), "turning it off hides the tab")
        await b.js("document.getElementById('settingsClose').click()")
        api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)
        check(len(transactions()) == 4, "and keeps every movement")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_finance():
    asyncio.run(main())
