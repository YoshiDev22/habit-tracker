"""Finanzas: dar de baja una tarjeta (Finanzas 0.8, BACKLOG 47)."""
from datetime import timedelta

from test_personal_finance import TODAY, setup, tx

URL = "/api/finance/accounts"


def days_ago(n):
    return TODAY - timedelta(days=n)


def balance(api, account):
    rows = api.call("GET", URL, expect=200)[1]["accounts"]
    return next(a for a in rows if a["id"] == account["id"])


def expenses(api):
    return api.call("GET", "/api/finance/summary?all=true", expect=200)[1]["totals"]


def finance_bell(api):
    return [n for n in api.call("GET", f"/api/notices?today={TODAY.isoformat()}&finance=true", expect=200)[1]["notices"]
            if n["kind"] == "fixed_cancelled"]


def test_msi_paid_off_early_never_moves_the_balance(api):
    """10k a 10 meses: 6k pagados, los 4k que faltan transferidos después y la baja unos
    días más tarde. El saldo queda en 0 y nada suma ni resta los meses que el plan no pidió."""
    cash, debit, credit, cats = setup(api, "msi@test.com")
    _, card = api.call("POST", URL, {"name": "Plata", "kind": "credit", "statement_day": 5, "due_day": 25},
                       expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 2_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=days_ago(200)), expect=201)
    _, buy = api.call("POST", "/api/finance/transactions", tx(card, 1_000_000, "Compra", cats["Personal"],
                                                              day=days_ago(180)), expect=201)
    _, plan = api.call("POST", "/api/finance/installments", {"transaction_id": buy["id"], "months": 10}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 600_000, "Seis meses", kind="transfer", to=card,
                                                     day=days_ago(30)), expect=201)
    assert balance(api, card)["balance_cents"] == -400_000
    api.call("POST", "/api/finance/transactions", tx(debit, 400_000, "Lo que faltaba", kind="transfer", to=card,
                                                     day=days_ago(5)), expect=201)
    assert balance(api, card)["balance_cents"] == 0
    before = expenses(api)
    assert [t["expense_cents"] for t in before] == [1_000_000], "the purchase counted whole, the day it was made"

    _, done = api.call("POST", f"{URL}/{card['id']}/cancel", {"cancelled_on": days_ago(2).isoformat()}, expect=200)
    assert not done["is_active"] and done["cancelled_on"] == days_ago(2).isoformat() and done["balance_cents"] == 0
    assert balance(api, card)["balance_cents"] == 0 and balance(api, debit)["balance_cents"] == 1_000_000
    assert expenses(api) == before, "cancelling never adds or removes an expense"
    [after] = [p for p in api.call("GET", "/api/finance/installments", expect=200)[1]["installments"] if p["id"] == plan["id"]]
    assert after["remaining_cents"] == 0 and after["next_statement"] is None
    assert all(b["cut"] <= days_ago(2).isoformat() for b in after["bills"]) and len(after["bills"]) < 10
    # Reactivarla deshace la baja
    _, back = api.call("PATCH", f"{URL}/{card['id']}", {"is_active": True}, expect=200)
    assert back["is_active"] and back["cancelled_on"] is None


