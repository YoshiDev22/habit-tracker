"""Finanzas como su propia página (/finance): la pestaña de la app lleva a ella; "¿Cada
cuándo cobras?" y el sueldo; tocar una categoría y teclear el monto con la calculadora;
una tarjeta de crédito con su disponible; una transferencia eligiendo una cuenta como
destino; ayer con periodicidad (un fijo); editar y borrar; pegar el estado de cuenta;
el resumen; los ajustes; ‹ regresa a la app; y sin el módulo, /finance regresa a /."""
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import api
from api import login, wait_api
from cdp import Browser

BASE = api.BASE
ROOT = Path(__file__).resolve().parents[2]
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
TODAY = date.today()


def grant(email):
    """scripts/grant_module.py contra la base de esta prueba (conftest: <nombre>.db)."""
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_finance.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), "--email", email,
                             "--module", "finance"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def transactions():
    query = f"?date_from={(TODAY - timedelta(days=40)).isoformat()}&date_to={TODAY.isoformat()}"
    return api.call("GET", f"/api/finance/transactions{query}", expect=200)[1]["transactions"]


def accounts():
    return {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}


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

    async def keys(sequence):
        for key in sequence:
            await b.js(f"document.querySelector('#finKeypad [data-key=\"{key}\"]').click()")

    async def open_category(name):
        await b.js(f"""[...document.querySelectorAll('#finRingGrid .fin-cat')]
            .find(c => c.querySelector('.fin-cat-name').textContent === {json.dumps(name)}).click()""")
        await b.wait_for("!document.getElementById('finEntry').classList.contains('hidden')")

    async def no_sideways(label):
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"{label}: no horizontal overflow on a phone ({wide}px)")

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/api/health")   # mismo origen, sin arrancar la app
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # En la app: sin encender no hay pestaña; encendido, la pestaña es un enlace a /finance
        check(await b.js("document.getElementById('tabFinance').hidden"), "no Finanzas tab while the module is off")
        await b.js("openSettings('modules')")
        await b.wait_for("!document.getElementById('moduleFinanceOption').hidden")
        await b.js("document.getElementById('moduleFinance').click()")
        await wait_api("/api/auth/me", lambda body: body["modules"]["finance"]["enabled"])
        await b.wait_for("!document.getElementById('tabFinance').hidden")
        await b.js("document.getElementById('settingsClose').click()")
        st = await b.js("""({href: document.getElementById('tabFinance').getAttribute('href'),
            tabs: [...document.querySelectorAll('.tabs .tab-btn:not([hidden])')].map(t => t.textContent),
            width: document.querySelector('.tab-indicator').style.width})""")
        check(st["href"] == "/finance" and st["tabs"][-2:] == ["Finanzas", "Reportes"],
              f"the Finanzas tab links to its page, before Reportes ({st})")
        check(st["width"] == "25%", f"the tab line counts the link as one of four tabs ({st['width']})")
        await b.js("document.getElementById('tabFinance').click()")
        await b.wait_for("location.pathname === '/finance'")
        await b.wait_for("!!document.getElementById('finAsk') && !document.getElementById('finAsk').hidden")
        check(await b.js("location.pathname") == "/finance", "tapping it opens /finance with the same session")
        await b.shot("finance_page_ask", full=False)

        # Cada cuándo, y luego cuánto (se puede dejar para después)
        await b.js("document.querySelector('#finAsk [data-period=\"biweekly\"]').click()")
        await wait_api("/api/finance/settings", lambda body: body["period"] == "biweekly")
        await b.wait_for("!document.getElementById('finSalarySheet').classList.contains('hidden')")
        title = await b.js("document.getElementById('finSalaryTitle').textContent")
        check(title == "¿Cuánto cobras cada quincena?", f"then it asks how much ({title})")
        await b.js("document.getElementById('finSalaryLater').click()")
        await b.wait_for("document.getElementById('finSalarySheet').classList.contains('hidden')")
        check(not await b.js("document.getElementById('finSalaryHint').hidden"), "later leaves a quiet way back")

        # Categorías: el anillo y los círculos; tocar uno abre el monto con la calculadora
        st = await b.js("""({cats: document.querySelectorAll('#finRingGrid .fin-cat:not(.fin-cat-add)').length,
            ring: !!document.querySelector('#finRingGrid .fin-ring svg')})""")
        check(st["cats"] == 9 and st["ring"], f"nine expense circles around the ring ({st})")
        await b.shot("finance_categories", full=False)
        await open_category("Comer fuera")
        st = await b.js("""({from: document.getElementById('finBandFromName').textContent,
            to: document.getElementById('finBandToName').textContent,
            date: document.getElementById('finEntryDate').textContent})""")
        check(st["from"] == "Efectivo" and st["to"] == "Comer fuera" and st["date"].startswith("Hoy, "),
              f"the sheet says from where, to which category and today ({st})")
        await keys(["1", "2", "0", "+", "1", "1", "0", "*", "1"])
        result = await b.js("document.getElementById('finEntryResult').textContent")
        check("230.00" in result, f"the keypad adds up (120 + 110 x 1 = {result})")
        await b.shot("finance_entry", full=False)
        await set_value("#finEntryNotes", "Tacos")
        await keys(["ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        tacos = [t for t in transactions() if t["concept"] == "Tacos"]
        check(len(tacos) == 1 and tacos[0]["amount_cents"] == 23000 and tacos[0]["kind"] == "expense",
              f"it saves the expense ({tacos})")
        amount = await b.wait_for("""[...document.querySelectorAll('#finRingGrid .fin-cat')]
            .find(c => c.textContent.includes('Comer fuera')).querySelector('.fin-cat-amount').textContent""",
                                  lambda v: v and "230" in v)
        check("230" in (amount or ""), f"the circle shows what went there ({amount})")

        # Cuentas: una tarjeta de crédito con lo que se debía, su límite, corte y pago
        await b.js("document.querySelector('#finNav [data-tab=\"accounts\"]').click()")
        await b.js("document.querySelector('#finAccountTabs [data-sub=\"cards\"]').click()")
        await b.js("document.querySelector('[data-new-account=\"credit\"]').click()")
        await b.wait_for("!document.getElementById('finAccountSheet').classList.contains('hidden')")
        await set_value("#finAccName", "Tarjeta")
        await set_value("#finAccOpening", "500")
        await set_value("#finAccLimit", "20000")
        await set_value("#finAccStatement", "5")
        await set_value("#finAccDue", "25")
        await b.js("document.getElementById('finAccSave').click()")
        await b.wait_for("document.getElementById('finAccountSheet').classList.contains('hidden')")
        card = accounts().get("Tarjeta", {})
        check(card.get("kind") == "credit" and card.get("balance_cents") == -50000
              and card.get("available_cents") == 1_950_000 and card.get("statement_day") == 5,
              f"the card owes 500 and has 19,500 available ({card})")
        side = await b.wait_for("[...document.querySelectorAll('.fin-account')].map(a => a.textContent).join('|')",
                                lambda v: v and "Disponible" in v)
        check("19,500.00" in side and "Corte: 5" in side, f"the card row shows available, cut and due days ({side})")
        await b.shot("finance_cards", full=False)

        # Una transferencia: en la hoja, el destino puede ser otra cuenta
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await open_category("Otros")
        await b.js("document.getElementById('finBandTo').click()")
        await b.wait_for("!document.getElementById('finPicker').classList.contains('hidden')")
        await b.js("document.querySelector('#finPickerGrid [data-pick-account]').click()")
        kind = await b.wait_for("document.getElementById('finEntryKind').textContent", lambda v: v == "Transferencia")
        check(kind == "Transferencia", f"choosing an account as destination makes it a transfer ({kind})")
        await keys(["2", "0", "0", "ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        card = accounts()["Tarjeta"]
        check(card["balance_cents"] == -30000, f"paying the card lowers its debt, not an expense ({card['balance_cents']})")

        # Ayer, cada mes: se guarda como fijo y el cobro de ayer queda anotado
        await open_category("Suscripciones")
        await keys(["1", "9", "9"])
        await b.js("document.querySelector('#finKeypad [data-key=\"date\"]').click()")
        await b.wait_for("!document.getElementById('finDateSheet').classList.contains('hidden')")
        await b.js("document.querySelector('#finDateSheet [data-day=\"-1\"]').click()")
        await set_value("#finRepeatSelect", "monthly")
        hint = await b.js("document.getElementById('finRepeatHint').textContent")
        yesterday = TODAY - timedelta(days=1)
        check(f"el {yesterday.day} de cada mes" in hint, f"the date sheet says when it repeats ({hint})")
        await b.shot("finance_date", full=False)
        await b.js("document.getElementById('finDateDone').click()")
        await set_value("#finEntryNotes", "Streaming")
        await keys(["ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        fixed = [r for r in api.call("GET", "/api/finance/recurring", expect=200)[1]["recurring"] if r["concept"] == "Streaming"]
        noted = [t for t in transactions() if t["concept"] == "Streaming"]
        check(len(fixed) == 1 and fixed[0]["start_date"] == yesterday.isoformat() and fixed[0]["frequency"] == "monthly",
              f"yesterday, monthly: a fixed ({fixed})")
        check(len(noted) == 1 and fixed and noted[0]["recurring_id"] == fixed[0]["id"], f"and yesterday's charge, once ({noted})")

        # Transacciones: por día; tocar una la edita
        await b.js("document.querySelector('#finNav [data-tab=\"transactions\"]').click()")
        await b.wait_for("document.querySelectorAll('.fin-tx').length >= 2")
        heads = await b.js("[...document.querySelectorAll('.fin-day-head')].map(h => h.textContent)")
        check(heads and heads[0].startswith("Hoy"), f"grouped by day, newest first ({heads})")
        await b.js("[...document.querySelectorAll('.fin-tx')].find(t => t.textContent.includes('Tacos')).click()")
        await b.wait_for("!document.getElementById('finEntryDelete').hidden")
        expr = await b.js("document.getElementById('finEntryExpr').textContent")
        check("230" in expr, f"editing shows its amount ({expr})")
        await keys(["back", "back", "back", "2", "5", "0", "ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        check([t["amount_cents"] for t in transactions() if t["concept"] == "Tacos"] == [25000], "the edit is saved")
        await no_sideways("Transacciones")

        # Pegar el estado de cuenta: lo repetido sale tachado y no entra
        await b.js("document.getElementById('finPasteBtn').click()")
        await b.wait_for("!document.getElementById('finImportModal').classList.contains('hidden')")
        await set_value("#finImportAccount", str(accounts()["Efectivo"]["id"]))
        text = f"Fecha\tConcepto\tMonto\n{TODAY.isoformat()}\tTacos\t-250\n{TODAY.isoformat()}\tFarmacia\t-120.50\n"
        await set_value("#finImportText", text)
        await b.wait_for("document.querySelectorAll('#finImportRows tr.duplicate').length === 1")
        summary_text = await b.js("document.getElementById('finImportSummary').textContent")
        check(summary_text.startswith("1 de 2"), f"the repeated row is skipped ({summary_text})")
        await b.js("document.getElementById('finImportConfirm').click()")
        await b.wait_for("document.getElementById('finImportModal').classList.contains('hidden')")
        check(any(t["concept"] == "Farmacia" and t["amount_cents"] == 12050 for t in transactions()), "the new row is added")

        # Resumen
        await b.js("document.querySelector('#finNav [data-tab=\"overview\"]').click()")
        await b.wait_for("document.querySelectorAll('.fin-catbar').length >= 2")
        st = await b.js("""({bars: [...document.querySelectorAll('.fin-catbar')].map(r => r.textContent),
            columns: document.querySelectorAll('.fin-columns rect').length})""")
        check(st["columns"] >= 1 and any("Comer fuera" in r for r in st["bars"]), f"the overview draws days and categories ({st})")
        await b.shot("finance_overview")
        await no_sideways("Resumen")

        # Ajustes: una categoría nueva con su icono; el periodo a mes
        await b.js("document.getElementById('finSettingsBtn').click()")
        await b.js("document.querySelector('#finSettingsMenu [data-open=\"categories\"]').click()")
        await b.wait_for("document.getElementById('finSettingsTitle').textContent === 'Categorías'")
        await set_value("#finCatName", "Moto")
        await b.js("document.querySelector('#finCatIcons [data-icon=\"bike\"]').click()")
        await b.js("document.getElementById('finCatSave').click()")
        cats = await wait_api("/api/finance/categories", lambda body: any(c["name"] == "Moto" for c in body["categories"]))
        moto = [c for c in cats["categories"] if c["name"] == "Moto"]
        check(moto and moto[0]["icon"] == "bike" and moto[0]["kind"] == "expense", f"a new category with its icon ({moto})")
        await b.js("document.getElementById('finSettingsBack').click()")
        await b.js("document.querySelector('#finSettingsMenu [data-open=\"period\"]').click()")
        await b.js("document.querySelector('#finPeriodToggle [data-period=\"month\"]').click()")
        await wait_api("/api/finance/settings", lambda body: body["period"] == "month")
        await b.js("document.getElementById('finSettingsClose').click()")
        months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                  "noviembre", "diciembre"]
        expected = f"{months[TODAY.month - 1].capitalize()} {TODAY.year}"
        label = await b.wait_for("document.getElementById('finPeriodLabel').textContent", lambda t: t == expected)
        check(label == expected, f"the period label follows the setting ({label})")

        # En oscuro también
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await b.js("document.documentElement.setAttribute('data-theme', 'dark')")
        await asyncio.sleep(0.2)
        await b.shot("finance_categories_dark", full=False)
        await b.js("document.documentElement.setAttribute('data-theme', 'light')")

        # ‹ regresa a la app
        await b.js("document.getElementById('finBack').click()")
        await b.wait_for("location.pathname === '/' && !!document.getElementById('tabFinance')")
        check(await b.js("location.pathname") == "/", "the back arrow goes to the app")

        # Sin el módulo, /finance regresa a la app
        api.call("PUT", "/api/auth/me/modules/finance", {"enabled": False}, expect=200)
        await b.goto(BASE + "/finance", wait=2.5)
        path = await b.wait_for("location.pathname", lambda p: p == "/")
        check(path == "/", f"with the module off, /finance sends you back ({path})")
        api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_finance():
    asyncio.run(main())
