"""Finanzas personales (épica 37, fase 1): el módulo, cuentas, categorías,
movimientos, fijos y el periodo. test_finance.py es otra cosa: el costeo de
proyectos del plan maker."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.finance import (DEFAULT_CATEGORIES, card_statement, cut_on_or_after, cut_on_or_before, due_after,
                             generate_due, installment_parts)
from backend.models import FinAccount, FinRecurring, User
from backend.series import occurrence, period_bounds
from test_modules import grant

TODAY = date.today()


def finance_on(api, email):
    """Cuenta con Finanzas: acceso dado por el script, módulo encendido y el
    consentimiento dado."""
    api.login(email)
    assert grant("--email", email, "--module", "finance").returncode == 0
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)
    api.call("POST", "/api/finance/consent", expect=200)


def setup(api, email="dinero@test.com"):
    """Finanzas encendido, con Efectivo, una de débito y una de crédito, y las
    categorías de inicio por nombre."""
    finance_on(api, email)
    accounts = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}
    _, debit = api.call("POST", "/api/finance/accounts", {"name": "Débito", "kind": "debit", "last4": "1234"}, expect=201)
    _, credit = api.call("POST", "/api/finance/accounts", {"name": "Crédito", "kind": "credit"}, expect=201)
    cats = {c["name"]: c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]}
    return accounts["Efectivo"], debit, credit, cats


def tx(account, amount, concept, category=None, kind="expense", to=None, day=TODAY):
    return {"kind": kind, "account_id": account["id"], "amount_cents": amount, "tx_date": day.isoformat(),
            "category_id": category["id"] if category else None, "to_account_id": to["id"] if to else None,
            "concept": concept}


def user_id(email):
    with Session(engine) as session:
        return session.exec(select(User.id).where(User.email == email)).one()


def test_needs_the_module(api):
    api.login("sinfinanzas@test.com")
    status, body = api.call("GET", "/api/finance/summary")
    assert status == 403 and "acceso" in body["detail"]
    assert grant("--email", "sinfinanzas@test.com", "--module", "finance").returncode == 0
    status, body = api.call("GET", "/api/finance/accounts")
    assert status == 403 and "Enciende" in body["detail"], "allowed but still off"
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)
    # Encendido, pero sin consentimiento no se guarda ni se enseña nada
    assert api.call("GET", "/api/finance/consent", expect=200)[1] == {"consent_at": None}
    for method, path, body in (("GET", "/api/finance/accounts", None), ("GET", "/api/finance/summary", None),
                               ("POST", "/api/finance/accounts", {"name": "Débito", "kind": "debit"})):
        status, answer = api.call(method, path, body)
        assert status == 403 and "acepta" in answer["detail"], (path, status)
    first = api.call("POST", "/api/finance/consent", expect=200)[1]["consent_at"]
    assert first is not None
    # Aceptar otra vez conserva la primera fecha
    assert api.call("POST", "/api/finance/consent", expect=200)[1]["consent_at"] == first
    assert api.call("GET", "/api/finance/consent", expect=200)[1]["consent_at"] == first
    api.call("GET", "/api/finance/accounts", expect=200)


def test_starts_with_cash_and_the_categories_once(api):
    finance_on(api, "inicio@test.com")
    for _ in range(2):
        accounts = api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]
        cats = api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
    assert [(a["name"], a["kind"], a["is_default"]) for a in accounts] == [("Efectivo", "cash", True)]
    assert [(c["name"], c["kind"], c["icon"]) for c in cats] == [(name, kind, icon) for name, _, kind, icon in DEFAULT_CATEGORIES]
    assert accounts[0]["icon"] == "banknote" and accounts[0]["balance_cents"] == 0


def test_a_credit_purchase_counts_once(api):
    """La aceptación de la fase: efectivo, débito, una compra con crédito y su
    pago. El gasto del mes cuenta la compra una sola vez."""
    cash, debit, credit, cats = setup(api)
    api.call("POST", "/api/finance/transactions", tx(cash, 23000, "Tacos", cats["Comer fuera"]), expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 158050, "Súper", cats["Súper"]), expect=201)
    api.call("POST", "/api/finance/transactions", tx(credit, 49900, "Audífonos", cats["Personal"]), expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 49900, "Pago de la tarjeta", kind="transfer", to=credit),
             expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 1500000, "Quincena", cats["Sueldo"], kind="income"),
             expect=201)

    _, s = api.call("GET", "/api/finance/summary", expect=200)
    assert s["totals"] == [{"currency": "MXN", "expense_cents": 23000 + 158050 + 49900,
                            "income_cents": 1500000, "net_cents": 1500000 - 23000 - 158050 - 49900}]
    by_account = {a["name"]: a for a in s["accounts"]}
    assert by_account["Crédito"]["expense_cents"] == 49900 and by_account["Crédito"]["transfer_in_cents"] == 49900
    assert by_account["Crédito"]["net_cents"] == 0, "the purchase and its payment cancel out on the card"
    assert by_account["Débito"]["transfer_out_cents"] == 49900
    assert by_account["Débito"]["net_cents"] == 1500000 - 158050 - 49900
    by_cat = {c["name"]: c["cents"] for c in s["categories"]}
    assert by_cat == {"Súper": 158050, "Personal": 49900, "Comer fuera": 23000, "Sueldo": 1500000}
    assert s["transactions"] == 5 and s["needs_review"] == 0

    listed = api.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"]
    assert len(listed) == 5 and {t["source"] for t in listed} == {"manual"}
    only_card = api.call("GET", f"/api/finance/transactions?account_id={credit['id']}", expect=200)[1]
    assert sorted(t["concept"] for t in only_card["transactions"]) == ["Audífonos", "Pago de la tarjeta"]



def test_balances_and_credit_cards(api):
    cash, debit, credit, cats = setup(api, "saldos@test.com")
    api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"opening_balance_cents": 1_000_000}, expect=200)
    _, card = api.call("PATCH", f"/api/finance/accounts/{credit['id']}",
                       {"opening_balance_cents": -50_000, "credit_limit_cents": 2_000_000, "statement_day": 5,
                        "due_day": 25, "icon": "credit-card", "color": "#5c6bc0"}, expect=200)
    assert (card["statement_day"], card["due_day"], card["icon"]) == (5, 25, "credit-card")
    api.call("POST", "/api/finance/transactions", tx(debit, 200_000, "Sueldo", cats["Sueldo"], kind="income"), expect=201)
    api.call("POST", "/api/finance/transactions", tx(credit, 30_000, "Súper", cats["Súper"]), expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 50_000, "Pago tarjeta", kind="transfer", to=credit), expect=201)
    api.call("POST", "/api/finance/transactions", tx(cash, 9_900, "Mañana", cats["Otros"], day=TODAY + timedelta(days=1)),
             expect=201)
    accounts = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}
    assert accounts["Débito"]["balance_cents"] == 1_000_000 + 200_000 - 50_000
    # La deuda: lo que se debía, más la compra, menos el pago; lo de mañana aún no cuenta
    assert accounts["Crédito"]["balance_cents"] == -50_000 - 30_000 + 50_000
    assert accounts["Crédito"]["available_cents"] == 2_000_000 - 30_000
    assert accounts["Efectivo"]["balance_cents"] == 0 and accounts["Efectivo"]["available_cents"] is None
    # Límite, corte y pago son solo de crédito
    _, plain = api.call("POST", "/api/finance/accounts", {"name": "Ahorro", "kind": "debit", "statement_day": 3,
                                                          "credit_limit_cents": 100}, expect=201)
    assert plain["statement_day"] is None and plain["credit_limit_cents"] is None
    _, moved = api.call("PATCH", f"/api/finance/accounts/{credit['id']}", {"kind": "debit"}, expect=200)
    assert moved["due_day"] is None and moved["available_cents"] is None
    assert api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"opening_balance_cents": None})[0] == 422


def test_a_charge_split_into_categories(api):
    cash, debit, credit, cats = setup(api, "partes@test.com")
    parts = [{"category_id": cats["Súper"]["id"], "amount_cents": 80_000},
             {"category_id": cats["Salud"]["id"], "amount_cents": 20_000}]
    body = {**tx(credit, 100_000, "Costco"), "category_id": None, "splits": parts}
    _, charge = api.call("POST", "/api/finance/transactions", body, expect=201)
    assert charge["category_id"] is None and charge["splits"] == parts
    # El resumen cuenta cada parte en su categoría; el gasto total, una vez
    _, sm = api.call("GET", "/api/finance/summary", expect=200)
    by_cat = {c["name"]: c["cents"] for c in sm["categories"]}
    assert by_cat["Súper"] == 80_000 and by_cat["Salud"] == 20_000 and sm["totals"][0]["expense_cents"] == 100_000
    # Filtrar por una categoría encuentra el dividido; borrarla con partes es 409
    found = api.call("GET", f"/api/finance/transactions?category_id={cats['Salud']['id']}", expect=200)[1]["transactions"]
    assert [t["id"] for t in found] == [charge["id"]]
    assert api.call("DELETE", f"/api/finance/categories/{cats['Salud']['id']}")[0] == 409

    # Las reglas
    def bad(**changes):
        return api.call("POST", "/api/finance/transactions", {**body, **changes})[0]
    assert bad(amount_cents=99_999) == 422                                     # no suman
    assert bad(splits=parts[:1], amount_cents=80_000) == 422                    # una sola parte
    assert bad(splits=[parts[0], {**parts[0], "amount_cents": 20_000}]) == 422  # categoría repetida
    assert bad(splits=[parts[0], {"category_id": cats["Sueldo"]["id"], "amount_cents": 20_000}]) == 422  # de ingresos
    assert bad(category_id=cats["Otros"]["id"]) == 422                          # categoría y partes
    assert api.call("POST", "/api/finance/transactions",
                    {**tx(debit, 100_000, "x", kind="transfer", to=credit), "splits": parts})[0] == 422

    # Editar: cambiar el monto sin las partes no cuadra; con ellas, sí; null las quita
    url = f"/api/finance/transactions/{charge['id']}"
    assert api.call("PATCH", url, {"amount_cents": 90_000})[0] == 422
    _, edited = api.call("PATCH", url, {"amount_cents": 90_000, "splits": [{**parts[0], "amount_cents": 70_000}, parts[1]]},
                         expect=200)
    assert [p["amount_cents"] for p in edited["splits"]] == [70_000, 20_000]
    assert api.call("PATCH", url, {"splits": None})[0] == 422                    # sin partes pide categoría
    _, plain = api.call("PATCH", url, {"splits": None, "category_id": cats["Súper"]["id"]}, expect=200)
    assert plain["splits"] == [] and plain["category_id"] == cats["Súper"]["id"]
    api.call("DELETE", f"/api/finance/categories/{cats['Salud']['id']}", expect=204)


def test_card_dates():
    assert cut_on_or_before(31, date(2026, 2, 15)) == date(2026, 1, 31)
    assert cut_on_or_before(31, date(2026, 2, 28)) == date(2026, 2, 28)
    assert cut_on_or_after(31, date(2026, 2, 1)) == date(2026, 2, 28)
    assert cut_on_or_after(5, date(2026, 12, 6)) == date(2027, 1, 5)
    assert due_after(date(2026, 1, 31), 20) == date(2026, 2, 20)
    assert due_after(date(2026, 3, 5), 25) == date(2026, 3, 25)
    assert installment_parts(1000, 3) == [334, 333, 333] and sum(installment_parts(99_999, 7)) == 99_999


def test_card_statement_and_installments(api):
    cash, debit, credit, cats = setup(api, "corte@test.com")
    api.call("PATCH", f"/api/finance/accounts/{credit['id']}", {"statement_day": 5, "due_day": 25}, expect=200)
    # Un corte de hace un mes o más, y "hoy" diez días después de él
    cut = cut_on_or_before(5, TODAY - timedelta(days=40))
    today = cut + timedelta(days=10)
    super_ = cats["Súper"]
    api.call("POST", "/api/finance/transactions", tx(credit, 100_000, "Súper", super_, day=cut - timedelta(days=3)), expect=201)
    _, laptop = api.call("POST", "/api/finance/transactions",
                         tx(credit, 1_200_000, "Laptop", cats["Personal"], day=cut - timedelta(days=2)), expect=201)
    _, plan = api.call("POST", "/api/finance/installments", {"transaction_id": laptop["id"], "months": 12}, expect=201)
    assert plan["first_statement"] == cut.isoformat() and plan["monthly_cents"] == 100_000 and plan["concept"] == "Laptop"
    assert api.call("POST", "/api/finance/installments", {"transaction_id": laptop["id"], "months": 6})[0] == 409
    api.call("POST", "/api/finance/transactions", tx(debit, 30_000, "Pago", kind="transfer", to=credit,
                                                     day=cut + timedelta(days=2)), expect=201)
    api.call("POST", "/api/finance/transactions", tx(credit, 5_000, "Café", cats["Comer fuera"], day=cut + timedelta(days=4)),
             expect=201)

    with Session(engine) as session:
        account = session.get(FinAccount, credit["id"])
        st = card_statement(session, account, today)
    # Al corte se debían el súper y la laptop completa; de la laptop solo se factura 1 de 12
    assert st.last_cut == cut and st.due_date == cut.replace(day=25)
    assert st.debt_at_cut_cents == 1_300_000 and st.msi_pending_cents == 1_100_000
    assert st.pay_no_interest_cents == 200_000 and st.paid_since_cut_cents == 30_000 and st.remaining_cents == 170_000
    assert st.cycle_charges_cents == 5_000
    assert [(i.concept, i.part, i.months, i.amount_cents) for i in st.installments] == [("Laptop", 1, 12, 100_000)]

    # La ruta: con hoy de verdad, y 409 sin días; una de débito no es tarjeta
    _, live = api.call("GET", f"/api/finance/accounts/{credit['id']}/statement", expect=200)
    assert live["due_day"] == 25 and live["last_cut"] <= TODAY.isoformat()
    assert api.call("GET", f"/api/finance/accounts/{debit['id']}/statement")[0] == 422
    _, other_card = api.call("POST", "/api/finance/accounts", {"name": "Otra", "kind": "credit"}, expect=201)
    assert api.call("GET", f"/api/finance/accounts/{other_card['id']}/statement")[0] == 409
    assert api.call("POST", "/api/finance/installments", {"account_id": debit["id"], "concept": "x", "total_cents": 300,
                                                          "months": 3, "purchase_date": TODAY.isoformat()})[0] == 422
    # Una sola compra en la lista, con lo que falta; borrar la compra se lleva su plan
    plans = api.call("GET", "/api/finance/installments", expect=200)[1]["installments"]
    assert [p["id"] for p in plans] == [plan["id"]] and plans[0]["remaining_cents"] < 1_200_000
    listed = api.call("GET", f"/api/finance/transactions?date_from={(cut - timedelta(days=5)).isoformat()}"
                             f"&date_to={cut.isoformat()}", expect=200)[1]["transactions"]
    assert [t["installment_id"] for t in listed if t["concept"] == "Laptop"] == [plan["id"]]
    api.call("DELETE", f"/api/finance/transactions/{laptop['id']}", expect=204)
    assert api.call("GET", "/api/finance/installments", expect=200)[1]["installments"] == []


def test_opening_balance_has_a_date(api):
    """El saldo inicial es a un día: los movimientos de antes (meses viejos que
    se cargan después) son historial y no mueven el saldo; los de después sí."""
    cash, debit, credit, cats = setup(api, "saldo-fecha@test.com")
    _, card = api.call("POST", "/api/finance/accounts", {"name": "TDC", "kind": "credit",
                                                         "opening_balance_cents": -1_000_000}, expect=201)
    assert card["opening_date"] == TODAY.isoformat(), "a balance with no day is today's"
    old = TODAY - timedelta(days=40)
    api.call("POST", "/api/finance/transactions", tx(card, 50_000, "Viejo", cats["Súper"], day=old), expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 20_000, "Pago viejo", kind="transfer", to=card, day=old),
             expect=201)
    accounts = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}
    tdc = accounts["TDC"]
    assert tdc["balance_cents"] == -1_000_000, "history before the day leaves the balance alone"
    assert (tdc["before_count"], tdc["before_in_cents"], tdc["before_out_cents"]) == (2, 20_000, 50_000)
    # La de débito no tiene día: su transferencia de entonces sí cuenta
    assert accounts["Débito"]["balance_cents"] == -20_000 and accounts["Débito"]["opening_date"] is None
    # Lo de hoy en adelante sí mueve el saldo, y el historial sigue en el resumen
    api.call("POST", "/api/finance/transactions", tx(card, 10_000, "Hoy", cats["Súper"], day=TODAY), expect=201)
    tdc = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}["TDC"]
    assert tdc["balance_cents"] == -1_010_000
    _, always = api.call("GET", "/api/finance/summary?all=true", expect=200)
    assert always["totals"][0]["expense_cents"] == 60_000
    # Mover el día al principio del historial: todo suma
    api.call("PATCH", f"/api/finance/accounts/{card['id']}", {"opening_date": old.isoformat()}, expect=200)
    tdc = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}["TDC"]
    assert tdc["balance_cents"] == -1_000_000 - 50_000 + 20_000 - 10_000 and tdc["before_count"] == 0
    # Sin día, también; un día futuro, no
    api.call("PATCH", f"/api/finance/accounts/{card['id']}", {"opening_date": None}, expect=200)
    status, err = api.call("PATCH", f"/api/finance/accounts/{card['id']}",
                           {"opening_date": (TODAY + timedelta(days=3)).isoformat()})
    assert status == 422 and "futuro" in err["detail"]
    assert api.call("POST", "/api/finance/accounts", {"name": "Futura", "opening_balance_cents": 100,
                                                      "opening_date": (TODAY + timedelta(days=3)).isoformat()})[0] == 422


def test_migrate_dates_existing_opening_balances(api):
    """migrate.py, al añadir opening_date: las cuentas con saldo inicial lo toman
    del día en que se dieron de alta; las de saldo 0 se quedan sin día."""
    import sqlite3
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import migrate

    finance_on(api, "migra-saldo@test.com")
    _, card = api.call("POST", "/api/finance/accounts", {"name": "TDC", "kind": "credit",
                                                         "opening_balance_cents": -500}, expect=201)
    _, zero = api.call("POST", "/api/finance/accounts", {"name": "Cero", "kind": "debit"}, expect=201)
    connection = sqlite3.connect(engine.url.database)
    try:
        connection.execute("UPDATE fin_accounts SET opening_date = NULL, created_at = '2026-01-05 10:00:00'")
        assert migrate.anchor_opening_balances(connection) == 1
        rows = dict(connection.execute("SELECT id, opening_date FROM fin_accounts").fetchall())
        connection.commit()
    finally:
        connection.close()
    assert rows[card["id"]] == "2026-01-05" and rows[zero["id"]] is None


def _days_for(cut_ago, due_after_cut):
    """Día de corte y de pago con el último corte hace `cut_ago` días y el pago
    `due_after_cut` días después de él (evita los días 29-31, que se recortan)."""
    cut = TODAY - timedelta(days=cut_ago)
    while cut.day > 28:
        cut -= timedelta(days=1)
    due = cut + timedelta(days=due_after_cut)
    while due.day > 28:
        due += timedelta(days=1)
    return cut, due


def test_card_shows_the_next_cut_when_the_payment_passed(api):
    """El caso de una tarjeta dada de alta hoy con su deuda, con el corte y el
    pago del mes ya pasados: enseña el PRÓXIMO corte y su pago, no uno vencido.
    Lo que está a meses en esa deuda no se pide de golpe."""
    cash, debit, credit, cats = setup(api, "tdc-alta@test.com")
    cut, due = _days_for(20, 12)            # cortó hace 20 días; el pago fue hace 8
    _, card = api.call("POST", "/api/finance/accounts", {
        "name": "TDC 1", "kind": "credit", "opening_balance_cents": -1_000_000,
        "statement_day": cut.day, "due_day": due.day}, expect=201)
    _, st = api.call("GET", f"/api/finance/accounts/{card['id']}/statement", expect=200)
    assert st["upcoming"] is True
    assert st["last_cut"] > TODAY.isoformat() and st["due_date"] > st["last_cut"]
    assert st["prev_cut"] == cut.isoformat()
    assert st["debt_at_cut_cents"] == 1_000_000 and st["remaining_cents"] == 1_000_000
    # De esos 10 000, 3 000 son meses que faltan (3 de 1 000): el próximo corte pide solo uno
    _, plan = api.call("POST", "/api/finance/installments", {
        "account_id": card["id"], "concept": "Celular", "total_cents": 300_000, "months": 3,
        "purchase_date": TODAY.isoformat()}, expect=201)
    assert plan["first_statement"] == st["last_cut"] and plan["monthly_cents"] == 100_000
    _, st = api.call("GET", f"/api/finance/accounts/{card['id']}/statement", expect=200)
    assert st["msi_pending_cents"] == 200_000 and st["remaining_cents"] == 800_000
    assert [(i["concept"], i["part"]) for i in st["installments"]] == [("Celular", 1)]
    # Un plan sin compra puede tener un mes; una compra a meses, no
    api.call("POST", "/api/finance/installments", {"account_id": card["id"], "concept": "Última", "total_cents": 500,
                                                   "months": 1, "purchase_date": TODAY.isoformat()}, expect=201)
    _, bought = api.call("POST", "/api/finance/transactions", tx(card, 900, "Tenis", cats["Personal"]), expect=201)
    assert api.call("POST", "/api/finance/installments", {"transaction_id": bought["id"], "months": 1})[0] == 422

    # Dada de alta después del corte, con el pago aún por venir: enseña ESE corte,
    # con la deuda inicial, menos los meses que le quedan, y se corrige con el banco
    cut2, due2 = _days_for(3, 20)
    _, card2 = api.call("POST", "/api/finance/accounts", {
        "name": "TDC 2", "kind": "credit", "opening_balance_cents": -50_000,
        "statement_day": cut2.day, "due_day": due2.day}, expect=201)
    url2 = f"/api/finance/accounts/{card2['id']}/statement"
    _, st2 = api.call("GET", url2, expect=200)
    assert st2["upcoming"] is False and st2["last_cut"] == cut2.isoformat() and st2["due_date"] == due2.isoformat()
    assert st2["debt_at_cut_cents"] == 50_000 and st2["remaining_cents"] == 50_000
    api.call("POST", "/api/finance/installments", {"account_id": card2["id"], "concept": "PC", "total_cents": 30_000,
                                                   "months": 3, "purchase_date": TODAY.isoformat()}, expect=201)
    _, st2 = api.call("GET", url2, expect=200)
    assert st2["msi_pending_cents"] == 30_000 and st2["remaining_cents"] == 20_000
    _, st2 = api.call("PUT", url2, {"cut_date": cut2.isoformat(), "pay_no_interest_cents": 25_000}, expect=200)
    assert st2["from_bank"] and st2["remaining_cents"] == 25_000


def test_the_bank_amount_overrides_the_estimate(api):
    """Lo que pide el estado de cuenta del banco, escrito por el usuario, manda
    sobre el cálculo en el corte en curso; quitarlo vuelve al cálculo."""
    cash, debit, credit, cats = setup(api, "banco@test.com")
    cut, due = _days_for(5, 15)             # cortó hace 5 días; el pago, en 10
    _, card = api.call("POST", "/api/finance/accounts", {
        "name": "TDC", "kind": "credit", "opening_balance_cents": -400_000,
        "opening_date": (cut - timedelta(days=30)).isoformat(),
        "statement_day": cut.day, "due_day": due.day}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 50_000, "Abono", kind="transfer", to=card), expect=201)
    url = f"/api/finance/accounts/{card['id']}/statement"
    _, st = api.call("GET", url, expect=200)
    assert not st["upcoming"] and not st["from_bank"] and st["pay_no_interest_cents"] == 400_000
    assert st["last_cut"] == cut.isoformat() and st["remaining_cents"] == 350_000
    _, st = api.call("PUT", url, {"cut_date": cut.isoformat(), "pay_no_interest_cents": 320_000}, expect=200)
    assert st["from_bank"] and st["pay_no_interest_cents"] == 320_000 and st["estimated_cents"] == 400_000
    assert st["remaining_cents"] == 270_000
    # Corregirlo otra vez reemplaza; otro corte, no
    _, st = api.call("PUT", url, {"cut_date": cut.isoformat(), "pay_no_interest_cents": 300_000}, expect=200)
    assert st["remaining_cents"] == 250_000
    assert api.call("PUT", url, {"cut_date": (cut - timedelta(days=30)).isoformat(),
                                 "pay_no_interest_cents": 1})[0] == 409
    _, st = api.call("DELETE", f"{url}?cut_date={cut.isoformat()}", expect=200)
    assert not st["from_bank"] and st["pay_no_interest_cents"] == 400_000
    # Borrar la tarjeta (sin movimientos) se lleva lo escrito
    _, empty = api.call("POST", "/api/finance/accounts", {
        "name": "Vacía", "kind": "credit", "opening_balance_cents": -1000,
        "opening_date": (cut - timedelta(days=30)).isoformat(), "statement_day": cut.day, "due_day": due.day},
        expect=201)
    api.call("PUT", f"/api/finance/accounts/{empty['id']}/statement",
             {"cut_date": cut.isoformat(), "pay_no_interest_cents": 500}, expect=200)
    api.call("DELETE", f"/api/finance/accounts/{empty['id']}", expect=204)


def test_import_a_whole_history(api):
    """Importar datos trae el historial de otra app de una vez: más de los 500 de
    un estado de cuenta, con transferencias y divididos, o todo o nada."""
    import time
    cash, debit, credit, cats = setup(api, "historial@test.com")
    rows = []
    for i in range(1500):
        day = TODAY - timedelta(days=i % 300)
        if i % 10 == 0:
            rows.append(tx(debit, 1000 + i, f"Pago {i}", kind="transfer", to=credit, day=day))
        elif i % 10 == 1:
            rows.append({**tx(cash, 300, f"Dividido {i}", day=day), "category_id": None,
                         "splits": [{"category_id": cats["Súper"]["id"], "amount_cents": 200},
                                    {"category_id": cats["Personal"]["id"], "amount_cents": 100}]})
        else:
            rows.append(tx(credit, 100 + i, f"Compra {i}", cats["Súper"], day=day))
    start = time.monotonic()
    _, body = api.call("POST", "/api/finance/transactions/import", {"rows": rows}, expect=201)
    assert len(body["transactions"]) == 1500 and time.monotonic() - start < 30
    # Una fila mala y no entra ninguna
    bad = rows[:10] + [tx(cash, 100, "x")]
    assert api.call("POST", "/api/finance/transactions/import", {"rows": bad})[0] == 422
    _, always = api.call("GET", "/api/finance/summary?all=true", expect=200)
    listed = api.call("GET", f"/api/finance/transactions?date_from={always['date_from']}&date_to={TODAY}",
                      expect=200)[1]["transactions"]
    assert len(listed) == 1500


def test_categories_reorder(api):
    cash, debit, credit, cats = setup(api, "orden@test.com")
    expense = [c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
               if c["kind"] == "expense"]
    ids = [c["id"] for c in expense][::-1]
    _, body = api.call("PUT", "/api/finance/categories/order", {"kind": "expense", "ids": ids}, expect=200)
    assert [c["id"] for c in body["categories"] if c["kind"] == "expense"] == ids
    # Todas, una vez cada una
    assert api.call("PUT", "/api/finance/categories/order", {"kind": "expense", "ids": ids[1:]})[0] == 422
    assert api.call("PUT", "/api/finance/categories/order", {"kind": "expense", "ids": ids + ids[:1]})[0] == 422
    income = [c["id"] for c in body["categories"] if c["kind"] == "income"]
    assert api.call("PUT", "/api/finance/categories/order", {"kind": "expense", "ids": ids[1:] + income[:1]})[0] == 404


def test_summary_of_any_range(api):
    cash, debit, credit, cats = setup(api, "rangos@test.com")
    old = TODAY - timedelta(days=500)
    api.call("POST", "/api/finance/transactions", tx(cash, 1_000, "Viejo", cats["Otros"], day=old), expect=201)
    api.call("POST", "/api/finance/transactions", tx(cash, 2_000, "Hoy", cats["Otros"]), expect=201)
    # Un día, un rango y "Siempre" (desde el primer movimiento hasta hoy)
    _, day = api.call("GET", f"/api/finance/summary?date_from={TODAY}&date_to={TODAY}", expect=200)
    assert day["date_from"] == day["date_to"] == TODAY.isoformat() and day["totals"][0]["expense_cents"] == 2_000
    _, always = api.call("GET", "/api/finance/summary?all=true", expect=200)
    assert always["date_from"] == old.isoformat() and always["date_to"] == TODAY.isoformat()
    assert always["totals"][0]["expense_cents"] == 3_000
    # La lista acepta el mismo rango (más de un año)
    listed = api.call("GET", f"/api/finance/transactions?date_from={old}&date_to={TODAY}", expect=200)[1]["transactions"]
    assert sorted(t["concept"] for t in listed) == ["Hoy", "Viejo"]
    assert api.call("GET", f"/api/finance/summary?date_from={TODAY}")[0] == 422
    too_long = TODAY - timedelta(days=3661)
    assert api.call("GET", f"/api/finance/summary?date_from={too_long}&date_to={TODAY}")[0] == 422

def test_transaction_rules(api):
    cash, debit, credit, cats = setup(api, "reglas@test.com")
    _, usd = api.call("POST", "/api/finance/accounts", {"name": "Dólares", "kind": "debit", "currency": "USD"},
                      expect=201)
    post = lambda body: api.call("POST", "/api/finance/transactions", body)
    assert post(tx(cash, 100, "x"))[0] == 422, "an expense needs a category"
    status, err = post(tx(cash, 100, "x", cats["Sueldo"]))
    assert status == 422 and "ingresos" in err["detail"], "an income category on an expense"
    assert post(tx(cash, 100, "x", cats["Súper"], to=debit))[0] == 422
    assert post(tx(cash, 100, "x", kind="transfer"))[0] == 422, "a transfer needs where it goes"
    assert post(tx(cash, 100, "x", cats["Súper"], kind="transfer", to=debit))[0] == 422, "and no category"
    assert post(tx(cash, 100, "x", kind="transfer", to=cash))[0] == 422
    status, err = post(tx(cash, 100, "x", kind="transfer", to=usd))
    assert status == 409 and "monedas" in err["detail"]
    assert post(tx(cash, 0, "x", cats["Súper"]))[0] == 422
    assert post(tx(cash, 100, "   ", cats["Súper"]))[0] == 422

    # Editar comprueba cómo queda: un gasto a transferencia, sin su categoría
    _, t = post(tx(debit, 100, "Pago", cats["Otros"]))
    assert api.call("PATCH", f"/api/finance/transactions/{t['id']}", {"kind": "transfer"})[0] == 422
    _, moved = api.call("PATCH", f"/api/finance/transactions/{t['id']}",
                        {"kind": "transfer", "category_id": None, "to_account_id": credit["id"]}, expect=200)
    assert moved["kind"] == "transfer" and moved["category_id"] is None
    api.call("DELETE", f"/api/finance/transactions/{t['id']}", expect=204)
    assert api.call("DELETE", f"/api/finance/transactions/{t['id']}")[0] == 404


def test_totals_never_mix_currencies(api):
    cash, debit, credit, cats = setup(api, "monedas@test.com")
    _, usd = api.call("POST", "/api/finance/accounts", {"name": "Dólares", "kind": "debit", "currency": "USD"},
                      expect=201)
    api.call("POST", "/api/finance/transactions", tx(cash, 10000, "a", cats["Súper"]), expect=201)
    _, t = api.call("POST", "/api/finance/transactions", tx(usd, 2500, "b", cats["Súper"]), expect=201)
    assert t["currency"] == "USD"
    _, s = api.call("GET", "/api/finance/summary", expect=200)
    assert [(t["currency"], t["expense_cents"]) for t in s["totals"]] == [("MXN", 10000), ("USD", 2500)]
    assert sorted((c["currency"], c["cents"]) for c in s["categories"]) == [("MXN", 10000), ("USD", 2500)]
    # Su moneda ya no cambia
    assert api.call("PATCH", f"/api/finance/accounts/{usd['id']}", {"currency": "MXN"})[0] == 409


def test_accounts_and_categories_rules(api):
    cash, debit, credit, cats = setup(api, "cuentas@test.com")
    assert api.call("POST", "/api/finance/accounts", {"name": "Débito"})[0] == 409
    # Una sola por defecto
    api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"is_default": True}, expect=200)
    accounts = api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]
    assert [a["name"] for a in accounts if a["is_default"]] == ["Débito"]
    assert api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"is_default": False})[0] == 409
    assert api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"is_active": False})[0] == 409
    assert api.call("DELETE", f"/api/finance/accounts/{debit['id']}")[0] == 409
    # Con movimientos se archiva, no se borra
    api.call("POST", "/api/finance/transactions", tx(cash, 100, "x", cats["Súper"]), expect=201)
    status, err = api.call("DELETE", f"/api/finance/accounts/{cash['id']}")
    assert status == 409 and "1 movimiento" in err["detail"]
    _, archived = api.call("PATCH", f"/api/finance/accounts/{cash['id']}", {"is_active": False}, expect=200)
    assert archived["is_active"] is False and archived["tx_count"] == 1
    api.call("DELETE", f"/api/finance/accounts/{credit['id']}", expect=204)
    # last4 se borra con null
    _, d = api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"last4": None}, expect=200)
    assert d["last4"] is None

    # Categorías: con movimientos no se borran; la última de su tipo tampoco
    status, err = api.call("DELETE", f"/api/finance/categories/{cats['Súper']['id']}")
    assert status == 409 and "1 movimiento" in err["detail"]
    assert api.call("POST", "/api/finance/categories", {"name": "Súper"})[0] == 409
    api.call("DELETE", f"/api/finance/categories/{cats['Otros ingresos']['id']}", expect=204)
    status, err = api.call("DELETE", f"/api/finance/categories/{cats['Sueldo']['id']}")
    assert status == 409 and "ingresos" in err["detail"]
    _, renamed = api.call("PATCH", f"/api/finance/categories/{cats['Ocio']['id']}", {"name": "Salidas"}, expect=200)
    assert renamed["name"] == "Salidas" and renamed["kind"] == "expense"


def test_import_is_all_or_nothing(api):
    cash, debit, credit, cats = setup(api, "importar@test.com")
    good = tx(debit, 5000, "Farmacia", cats["Salud"])
    bad = tx(debit, 5000, "Sueldo como gasto", cats["Sueldo"])
    assert api.call("POST", "/api/finance/transactions/import", {"rows": [good, bad]})[0] == 422
    assert api.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"] == []
    _, done = api.call("POST", "/api/finance/transactions/import", {"rows": [good, good]}, expect=201)
    assert [t["source"] for t in done["transactions"]] == ["import", "import"], "two equal rows are two purchases"


def test_period_is_asked_and_measures_the_list(api):
    cash, debit, credit, cats = setup(api, "quincena@test.com")
    assert api.call("GET", "/api/finance/settings", expect=200)[1] == {"period": None}
    _, s = api.call("GET", "/api/finance/summary", expect=200)
    assert s["period"] == "month" and s["period_asked"] is False
    assert (s["date_from"], s["date_to"]) == tuple(d.isoformat() for d in period_bounds("month", TODAY))

    assert api.call("PUT", "/api/finance/settings", {"period": "weekly"})[0] == 422
    api.call("PUT", "/api/finance/settings", {"period": "biweekly"}, expect=200)
    day = date(2026, 2, 20)
    _, s = api.call("GET", f"/api/finance/summary?day={day.isoformat()}", expect=200)
    assert (s["period"], s["period_asked"]) == ("biweekly", True)
    assert (s["date_from"], s["date_to"]) == ("2026-02-16", "2026-02-28")
    assert (s["prev_day"], s["next_day"]) == ("2026-02-01", "2026-03-01")
    api.call("POST", "/api/finance/transactions", tx(cash, 100, "en la quincena", cats["Súper"], day=day), expect=201)
    api.call("POST", "/api/finance/transactions", tx(cash, 100, "la anterior", cats["Súper"], day=date(2026, 2, 15)),
             expect=201)
    _, listed = api.call("GET", f"/api/finance/transactions?day={day.isoformat()}", expect=200)
    assert [t["concept"] for t in listed["transactions"]] == ["en la quincena"]
    assert api.call("GET", "/api/finance/transactions?date_from=2016-01-01&date_to=2027-01-02")[0] == 422   # más de diez años


def test_periods_and_semimonthly_charges():
    assert period_bounds("biweekly", date(2026, 2, 15)) == (date(2026, 2, 1), date(2026, 2, 15))
    assert period_bounds("biweekly", date(2028, 2, 16)) == (date(2028, 2, 16), date(2028, 2, 29))
    assert period_bounds("biweekly", date(2026, 4, 30)) == (date(2026, 4, 16), date(2026, 4, 30))
    assert period_bounds("month", date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))
    # El 15 y el último día, empezando por el primero en o después del inicio
    days = [occurrence(date(2026, 1, 20), "semimonthly", n) for n in range(5)]
    assert days == [date(2026, 1, 31), date(2026, 2, 15), date(2026, 2, 28), date(2026, 3, 15), date(2026, 3, 31)]
    assert occurrence(date(2026, 12, 16), "semimonthly", 1) == date(2027, 1, 15)
    assert occurrence(date(2026, 1, 15), "semimonthly", 0) == date(2026, 1, 15)


def test_recurring_generates_what_is_due_once(api):
    cash, debit, credit, cats = setup(api, "fijos@test.com")
    start = TODAY - timedelta(days=40)
    body = {"kind": "expense", "account_id": debit["id"], "category_id": cats["Casa y servicios"]["id"],
            "concept": "Renta", "amount_cents": 800000, "frequency": "monthly", "start_date": start.isoformat()}
    _, rc = api.call("POST", "/api/finance/recurring", body, expect=201)
    due = [d for d in (occurrence(start, "monthly", n) for n in range(3)) if d <= TODAY]
    rows = lambda: api.call("GET", f"/api/finance/transactions?date_from={start.isoformat()}&date_to={TODAY.isoformat()}",
                            expect=200)[1]["transactions"]
    assert sorted(t["tx_date"] for t in rows()) == [d.isoformat() for d in due]
    assert all(t["source"] == "recurring" and t["recurring_id"] == rc["id"] for t in rows())
    assert rc["generated"] == len(due) and rc["currency"] == "MXN"
    assert len(rows()) == len(due), "asking again does not duplicate"

    # Uno borrado no vuelve
    api.call("DELETE", f"/api/finance/transactions/{rows()[0]['id']}", expect=204)
    assert len(rows()) == len(due) - 1
    # La cuenta y la categoría que usa un fijo no se borran
    assert api.call("DELETE", f"/api/finance/categories/{cats['Casa y servicios']['id']}")[0] == 409
    assert api.call("PATCH", f"/api/finance/accounts/{debit['id']}", {"is_active": False})[0] == 409

    # Pausado no genera; al reanudar, lo de la pausa no se cobra
    api.call("PATCH", f"/api/finance/recurring/{rc['id']}", {"paused": True}, expect=200)
    uid = user_id("fijos@test.com")
    with Session(engine) as session:
        assert generate_due(session, uid, TODAY + timedelta(days=90)) == []

    # El sueldo por quincena
    salary = {**body, "kind": "income", "category_id": cats["Sueldo"]["id"], "concept": "Sueldo",
              "amount_cents": 1500000, "frequency": "semimonthly", "start_date": TODAY.isoformat()}
    _, s = api.call("POST", "/api/finance/recurring", salary, expect=201)
    assert s["generated"] == (1 if TODAY.day in (15, period_bounds("month", TODAY)[1].day) else 0)
    assert api.call("POST", "/api/finance/recurring", {**salary, "frequency": "weekly"})[0] == 422
    assert api.call("POST", "/api/finance/recurring", {**salary, "category_id": cats["Súper"]["id"]})[0] == 422

    # Borrarlo deja sus movimientos sin el 🔁, salvo que se pida
    api.call("DELETE", f"/api/finance/recurring/{rc['id']}", expect=204)
    assert all(t["recurring_id"] is None for t in rows() if t["concept"] == "Renta")
    with Session(engine) as session:
        assert session.get(FinRecurring, rc["id"]) is None



def test_semimonthly_on_other_days():
    # El 14 y el 29: en febrero, el 29 cae en el último día
    days = [occurrence(date(2026, 1, 14), "semimonthly", n, (14, 29)) for n in range(5)]
    assert days == [date(2026, 1, 14), date(2026, 1, 29), date(2026, 2, 14), date(2026, 2, 28), date(2026, 3, 14)]
    assert occurrence(date(2026, 1, 20), "semimonthly", 0, (14, 29)) == date(2026, 1, 29)
    assert occurrence(date(2026, 1, 30), "semimonthly", 0, (14, 29)) == date(2026, 2, 14)
    # El orden en que llegan no importa, y el 31 es el último día
    assert occurrence(date(2026, 4, 1), "semimonthly", 1, (31, 10)) == date(2026, 4, 30)


def test_pay_days_of_a_fortnightly_fixed(api):
    cash, debit, credit, cats = setup(api, "dias@test.com")
    body = {"kind": "income", "account_id": debit["id"], "category_id": cats["Sueldo"]["id"], "concept": "Sueldo",
            "amount_cents": 1000000, "frequency": "semimonthly", "start_date": (TODAY + timedelta(days=1)).isoformat()}
    _, rc = api.call("POST", "/api/finance/recurring", {**body, "first_day": 29, "second_day": 14}, expect=201)
    assert (rc["first_day"], rc["second_day"]) == (14, 29)
    assert financial_day(rc["next_date"]) in (14, 29) or rc["next_date"].endswith("-28")
    assert api.call("POST", "/api/finance/recurring", {**body, "first_day": 14})[0] == 422
    assert api.call("POST", "/api/finance/recurring", {**body, "first_day": 14, "second_day": 14})[0] == 422
    assert api.call("POST", "/api/finance/recurring", {**body, "first_day": 0, "second_day": 14})[0] == 422
    # El 15 y el último son los de siempre; un mensual no guarda días
    _, classic = api.call("POST", "/api/finance/recurring", {**body, "first_day": 15, "second_day": 31}, expect=201)
    assert classic["first_day"] is None and classic["second_day"] is None
    _, monthly = api.call("POST", "/api/finance/recurring",
                          {**body, "frequency": "monthly", "first_day": 1, "second_day": 16}, expect=201)
    assert monthly["first_day"] is None
    # Volverlo mensual olvida los días
    _, rc = api.call("PATCH", f"/api/finance/recurring/{rc['id']}", {"frequency": "monthly"}, expect=200)
    assert rc["first_day"] is None and rc["frequency"] == "monthly"


def financial_day(iso):
    return int(iso[-2:])


def test_changing_or_removing_the_salary_keeps_its_history(api):
    cash, debit, credit, cats = setup(api, "historial@test.com")
    start = TODAY - timedelta(days=75)
    body = {"kind": "income", "account_id": debit["id"], "category_id": cats["Sueldo"]["id"], "concept": "Sueldo",
            "amount_cents": 2000000, "frequency": "monthly", "start_date": start.isoformat()}
    _, rc = api.call("POST", "/api/finance/recurring", body, expect=201)
    url = f"/api/finance/recurring/{rc['id']}"
    rows = lambda: sorted(api.call("GET", f"/api/finance/transactions?date_from={start.isoformat()}"
                                          f"&date_to={TODAY.isoformat()}", expect=200)[1]["transactions"],
                          key=lambda t: t["tx_date"])
    before = [(t["id"], t["tx_date"], t["amount_cents"]) for t in rows()]
    assert len(before) >= 2 and rc["last_charge"] == before[-1][1]

    # De mensual a quincenal: lo anotado no se mueve; la serie sigue después del último cobro
    assert api.call("PATCH", url, {"frequency": "semimonthly", "start_date": before[-1][1]})[0] == 409
    _, rc = api.call("PATCH", url, {"frequency": "semimonthly", "amount_cents": 1000000,
                                    "start_date": (TODAY + timedelta(days=1)).isoformat()}, expect=200)
    assert [(t["id"], t["tx_date"], t["amount_cents"]) for t in rows()] == before
    assert rc["frequency"] == "semimonthly" and rc["next_date"] > TODAY.isoformat()
    with Session(engine) as session:
        made = generate_due(session, user_id("historial@test.com"), TODAY + timedelta(days=40))
        assert len(made) >= 2 and all(t.amount_cents == 1000000 for t in made)
        assert all(t.tx_date.day == 15 or (t.tx_date + timedelta(days=1)).day == 1 for t in made)

    # Quitarlo: lo anotado se queda, con su monto, y no anota más
    api.call("DELETE", url, expect=204)
    after = rows()
    assert [(t["id"], t["tx_date"], t["amount_cents"]) for t in after] == before
    assert all(t["recurring_id"] is None for t in after)
    with Session(engine) as session:
        assert generate_due(session, user_id("historial@test.com"), TODAY + timedelta(days=120)) == []

def test_turning_it_off_keeps_everything(api):
    cash, debit, credit, cats = setup(api, "apagar@test.com")
    api.call("POST", "/api/finance/transactions", tx(cash, 100, "x", cats["Súper"]), expect=201)
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": False}, expect=200)
    assert api.call("GET", "/api/finance/transactions")[0] == 403
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)
    assert len(api.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"]) == 1


def test_deleting_the_account_takes_its_finances(api):
    from backend.accounts import purge_user
    from backend.models import FinAccount, FinCategory, FinSettings, FinTransaction
    cash, debit, credit, cats = setup(api, "seva@test.com")
    api.call("PUT", "/api/finance/settings", {"period": "biweekly"}, expect=200)
    api.call("POST", "/api/finance/transactions", tx(cash, 100, "x", cats["Súper"]), expect=201)
    api.call("POST", "/api/finance/recurring", {"account_id": cash["id"], "category_id": cats["Súper"]["id"],
                                                "concept": "x", "amount_cents": 1,
                                                "start_date": TODAY.isoformat()}, expect=201)
    uid = user_id("seva@test.com")
    with Session(engine) as session:
        purge_user(session, session.get(User, uid))
        for model in (FinAccount, FinCategory, FinTransaction, FinRecurring, FinSettings):
            assert session.exec(select(model).where(model.user_id == uid)).first() is None, model.__name__


def test_seeding_twice_at_once_does_not_fail(api, monkeypatch):
    """La pantalla pide cuentas y resumen a la vez: las dos siembran. La que
    llega segunda choca con la restricción única y no debe tumbar la petición
    ni quedarse sin sembrar las categorías."""
    import backend.finance as finance
    from backend.models import FinAccount, FinCategory
    finance_on(api, "doble@test.com")
    uid = user_id("doble@test.com")
    with Session(engine) as session:
        session.add(FinAccount(user_id=uid, name="Efectivo", kind="cash", is_default=True))
        session.commit()
    # La otra petición: comprobó antes de que la primera guardara, así que cree que no hay nada
    real_exec = Session.exec
    calls = {"n": 0}

    def stale_first_check(self, statement, *args, **kwargs):
        calls["n"] += 1
        result = real_exec(self, statement, *args, **kwargs)
        if calls["n"] == 1:
            class Empty:
                def first(self):
                    return None
            return Empty()
        return result

    monkeypatch.setattr(Session, "exec", stale_first_check)
    with Session(engine) as session:
        finance.ensure_finance_setup(session, uid)
    monkeypatch.undo()
    with Session(engine) as session:
        assert len(session.exec(select(FinAccount).where(FinAccount.user_id == uid)).all()) == 1
        assert len(session.exec(select(FinCategory).where(FinCategory.user_id == uid)).all()) == len(DEFAULT_CATEGORIES)


def test_download_my_data_and_deleting_the_account_cover_finances(api):
    """Descargar mis datos y Borrar mi cuenta recorren cada tabla con user_id: las
    de Finanzas salen en el JSON con sus filas y se van con la cuenta."""
    from test_accounts import PASSWORD, rows_of
    cash, debit, credit, cats = setup(api, "exporta@test.com")
    api.call("PUT", "/api/finance/settings", {"period": "biweekly"}, expect=200)
    api.call("POST", "/api/finance/transactions", tx(credit, 49900, "Audífonos", cats["Personal"]), expect=201)
    api.call("POST", "/api/finance/recurring", {"account_id": debit["id"], "category_id": cats["Casa y servicios"]["id"],
                                                "concept": "Renta", "amount_cents": 800000,
                                                "start_date": TODAY.isoformat()}, expect=201)
    uid = user_id("exporta@test.com")

    _, data = api.call("GET", "/api/auth/me/export", expect=200)
    tables = data["tables"]
    for name in ("fin_accounts", "fin_categories", "fin_transactions", "fin_recurring", "fin_settings"):
        assert tables[name], name
    assert {name: len(rows) for name, rows in tables.items()} == rows_of(uid)
    bought = next(r for r in tables["fin_transactions"] if r["concept"] == "Audífonos")
    assert bought["amount_cents"] == 49900 and bought["account_id"] == credit["id"]
    assert tables["fin_settings"][0]["period"] == "biweekly"

    api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "now", "confirm": "BORRAR"}, expect=204)
    assert sum(rows_of(uid).values()) == 0


def test_the_timer_charges_fixed_and_logs_no_email(api, capsys):
    """El timer diario anota los fijos que llegaron. Su salida va al registro del
    servidor: el número de la cuenta, nunca su correo."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import generate_reports

    cash, debit, credit, cats = setup(api, "timer-fin@test.com")
    due = TODAY + timedelta(days=5)
    api.call("POST", "/api/finance/recurring", {"account_id": debit["id"], "category_id": cats["Suscripciones"]["id"],
                                                "concept": "Streaming", "amount_cents": 19900,
                                                "start_date": due.isoformat()}, expect=201)
    uid = user_id("timer-fin@test.com")
    assert generate_reports.main(["--email", "timer-fin@test.com", "--today", due.isoformat()]) == 0
    out = capsys.readouterr().out
    assert f"fixed charge for account {uid} on {due.isoformat()}" in out and "@" not in out
    # Con el módulo apagado, el timer no anota nada
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": False}, expect=200)
    later = TODAY + timedelta(days=40)
    assert generate_reports.main(["--email", "timer-fin@test.com", "--today", later.isoformat()]) == 0
    assert "fixed charge" not in capsys.readouterr().out