def test_a_card_is_settled_before_it_is_cancelled(api):
    cash, debit, credit, cats = setup(api, "baja@test.com")
    api.call("POST", "/api/finance/transactions", tx(debit, 100_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=days_ago(20)), expect=201)
    # Con deuda: pide desde qué cuenta se pagó, y la anota con su fecha
    _, owed = api.call("POST", URL, {"name": "Debe", "kind": "credit"}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(owed, 50_000, "Súper", cats["Súper"], day=days_ago(10)), expect=201)
    status, body = api.call("POST", f"{URL}/{owed['id']}/cancel", {"cancelled_on": TODAY.isoformat()})
    assert status == 409 and "Aún debes $500.00" in body["detail"]
    api.call("POST", f"{URL}/{owed['id']}/cancel", {"cancelled_on": TODAY.isoformat(), "settle_account_id": debit["id"],
                                                    "settle_date": days_ago(1).isoformat()}, expect=200)
    pays = [t for t in api.call("GET", f"/api/finance/transactions?date_from={days_ago(30).isoformat()}"
                                       f"&date_to={TODAY.isoformat()}", expect=200)[1]["transactions"]
            if t["to_account_id"] == owed["id"]]
    assert [(p["amount_cents"], p["account_id"], p["tx_date"]) for p in pays] == [(50_000, debit["id"], days_ago(1).isoformat())]
    assert balance(api, owed)["balance_cents"] == 0 and balance(api, debit)["balance_cents"] == 50_000

    # Con saldo a favor: pide a dónde va
    _, favor = api.call("POST", URL, {"name": "A favor", "kind": "credit"}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 30_000, "Pagué de más", kind="transfer", to=favor), expect=201)
    status, body = api.call("POST", f"{URL}/{favor['id']}/cancel", {"cancelled_on": TODAY.isoformat()})
    assert status == 409 and "$300.00 a favor" in body["detail"]
    api.call("POST", f"{URL}/{favor['id']}/cancel", {"cancelled_on": TODAY.isoformat(), "settle_account_id": cash["id"]},
             expect=200)
    assert balance(api, favor)["balance_cents"] == 0 and balance(api, cash)["balance_cents"] == 30_000

    # Las reglas
    _, other = api.call("POST", URL, {"name": "Otra", "kind": "credit"}, expect=201)
    assert api.call("POST", f"{URL}/{other['id']}/cancel", {"cancelled_on": (TODAY + timedelta(days=1)).isoformat()})[0] == 422
    assert api.call("POST", f"{URL}/{debit['id']}/cancel", {"cancelled_on": TODAY.isoformat()})[0] == 422
    assert api.call("POST", f"{URL}/{owed['id']}/cancel", {"cancelled_on": TODAY.isoformat()})[0] == 409, "already archived"
    assert api.call("POST", f"{URL}/{other['id']}/cancel", {"cancelled_on": TODAY.isoformat(), "fixed_action": "x"})[0] == 422


def test_fixed_charges_move_or_wait_with_a_reminder(api):
    cash, debit, credit, cats = setup(api, "fijos@test.com")
    fixed = {"kind": "expense", "category_id": cats["Suscripciones"]["id"], "concept": "Streaming",
             "amount_cents": 19_900, "frequency": "monthly", "start_date": (TODAY + timedelta(days=10)).isoformat()}
    _, card = api.call("POST", URL, {"name": "Con fijo", "kind": "credit"}, expect=201)
    _, rc = api.call("POST", "/api/finance/recurring", {**fixed, "account_id": card["id"]}, expect=201)
    status, body = api.call("POST", f"{URL}/{card['id']}/cancel", {"cancelled_on": TODAY.isoformat()})
    assert status == 409 and "fijo" in body["detail"]

    # Dejarlo para después: se pausa, y la campana de Finanzas lo recuerda
    api.call("POST", f"{URL}/{card['id']}/cancel", {"cancelled_on": TODAY.isoformat(), "fixed_action": "pause"},
             expect=200)
    rows = {r["id"]: r for r in api.call("GET", "/api/finance/recurring", expect=200)[1]["recurring"]}
    assert rows[rc["id"]]["paused"]
    [notice] = finance_bell(api)
    assert notice["status"] == "pending" and notice["recurring_id"] == rc["id"] and "Con fijo" in notice["detail"]
    assert not [n for n in api.call("GET", f"/api/notices?today={TODAY.isoformat()}", expect=200)[1]["notices"]
                if n["kind"] == "fixed_cancelled"], "not in Habit Tracker's bell"
    # No se reanuda en la tarjeta dada de baja; con otra cuenta, sí, y el aviso queda hecho
    assert api.call("PATCH", f"/api/finance/recurring/{rc['id']}", {"paused": False})[0] == 409
    api.call("PATCH", f"/api/finance/recurring/{rc['id']}", {"paused": False, "account_id": debit["id"]}, expect=200)
    assert finance_bell(api)[0]["status"] == "done"

    # Pasarlos a otra cuenta al darla de baja
    _, card2 = api.call("POST", URL, {"name": "Otra", "kind": "credit"}, expect=201)
    _, rc2 = api.call("POST", "/api/finance/recurring", {**fixed, "account_id": card2["id"]}, expect=201)
    assert api.call("POST", f"{URL}/{card2['id']}/cancel", {"cancelled_on": TODAY.isoformat(),
                                                            "fixed_action": "move"})[0] == 422
    api.call("POST", f"{URL}/{card2['id']}/cancel", {"cancelled_on": TODAY.isoformat(), "fixed_action": "move",
                                                     "fixed_account_id": cash["id"]}, expect=200)
    rows = {r["id"]: r for r in api.call("GET", "/api/finance/recurring", expect=200)[1]["recurring"]}
    assert rows[rc2["id"]]["account_id"] == cash["id"] and not rows[rc2["id"]]["paused"]
