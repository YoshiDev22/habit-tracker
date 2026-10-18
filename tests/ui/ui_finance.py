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
        # La primera vez, el consentimiento: hasta aceptarlo, la API no da nada
        await b.wait_for("!!document.getElementById('finConsent') && !document.getElementById('finConsent').hidden")
        check(api.call("GET", "/api/finance/accounts")[0] == 403, "without consent the API gives nothing")
        check(await b.js("document.getElementById('finAsk').hidden"), "nothing else shows before consent")
        await b.shot("finance_consent", full=False)
        await b.js("document.getElementById('finConsentAccept').click()")
        await wait_api("/api/finance/consent", lambda body: body["consent_at"] is not None)
        await b.wait_for("!!document.getElementById('finAsk') && !document.getElementById('finAsk').hidden")
        check(await b.js("document.getElementById('finConsent').hidden"), "accepting hides the consent screen")
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

        # La tarjeta dice cuánto pagar para no generar intereses, y se paga desde ahí
        await b.js("document.querySelector('#finNav [data-tab=\"accounts\"]').click()")
        await b.js("document.querySelector('#finAccountTabs [data-sub=\"cards\"]').click()")
        statement = api.call("GET", f"/api/finance/accounts/{card['id']}/statement", expect=200)[1]
        shown = await b.wait_for("(document.querySelector('.fin-statement-pay strong') || {}).textContent",
                                 lambda v: v and ("$" in v or v == "Pagado"))
        check(statement["remaining_cents"] == 30000 and "300.00" in (shown or ""),
              f"the card says what to pay before its due date ({shown}, {statement['remaining_cents']})")
        await b.shot("finance_statement", full=False)
        await b.js("document.querySelector('[data-pay-card]').click()")
        await b.wait_for("!document.getElementById('finEntry').classList.contains('hidden')")
        st = await b.js("""({kind: document.getElementById('finEntryKind').textContent,
            expr: document.getElementById('finEntryExpr').textContent,
            to: document.getElementById('finBandToName').textContent})""")
        check(st["kind"] == "Transferencia" and "300" in st["expr"] and st["to"] == "Tarjeta",
              f"Pagar opens a transfer to the card for what is left ({st})")
        chips = await b.js("[...document.querySelectorAll('.fin-pay-option')].map(c => c.textContent)")
        # "Toda la deuda" solo si es más que lo de sin intereses (aquí son iguales: 300)
        debt = -accounts()["Tarjeta"]["balance_cents"]
        check(chips[0].startswith("Sin intereses") and len(chips) == (2 if debt > 30000 else 1),
              f"it offers the no-interest amount, and the whole debt when it is more ({chips}, debt {debt})")
        # Pagar de más: teclear reemplaza el monto propuesto
        await keys(["4", "0", "0"])
        expr = await b.js("document.getElementById('finEntryExpr').textContent")
        check(expr == "$ 400", f"typing replaces the proposed amount ({expr})")
        await keys(["ok"])
        # "Pagado" con el corte en curso; "Nada por ahora" si ya enseña el próximo
        # (la tarjeta se dio de alta hoy: depende del día del mes)
        paid = await b.wait_for("(document.querySelector('.fin-statement-pay strong') || {}).textContent",
                                lambda v: v in ("Pagado", "Nada por ahora"))
        check(paid in ("Pagado", "Nada por ahora"), f"after paying, the card owes nothing for now ({paid})")
        paid_tx = [t for t in transactions() if t["kind"] == "transfer" and t["amount_cents"] == 40000]
        check(len(paid_tx) == 1, f"the payment saved the typed amount, 400 ({len(paid_tx)})")

        # Tocar una cuenta abre su menú: saldo y acciones (no el formulario de alta)
        async def open_menu(name):
            await b.js(f"""[...document.querySelectorAll('#finAccountsBody .fin-account')]
                .find(r => r.querySelector('strong').textContent === {json.dumps(name)}).click()""")
            await b.wait_for("!document.getElementById('finAccountMenu').classList.contains('hidden')")

        await b.js("document.querySelector('#finAccountTabs [data-sub=\"cards\"]').click()")
        await open_menu("Tarjeta")
        st = await b.js("""({acts: [...document.querySelectorAll('#finMenuActions [data-menu-act]')].map(a => a.dataset.menuAct),
            label: document.getElementById('finMenuLabel').textContent,
            form: document.getElementById('finAccountSheet').classList.contains('hidden')})""")
        check(st["acts"] == ["edit", "adjust", "movements", "pay", "expense", "msi"] and st["label"] == "A favor" and st["form"],
              f"a card opens its menu, with what it has in favor after paying more ({st})")
        await b.shot("finance_card_menu", full=False)
        # Meses sin intereses copiados del estado de cuenta: $300 en 3, el pago 2 de 3
        await b.js("document.querySelector('[data-menu-act=\"msi\"]').click()")
        cut_default = await b.wait_for("document.getElementById('finMsiCut').value", lambda v: v)
        check(bool(cut_default), f"the statement's cut comes filled in ({cut_default})")
        await set_value("#finMsiConcept", "Celular")
        await set_value("#finMsiOriginal", "300")
        await set_value("#finMsiPending", "90")
        await set_value("#finMsiMonthly", "100")
        await set_value("#finMsiPart", "2")
        await set_value("#finMsiMonths", "3")
        await b.js("document.querySelector('#finMsiForm [type=\"submit\"]').click()")
        err = await b.wait_for("document.getElementById('finMsiError').textContent", lambda v: v)
        check("No cuadra" in (err or ""), f"a pending balance that does not add up is caught ({err})")
        await set_value("#finMsiPending", "100")
        await b.js("document.querySelector('#finMsiForm [type=\"submit\"]').click()")
        await b.wait_for("document.getElementById('finMsiList').textContent.includes('Celular')")
        item = await b.js("document.getElementById('finMsiList').textContent")
        check("pago 2 de 3" in item and "original" in item, f"the plan reads like the statement ({item})")
        await b.shot("finance_msi", full=False)
        fresh = await b.js("(finState.installments || []).map(p => p.concept)")
        check("Celular" in fresh, f"adding one refreshes the plans Movimientos draws, without reloading ({fresh})")
        plans = [p for p in api.call("GET", "/api/finance/installments", expect=200)[1]["installments"]
                 if p["concept"] == "Celular"]
        check(len(plans) == 1 and plans[0]["transaction_id"] is None and plans[0]["months"] == 3
              and plans[0]["total_cents"] == 30000, f"the debt's months-without-interest are saved ({plans})")
        await b.js("document.querySelector('#finAccountMenu [data-close-sheet]').click()")

        await b.js("document.querySelector('#finAccountTabs [data-sub=\"accounts\"]').click()")
        await open_menu("Efectivo")
        acts = await b.js("[...document.querySelectorAll('#finMenuActions [data-menu-act]')].map(a => a.dataset.menuAct)")
        check(acts == ["edit", "adjust", "movements", "income", "expense", "transfer"], f"cash offers income and more ({acts})")
        await b.shot("finance_account_menu", full=False)
        # Ingreso directo a Efectivo
        await b.js("document.querySelector('[data-menu-act=\"income\"]').click()")
        await b.wait_for("!document.getElementById('finEntry').classList.contains('hidden')")
        st = await b.js("""({kind: document.getElementById('finEntryKind').textContent,
            to: document.getElementById('finBandToName').textContent})""")
        check(st["kind"] == "Ingreso" and st["to"] == "Efectivo", f"Ingreso opens an income into that account ({st})")
        await keys(["1", "0", "0", "0", "ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        income = [t for t in transactions() if t["kind"] == "income" and t["amount_cents"] == 100000]
        cash_id = accounts()["Efectivo"]["id"]
        check(len(income) == 1 and income[0]["account_id"] == cash_id, f"the income went into Efectivo ({income})")
        # Ajustar el saldo al real: cuadra sin crear movimientos (antes, un gasto en
        # otra cuenta, para que el filtro de Movimientos tenga qué dejar fuera)
        cats = {c["name"]: c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]}
        api.call("POST", "/api/finance/transactions", {
            "kind": "expense", "account_id": accounts()["Tarjeta"]["id"], "amount_cents": 7000,
            "tx_date": TODAY.isoformat(), "category_id": cats["Transporte"]["id"], "concept": "Gasolina"}, expect=201)
        before = len(transactions())
        await open_menu("Efectivo")
        await b.js("document.querySelector('[data-menu-act=\"adjust\"]').click()")
        await set_value("#finAdjustAmount", "5000")
        await b.js("document.querySelector('#finAdjustForm [type=\"submit\"]').click()")
        await b.wait_for("document.getElementById('finAccountMenu').classList.contains('hidden')")
        cash = accounts()["Efectivo"]
        check(cash["balance_cents"] == 500000 and len(transactions()) == before,
              f"adjusting sets the real balance without a movement ({cash['balance_cents']})")
        # Sus movimientos, solos
        await open_menu("Efectivo")
        await b.js("document.querySelector('[data-menu-act=\"movements\"]').click()")
        await b.wait_for("!document.getElementById('finTxFilter').hidden")
        st = await b.js("""({label: document.getElementById('finTxFilterLabel').textContent,
            rows: document.querySelectorAll('#finTxList [data-tx-id]').length})""")
        mine = [t for t in transactions() if t["account_id"] == cash_id or t["to_account_id"] == cash_id]
        check(st["label"] == "Solo Efectivo" and st["rows"] == len(mine) and st["rows"] < len(transactions()),
              f"Movimientos shows only that account ({st}, {len(mine)})")
        await b.js("document.getElementById('finTxFilterClear').click()")
        rows = await b.js("document.querySelectorAll('#finTxList [data-tx-id]').length")
        check(rows == len(transactions()), f"the x shows every account again ({rows})")
        # El saldo con el que empieza una cuenta sale en su día, sin contar como ingreso
        api.call("POST", "/api/finance/accounts", {"name": "Nómina", "kind": "debit", "currency": "MXN",
                                                   "opening_balance_cents": 250000,
                                                   "opening_date": TODAY.isoformat()}, expect=201)
        await b.js("finLoad()")
        st = await b.wait_for("""(() => { const r = [...document.querySelectorAll('#finTxList [data-opening-account]')]
            .find(x => x.textContent.includes('Nómina')); return r ? r.textContent : null; })()""", lambda v: v)
        check(st and "Saldo inicial" in st and "2,500.00" in st, f"an account's opening balance shows on its day ({st})")
        await b.js("""[...document.querySelectorAll('#finTxList [data-opening-account]')]
            .find(x => x.textContent.includes('Nómina')).click()""")
        await b.wait_for("!document.getElementById('finAccountMenu').classList.contains('hidden')")
        await b.js("document.querySelector('#finAccountMenu [data-close-sheet]').click()")

        # El ojo oculta el total, y se recuerda
        await b.js("document.getElementById('finEyeBtn').click()")
        st = await b.js("""({total: document.getElementById('finTotal').textContent,
            saved: localStorage.getItem('finance_hide_total')})""")
        check(st["total"] == "•••••" and st["saved"] == "1", f"the eye hides the total ({st})")
        await b.js("document.getElementById('finEyeBtn').click()")
        check("$" in await b.js("document.getElementById('finTotal').textContent"), "and shows it again")

        # Ordenar categorías: ✎, tocar una y luego otra las cambia de lugar
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        names = lambda: [c["name"] for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
                         if c["kind"] == "expense"]
        first, second = names()[:2]
        # El ✎ va arriba, junto a Ajustes, y solo en Categorías
        st = await b.js("""({inTop: !!document.querySelector('.fin-top #finRingEdit'),
            shown: !document.getElementById('finRingEdit').hidden})""")
        check(st["inTop"] and st["shown"], f"the pencil sits in the top bar on Categorías ({st})")
        await b.js("document.querySelector('#finNav [data-tab=\"transactions\"]').click()")
        check(await b.js("document.getElementById('finRingEdit').hidden"), "and only there")
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await b.js("document.getElementById('finRingEdit').click()")
        check(not await b.js("document.getElementById('finRingHint').hidden"), "editing says how to reorder")
        await b.js("document.querySelectorAll('#finRingGrid .fin-cat[data-category-id]')[0].click()")
        await b.js("document.querySelectorAll('#finRingGrid .fin-cat[data-category-id]')[1].click()")
        order = await wait_api("/api/finance/categories",
                               lambda body: [c["name"] for c in body["categories"] if c["kind"] == "expense"][:2] == [second, first])
        check([c["name"] for c in order["categories"] if c["kind"] == "expense"][:2] == [second, first],
              f"two taps swap two categories ({first}, {second})")
        await b.js("document.getElementById('finRingEdit').click()")
        check(await b.js("document.getElementById('finRingHint').hidden"), "the check ends reordering")

        # El CSV de ejemplo se lee completo en la vista previa
        rows = await b.js("""rowsToFinance(parseTable(finSampleCsv()))
            .map(r => [r.kind, r.amount_cents, r.categoryName, r.problem])""")
        check(len(rows) == 5 and all(r[3] is None for r in rows) and rows[0][:2] == ["expense", 125050]
              and rows[4][:2] == ["income", 1500000], f"the sample CSV reads cleanly ({rows})")

        # Enter en las notas también guarda
        await open_category("Transporte")
        await keys(["5", "0"])
        await set_value("#finEntryNotes", "Camión")
        await b.js("""document.getElementById('finEntryNotes').dispatchEvent(
            new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))""")
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        check(any(t["concept"] == "Camión" and t["amount_cents"] == 5000 for t in transactions()),
              "Enter in the notes saves the movement")

        # Una compra a meses con la tarjeta
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await open_category("Personal")
        await b.js("document.getElementById('finBandFrom').click()")
        await b.wait_for("!document.getElementById('finPicker').classList.contains('hidden')")
        await b.js("[...document.querySelectorAll('#finPickerGrid [data-pick-account]')].find(x => x.textContent.includes('Tarjeta')).click()")
        await keys(["1", "2", "0", "0"])
        await b.js("document.querySelector('#finKeypad [data-key=\"date\"]').click()")
        await b.wait_for("!document.getElementById('finDateSheet').classList.contains('hidden')")
        check(not await b.js("document.getElementById('finMsiTile').hidden"), "a card purchase offers months without interest")
        await set_value("#finMsiSelect", "12")
        hint = await b.js("document.getElementById('finMsiHint').textContent")
        check(hint.startswith("12 pagos de $100.00"), f"it says the monthly payment ({hint})")
        await b.js("document.getElementById('finDateDone').click()")
        await set_value("#finEntryNotes", "Laptop")
        await keys(["ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        plans = [p for p in api.call("GET", "/api/finance/installments", expect=200)[1]["installments"]
                 if p["transaction_id"]]
        check(len(plans) == 1 and plans[0]["months"] == 12 and plans[0]["concept"] == "Laptop"
              and plans[0]["monthly_cents"] == 10000, f"the purchase is planned in 12 months ({plans})")

        # Un cargo dividido en dos categorías
        await open_category("Súper")
        await keys(["1", "0", "0", "0"])
        await b.js("document.getElementById('finSplitBtn').click()")
        await b.wait_for("!document.getElementById('finSplitSheet').classList.contains('hidden')")
        await b.js("""(() => {
            const rows = document.querySelectorAll('#finSplitRows .fin-split-row');
            const set = (node, value) => { node.value = value; node.dispatchEvent(new Event('input', {bubbles: true}));
                node.dispatchEvent(new Event('change', {bubbles: true})); };
            set(rows[0].querySelector('input'), '800');
            const salud = [...rows[1].querySelector('select').options].find(o => o.textContent === 'Salud');
            set(rows[1].querySelector('select'), salud.value);
            set(rows[1].querySelector('input'), '200');
        })()""")
        left = await b.js("document.getElementById('finSplitLeft').textContent")
        check(left == "Cuadra con el total.", f"the split adds up to the total ({left})")
        await b.shot("finance_split", full=False)
        await b.js("document.getElementById('finSplitDone').click()")
        band = await b.wait_for("document.getElementById('finBandToName').textContent", lambda v: v == "2 categorías")
        check(band == "2 categorías", f"the band says it is split ({band})")
        await set_value("#finEntryNotes", "Costco")
        await keys(["ok"])
        await b.wait_for("document.getElementById('finEntry').classList.contains('hidden')")
        costco = [t for t in transactions() if t["concept"] == "Costco"]
        check(len(costco) == 1 and costco[0]["category_id"] is None and [x["amount_cents"] for x in costco[0]["splits"]] == [80000, 20000],
              f"one charge, two categories ({costco})")

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

        # Movimientos: por día; tocar uno lo edita
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
        await no_sideways("Movimientos")
        await b.shot("finance_transactions", full=False)

        # Pegar el estado de cuenta: lo repetido sale tachado y no entra
        await b.js("document.getElementById('finImportBtn').click()")
        await b.wait_for("!document.getElementById('finImportModal').classList.contains('hidden')")
        await set_value("#finImportAccount", str(accounts()["Efectivo"]["id"]))
        text = f"Fecha\tConcepto\tMonto\n{TODAY.isoformat()}\tTacos\t-250\n{TODAY.isoformat()}\tFarmacia\t-120.50\n"
        await set_value("#finImportText", text)
        await b.wait_for("document.querySelectorAll('#finImportRows tr.duplicate').length === 1")
        summary_text = await b.js("document.getElementById('finImportSummary').textContent")
        check(summary_text.startswith("1 de 2"), f"the repeated row is skipped ({summary_text})")
        # La vista previa se corrige antes de agregar: concepto, monto y categoría
        salud = [c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"] if c["name"] == "Salud"][0]

        async def edit_cell(field, value):
            await b.js(f"""(() => {{
                const input = document.querySelector('#finImportRows [data-row="1"][data-field="{field}"]');
                input.value = {json.dumps(value)};
                input.dispatchEvent(new Event('change', {{bubbles: true}}));
            }})()""")
            await asyncio.sleep(0.3)

        await edit_cell("concept", "Farmacia del barrio")
        await edit_cell("amount_cents", "130")
        await edit_cell("category", str(salud["id"]))
        await b.shot("finance_import_edit", full=False)
        await b.js("document.getElementById('finImportConfirm').click()")
        await b.wait_for("document.getElementById('finImportModal').classList.contains('hidden')")
        added = [t for t in transactions() if t["concept"] == "Farmacia del barrio"]
        check(len(added) == 1 and added[0]["amount_cents"] == 13000 and added[0]["category_id"] == salud["id"],
              f"the row is added as corrected in the preview ({added})")

        # El ⚙️ abre el panel lateral; Datos exporta e importa
        await b.js("document.getElementById('finMenuBtn').click()")
        await b.wait_for("!document.getElementById('finDrawer').classList.contains('hidden')")
        items = await b.js("[...document.querySelectorAll('#finDrawer .fin-drawer-item')].map(i => i.textContent.trim())")
        check(items == ["Configuración", "Datos", "Aviso de privacidad", "Regresar a Habit Tracker"],
              f"the gear opens a side menu ({items})")
        await b.shot("finance_drawer", full=False)
        await b.js("document.querySelector('#finDrawer [data-drawer=\"data\"]').click()")
        await b.wait_for("!document.getElementById('finDataSheet').classList.contains('hidden')")
        lines = await b.js("finExportLines(finState.transactions)")
        check(lines[0] == "Fecha,Tipo,Cuenta,Hacia cuenta,Categoría,Monto,Moneda,Concepto,Nota,Parte de"
              and any(",D" in line for line in lines[1:]),
              f"the export has its header and marks split parts ({lines[:2]})")

        # Importar el CSV de otra app: cuenta o categoría en una sola columna, y "$" como USD
        # aunque las cuentas sean en pesos
        await b.js("document.getElementById('finDataImportOpen').click()")
        await b.wait_for("!document.getElementById('finDataImportModal').classList.contains('hidden')")
        d = (TODAY - timedelta(days=3)).strftime("%d/%m/%Y")
        other_app = ("FECHA,TIPO,DE CUENTA,A CUENTA/A CATEGORÍA,CANTIDAD,MONEDA,CANTIDAD 2,MONEDA 2,ETIQUETAS,NOTAS\n"
                     f"{d},Gasto,Efectivo,Tienda,15,USD,15,USD,,Agua\n"
                     f"{d},Gasto,Cartera nueva,Regalos,5,USD,5,USD,viaje,Cerillito\n"
                     f"{d},Ingreso,Sueldo,Efectivo,1000,USD,1000,USD,,Quincena\n"
                     f"{d},Transferencia,Efectivo,Cartera nueva,50,USD,50,USD,,Paso\n")
        await set_value("#finDataText", other_app)
        summary_text = await b.wait_for("document.getElementById('finDataSummary').textContent",
                                        lambda v: v and v.startswith("4 de 4"))
        st = await b.js("""({kind: (document.querySelector('#finDataNew [data-new-account]') || {}).value,
            currency: (document.querySelector('#finDataNew [data-currency-map="USD"]') || {}).value,
            text: document.getElementById('finDataNew').textContent})""")
        check(summary_text and st["kind"] == "cash" and "Cartera nueva (MXN)" in st["text"] and "Tienda" in st["text"],
              f"the other app's CSV reads, with the account and categories to create ({summary_text}, {st})")
        check(st["currency"] == "MXN", f"USD that no account uses is taken as the main currency ({st['currency']})")
        # Tal cual: las filas de Efectivo (en pesos) se saltan
        await b.js("""(() => { const s = document.querySelector('#finDataNew [data-currency-map="USD"]');
            s.value = 'USD'; s.dispatchEvent(new Event('change', {bubbles: true})); })()""")
        as_is = await b.wait_for("document.getElementById('finDataSummary').textContent",
                                 lambda v: v and v.startswith("1 de 4"))
        check(bool(as_is), f"keeping USD skips the rows of a peso account ({as_is})")
        await b.js("""(() => { const s = document.querySelector('#finDataNew [data-currency-map="USD"]');
            s.value = 'MXN'; s.dispatchEvent(new Event('change', {bubbles: true})); })()""")
        await b.wait_for("document.getElementById('finDataSummary').textContent", lambda v: v and v.startswith("4 de 4"))
        await b.shot("finance_data_import", full=False)
        await b.js("document.getElementById('finDataConfirm').click()")
        await b.wait_for("document.getElementById('finDataImportModal').classList.contains('hidden')")
        accs = accounts()
        cats = {c["id"]: c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]}
        by = {t["concept"]: t for t in transactions()}
        check(accs.get("Cartera nueva", {}).get("kind") == "cash" and accs["Cartera nueva"]["currency"] == "MXN"
              and cats[by["Agua"]["category_id"]]["name"] == "Tienda"
              and by["Cerillito"]["account_id"] == accs["Cartera nueva"]["id"] and "viaje" in (by["Cerillito"]["note"] or "")
              and by["Quincena"]["kind"] == "income" and by["Quincena"]["account_id"] == accs["Efectivo"]["id"]
              and cats[by["Quincena"]["category_id"]]["name"] == "Sueldo"
              and by["Paso"]["kind"] == "transfer" and by["Paso"]["to_account_id"] == accs["Cartera nueva"]["id"],
              f"the import creates what was missing and lands each row where it goes ({sorted(by)})")
        # Lo mismo otra vez: todo sale repetido y no entra
        await b.js("document.getElementById('finMenuBtn').click()")
        await b.js("document.querySelector('#finDrawer [data-drawer=\"data\"]').click()")
        await b.js("document.getElementById('finDataImportOpen').click()")
        await set_value("#finDataText", other_app)
        again = await b.wait_for("document.getElementById('finDataSummary').textContent",
                                 lambda v: v and v.startswith("0 de 4"))
        check(bool(again), f"importing the same file again skips every row ({again})")
        # El formato propio, con un cargo dividido en dos filas
        own = ("Fecha,Tipo,Cuenta,Hacia cuenta,Categoría,Monto,Moneda,Concepto,Nota,Parte de\n"
               f"{TODAY.isoformat()},Gasto,Efectivo,,Súper,33.00,MXN,Compra mixta,,D9\n"
               f"{TODAY.isoformat()},Gasto,Efectivo,,Personal,22.00,MXN,Compra mixta,,D9\n")
        await set_value("#finDataText", own)
        await b.wait_for("document.getElementById('finDataSummary').textContent",
                         lambda v: v and v.startswith("1 de 1"))
        await b.js("document.getElementById('finDataConfirm').click()")
        await b.wait_for("document.getElementById('finDataImportModal').classList.contains('hidden')")
        mixed = [t for t in transactions() if t["concept"] == "Compra mixta"]
        check(len(mixed) == 1 and mixed[0]["amount_cents"] == 5500 and len(mixed[0]["splits"]) == 2,
              f"rows with the same 'Parte de' become one split charge ({mixed})")

        # Resumen
        await b.js("document.querySelector('#finNav [data-tab=\"overview\"]').click()")
        await b.wait_for("document.querySelectorAll('.fin-catbar').length >= 2")
        st = await b.js("""({bars: [...document.querySelectorAll('.fin-catbar')].map(r => r.textContent),
            columns: document.querySelectorAll('.fin-columns rect').length})""")
        check(st["columns"] >= 1 and any("Comer fuera" in r for r in st["bars"]), f"the overview draws days and categories ({st})")
        await b.shot("finance_overview")
        await no_sideways("Resumen")
        check(await b.js("document.querySelectorAll('.fin-columns-grid').length") == 2, "the chart has its amount axis")

        # El periodo: la semana, siempre y de vuelta al tuyo
        await b.js("document.getElementById('finPeriodLabel').click()")
        await b.wait_for("!document.getElementById('finRangeSheet').classList.contains('hidden')")
        await b.shot("finance_range", full=False)
        await b.js("document.querySelector('#finRangeSheet [data-range=\"week\"]').click()")
        monday = TODAY - timedelta(days=TODAY.weekday())
        summary_week = await wait_api(f"/api/finance/summary?date_from={monday}&date_to={monday + timedelta(days=6)}",
                                      lambda body: True)
        label = await b.wait_for("document.getElementById('finPeriodLabel').textContent",
                                 lambda v: v and v.startswith(str(monday.day)))
        check(label.startswith(str(monday.day)), f"Semana shows this week ({label})")
        await b.js("document.getElementById('finPeriodLabel').click()")
        await b.js("document.querySelector('#finRangeSheet [data-range=\"all\"]').click()")
        label = await b.wait_for("document.getElementById('finPeriodLabel').textContent", lambda v: v == "Siempre")
        prev = await b.js("document.getElementById('finPrev').disabled")
        check(label == "Siempre" and prev, f"Siempre has no arrows ({label}, {prev})")
        await b.js("document.getElementById('finPeriodLabel').click()")
        await b.js("document.querySelector('#finRangeSheet [data-range=\"period\"]').click()")
        await b.wait_for("document.getElementById('finPeriodLabel').textContent !== 'Siempre'")

        # Ajustes: una categoría nueva con su icono; el periodo a mes
        await b.js("document.getElementById('finMenuBtn').click()")
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
        bills = await b.js("finBillsInPeriod(null).map(x => x.plan.concept + ' ' + x.bill.part)")
        check(any(x.startswith("Celular ") for x in bills), f"each monthly payment of a plan shows in Movimientos on its cut ({bills})")

        # En oscuro también
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await b.js("document.documentElement.setAttribute('data-theme', 'dark')")
        await asyncio.sleep(0.2)
        await b.shot("finance_categories_dark", full=False)
        await b.js("document.documentElement.setAttribute('data-theme', 'light')")

        # Corregir el pago con lo que dice el banco (una tarjeta con su corte en curso)
        cut = TODAY - timedelta(days=5)
        while cut.day > 28:
            cut -= timedelta(days=1)
        due = cut + timedelta(days=15)
        while due.day > 28:
            due += timedelta(days=1)
        _, bank_card = api.call("POST", "/api/finance/accounts", {
            "name": "Banco", "kind": "credit", "opening_balance_cents": -200_000,
            "opening_date": (cut - timedelta(days=30)).isoformat(), "statement_day": cut.day, "due_day": due.day},
            expect=201)
        await b.goto(BASE + "/finance", wait=2.5)
        await b.js("document.querySelector('#finNav [data-tab=\"accounts\"]').click()")
        await b.js("document.querySelector('#finAccountTabs [data-sub=\"cards\"]').click()")
        await b.wait_for(f"!!document.querySelector('[data-bank-edit=\"{bank_card['id']}\"]')")
        box = f"document.querySelector('[data-statement-for=\"{bank_card['id']}\"]')"
        st = await b.js(f"""({{open: {box}.querySelector('.fin-statement-more').open,
            seen: {box}.querySelector('[data-bank-edit]').checkVisibility(),
            pay: {box}.querySelector('.fin-statement-pay').checkVisibility()}})""")
        check(not st["open"] and not st["seen"] and st["pay"],
              f"only what to pay shows; the detail waits behind its arrow ({st})")
        await b.js(f"{box}.querySelector('.fin-statement-more > summary').click()")
        seen = await b.js(f"{box}.querySelector('[data-bank-edit]').checkVisibility()")
        check(seen, "the arrow opens the detail")
        await b.js(f"document.querySelector('[data-bank-edit=\"{bank_card['id']}\"]').click()")
        await b.js("""(() => { const input = document.querySelector('.fin-bank-form input');
            input.value = '1500'; document.querySelector('.fin-bank-form [type="submit"]').click(); })()""")
        st = await wait_api(f"/api/finance/accounts/{bank_card['id']}/statement", lambda body: body["from_bank"])
        check(st["from_bank"] and st["pay_no_interest_cents"] == 150_000 and st["estimated_cents"] == 200_000,
              f"the bank's amount replaces the estimate for this cut ({st['pay_no_interest_cents']})")
        facts = await b.wait_for(f"""(document.querySelector('[data-statement-for="{bank_card['id']}"] .fin-statement-facts')
            || {{}}).textContent""", lambda v: v and "según tu estado de cuenta" in v)
        check("según tu estado de cuenta" in (facts or ""), f"the card says where the amount comes from ({facts})")

        # Dada de alta hoy, después de su corte y antes del pago: su menú enseña ESE
        # pago, y el estado de cuenta se desglosa y se corrige ahí mismo
        cut3 = TODAY - timedelta(days=3)
        while cut3.day > 28:
            cut3 -= timedelta(days=1)
        due3 = cut3 + timedelta(days=20)
        while due3.day > 28:
            due3 += timedelta(days=1)
        _, late_card = api.call("POST", "/api/finance/accounts", {
            "name": "Recién", "kind": "credit", "opening_balance_cents": -900_000,
            "statement_day": cut3.day, "due_day": due3.day}, expect=201)
        api.call("POST", "/api/finance/installments", {"account_id": late_card["id"], "concept": "PC",
                                                       "total_cents": 300_000, "months": 3,
                                                       "purchase_date": TODAY.isoformat()}, expect=201)
        await b.js("finLoad()")
        await b.wait_for("[...document.querySelectorAll('#finAccountsBody .fin-account strong')].some(s => s.textContent === 'Recién')")
        await open_menu("Recién")
        line = await b.wait_for("document.getElementById('finMenuStatementPay').textContent",
                                lambda v: v and v.startswith("Pagar"))
        check(line and "6,000.00" in line and str(due3.day) in line,
              f"the card's menu says what to pay for the cut that passed, before its due date ({line})")
        await b.js("document.getElementById('finMenuStatement').click()")
        st = await b.js("""({lines: document.getElementById('finStLines').textContent,
            form: !document.getElementById('finStBankForm').hidden})""")
        check("Deuda al darla de alta" in st["lines"] and "3,000.00" in st["lines"] and st["form"],
              f"the statement breaks down the debt, the months-without-interest and lets you correct it ({st})")
        card_msi = await b.js("[...document.querySelectorAll('#finStExtra .fin-msi-card')].map(c => c.textContent)")
        check(len(card_msi) == 1 and "PC" in card_msi[0] and "$3,000.00" in card_msi[0] and "0 de 3 pagos" in card_msi[0],
              f"each plan shows what is left in big and its payments ({card_msi})")
        await b.shot("finance_card_statement", full=False)
        await set_value("#finStBankAmount", "5500")
        await b.js("document.querySelector('#finStBankForm [type=\"submit\"]').click()")
        st = await wait_api(f"/api/finance/accounts/{late_card['id']}/statement", lambda body: body["from_bank"])
        check(st["remaining_cents"] == 550_000, f"the bank amount from the card's statement is saved ({st['remaining_cents']})")
        line = await b.wait_for("document.getElementById('finStLines').textContent",
                                lambda v: v and "Según tu estado de cuenta" in v)
        check(bool(line), f"and the breakdown says it ({line})")
        await b.js("document.querySelector('#finAccountMenu [data-close-sheet]').click()")

        # Presupuesto: el ingreso empieza con el sueldo (quincenal: dos pagos al mes), los
        # grupos salen de 50/30/20 y se cambian, un renglón estimado, otro hecho fijo, y un
        # fijo que ya existía metido a un grupo. Nada de esto crea movimientos
        cats = {c["name"]: c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]}
        api.call("POST", "/api/finance/recurring", {
            "kind": "income", "account_id": accounts()["Efectivo"]["id"], "category_id": cats["Sueldo"]["id"],
            "concept": "Sueldo", "amount_cents": 1_275_000, "frequency": "semimonthly",
            "start_date": (TODAY + timedelta(days=1)).isoformat()}, expect=201)
        before_tx = len(transactions())
        await b.js("finLoad()")
        await b.js("document.querySelector('#finNav [data-tab=\"budget\"]').click()")
        income = await b.wait_for("(document.querySelector('#finBudget .fin-budget-head strong') || {}).textContent",
                                  lambda v: v and v != "$0.00")
        check(income == "$25,500.00", f"the budget's income starts with the salary, twice a month ({income})")
        await b.js("document.querySelector('[data-budget-template=\"50-30-20\"]').click()")
        await b.wait_for("document.querySelectorAll('.fin-budget-group-head').length === 3")
        # Renombrar el primero y cambiar su %
        await b.js("document.querySelector('.fin-budget-group-head').click()")
        await set_value("#finBudgetGroupName", "Gastos necesarios")
        await set_value("#finBudgetGroupPercent", "45")
        await b.js("document.querySelector('#finBudgetGroupForm [type=\"submit\"]').click()")
        await b.wait_for("document.querySelector('.fin-budget-group-head').textContent.includes('Gastos necesarios')")
        # Un renglón estimado
        await b.js("document.querySelector('[data-budget-add=\"expense\"]').click()")
        await set_value("#finBudgetItemName", "Renta")
        await set_value("#finBudgetItemAmount", "4500")
        await set_value("#finBudgetItemNote", "Va a cuenta")
        await b.js("document.querySelector('#finBudgetItemForm [type=\"submit\"]').click()")
        await b.wait_for("document.getElementById('finBudget').textContent.includes('Renta')")
        # Otro, hecho fijo: pide la categoría, la cuenta y el primer cobro
        await b.js("document.querySelector('[data-budget-add=\"expense\"]').click()")
        await set_value("#finBudgetItemName", "Internet")
        await set_value("#finBudgetItemAmount", "500")
        await b.js("document.getElementById('finBudgetItemFixed').click()")
        await b.js("document.querySelector('#finBudgetItemForm [type=\"submit\"]').click()")
        err = await b.wait_for("document.getElementById('finBudgetItemError').textContent", lambda v: v)
        check("categoría" in (err or ""), f"a fixed one asks for its category ({err})")
        await b.js(f"""(() => {{ const s = document.getElementById('finBudgetItemCategory');
            s.value = '{cats["Casa y servicios"]["id"]}'; }})()""")
        await set_value("#finBudgetFixedDate", (TODAY + timedelta(days=3)).isoformat())
        await b.js("document.querySelector('#finBudgetItemForm [type=\"submit\"]').click()")
        await b.wait_for("document.getElementById('finBudgetItemSheet').classList.contains('hidden')")
        budget = api.call("GET", "/api/finance/budget", expect=200)[1]
        fixed = [r for r in api.call("GET", "/api/finance/recurring", expect=200)[1]["recurring"] if r["concept"] == "Internet"]
        line = next((i for i in budget["items"] if i["name"] == "Internet"), {})
        check(len(fixed) == 1 and line.get("recurring_id") == fixed[0]["id"] and fixed[0]["amount_cents"] == 50000,
              f"Hacer fijo creates the fixed charge and links the line ({line}, {fixed})")
        # El fijo que ya existía (Streaming), metido a un grupo desde "Fijos sin presupuesto"
        group_id = budget["groups"][1]["id"]
        await b.wait_for("!!document.querySelector('[data-budget-loose]')")
        await b.js(f"""(() => {{ const s = document.querySelector('[data-budget-loose]');
            s.value = '{group_id}'; s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()""")
        await b.wait_for("!document.querySelector('[data-budget-loose]')")
        free = await b.wait_for("(document.querySelector('.fin-budget-free') || {}).textContent",
                                lambda v: v and "20,301.00" in v)
        check(bool(free), f"what is left: income minus everything planned (25,500 - 4,500 - 500 - 199) ({free})")
        table = await b.js("document.querySelector('.fin-budget-table').textContent")
        check("45 %" in table and "11,475.00" in table and "Teórico" in table,
              f"the plan's table: each group with its %, theoretical and planned ({table})")
        await b.shot("finance_budget", full=False)
        check(len(transactions()) == before_tx, "the budget never adds movements")

        # El teléfono más angosto común (360px) con la letra más grande: nada se sale de
        # lado en ninguna pestaña ni hoja
        await b.viewport(360, 640, mobile=True)
        await b.js("document.documentElement.setAttribute('data-text-size', 'xlarge')")
        outside = """(() => {
            const w = document.documentElement.clientWidth;
            const out = [...document.querySelectorAll('body *')].filter(e => {
                const r = e.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && (r.right > w + 1 || r.left < -1)
                    && getComputedStyle(e).visibility !== 'hidden';
            }).map(e => (e.id || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right));
            // Y que ningún nombre de la barra de abajo quede cortado
            const cut = [...document.querySelectorAll('.fin-nav-label')]
                .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent);
            return {page: document.documentElement.scrollWidth, out: out.slice(0, 5).concat(cut)};
        })()"""

        async def fits(label):
            await asyncio.sleep(0.4)
            # Lo que entra deslizándose, ya en su lugar
            await b.js("document.getAnimations().forEach(a => a.finish())")
            st = await b.js(outside)
            check(st["page"] <= 360 and not st["out"], f"{label}: fits 360px with the largest text ({st})")

        for tab in ("accounts", "categories", "transactions", "budget", "overview"):
            await b.js(f"document.querySelector('#finNav [data-tab=\"{tab}\"]').click()")
            await fits(tab)
        await b.js("document.querySelector('#finNav [data-tab=\"accounts\"]').click()")
        await b.js("document.querySelector('#finAccountTabs [data-sub=\"cards\"]').click()")
        await fits("accounts › cards")
        await b.shot("finance_cards_xlarge", full=False)
        await b.js("document.querySelector('#finNav [data-tab=\"categories\"]').click()")
        await open_category("Comer fuera")
        await fits("the entry sheet")
        # En un teléfono bajo, el teclado y su ✓ se alcanzan (la hoja se desplaza si hace falta)
        st = await b.js("""(() => {
            const panel = document.querySelector('#finEntry .fin-sheet-panel');
            const ok = [...document.querySelectorAll('#finKeypad [data-key]')].pop();
            panel.scrollTop = panel.scrollHeight;
            const r = ok.getBoundingClientRect();
            return {bottom: Math.round(r.bottom), height: innerHeight, key: ok.dataset.key};
        })()""")
        check(st["bottom"] <= st["height"], f"on a short phone the keypad is reachable ({st})")
        await b.shot("finance_entry_xlarge", full=False)
        await b.js("document.getElementById('finEntryDate').click()")
        await fits("the date sheet")
        await b.goto(BASE + "/finance", wait=2.5)
        await b.js("document.documentElement.setAttribute('data-text-size', 'xlarge')")
        await b.js("document.getElementById('finPeriodLabel').click()")
        await fits("the period sheet")
        await b.shot("finance_range_xlarge", full=False)
        await b.goto(BASE + "/finance", wait=2.5)
        await b.js("document.documentElement.setAttribute('data-text-size', 'xlarge')")
        await b.js("document.getElementById('finMenuBtn').click()")
        await fits("settings")
        await b.js("document.documentElement.removeAttribute('data-text-size')")
        await b.viewport(390, 844, mobile=True)

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
