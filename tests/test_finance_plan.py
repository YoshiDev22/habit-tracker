"""Finanzas: el plan de pagos del mes (Finanzas 0.9). Por fecha, lo que hay que pagar
(tarjetas, préstamos, fijos) y lo que entra, más los aproximados del presupuesto que el
usuario elige. Nada cuenta dos veces, y nunca cambia el presupuesto."""
from datetime import date, timedelta

import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.models import FinPlanChoice
from test_personal_finance import setup, tx, user_id

PLAN = "/api/finance/budget/plan"


def get_plan(api, month=None, expect=200):
    return api.call("GET", PLAN + (f"?month={month.isoformat()}" if month else ""), expect=expect)[1]


def first_of_next(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def by_kind(plan, kind):
    return [e for e in plan["entries"] if e["kind"] == kind]


@pytest.mark.parametrize("day", [None, 10, 25])
def test_the_plan_of_this_month_and_the_next(api, monkeypatch, day):
    """Con el día de hoy, y con el 10 y el 25 (antes y después de la fecha límite de la tarjeta)."""
    cash, debit, credit, cats = setup(api, "plan@test.com")
    if day:
        from backend.routers import finance_budget
        fixed_today = date.today().replace(day=day)
        monkeypatch.setattr(finance_budget, "_today", lambda session, user: fixed_today)
    today = date.fromisoformat(get_plan(api)["today"])
    nm = first_of_next(today)
    api.call("POST", "/api/finance/transactions", tx(debit, 1_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=today), expect=201)
    _, card = api.call("POST", "/api/finance/accounts", {
        "name": "Tarjeta", "kind": "credit", "statement_day": 1, "due_day": 20, "opening_balance_cents": -100_000,
        "opening_date": (today - timedelta(days=90)).isoformat()}, expect=201)
    _, loan = api.call("POST", "/api/finance/accounts", {
        "name": "Préstamo", "kind": "loan", "debt_type": "bank", "opening_balance_cents": -500_000,
        "opening_date": (today - timedelta(days=60)).isoformat(), "loan_payment_cents": 80_000, "due_day": 10},
        expect=201)

    def fixed(account, category, concept, amount, start, kind="expense"):
        return api.call("POST", "/api/finance/recurring", {
            "kind": kind, "account_id": account["id"], "category_id": category["id"], "concept": concept,
            "amount_cents": amount, "start_date": start.isoformat()}, expect=201)[1]

    rent = fixed(debit, cats["Casa y servicios"], "Renta", 300_000, nm.replace(day=5))
    fixed(card, cats["Suscripciones"], "Streaming", 20_000, nm)           # va dentro del pago de la tarjeta
    fixed(debit, cats["Sueldo"], "Sueldo", 900_000, nm.replace(day=15), kind="income")
    _, group = api.call("POST", "/api/finance/budget/groups", {"name": "Necesidades", "percent_bp": 5000}, expect=201)
    _, food = api.call("POST", "/api/finance/budget/items", {"group_id": group["id"], "name": "Súper",
                                                             "amount_cents": 400_000,
                                                             "category_id": cats["Súper"]["id"]}, expect=201)
    _, rent_line = api.call("POST", "/api/finance/budget/items", {"group_id": group["id"], "name": "Renta",
                                                                  "amount_cents": 300_000, "recurring_id": rent["id"]},
                            expect=201)

    # ---- Este mes ----
    plan = get_plan(api)
    assert plan["current"] and plan["month"] == today.replace(day=1).isoformat()
    assert plan["start"] == [{"currency": "MXN", "cents": 1_000_000}], "cash and debit only, not the card or loan"
    assert not by_kind(plan, "fixed"), "the fixed ones start next month"
    [loan_entry] = by_kind(plan, "loan")
    assert (loan_entry["pending_cents"], loan_entry["tx_date"], loan_entry["source"]) == \
        (80_000, today.replace(day=10).isoformat(), "payment")
    cards = by_kind(plan, "card")
    if today.day <= 20:
        [this] = cards
        assert (this["pending_cents"], this["source"], this["cut_date"]) == \
            (100_000, "calculated", today.replace(day=1).isoformat())
    else:
        assert not cards, "this month's payment is past and nothing was paid"
    [estimate] = by_kind(plan, "estimate")
    assert estimate["ref_id"] == food["id"], "a budget line that is a fixed one is not an estimate"
    assert not estimate["included"] and estimate["pending_cents"] == 0, "the user picks which estimates go in"

    # Elegir el aproximado y cambiar su monto solo para este mes
    url = f"{PLAN}/items/{food['id']}"
    plan = api.call("PUT", url, {"month": today.isoformat(), "included": True, "amount_cents": 300_000}, expect=200)[1]
    [estimate] = by_kind(plan, "estimate")
    assert (estimate["included"], estimate["amount_cents"], estimate["budget_cents"], estimate["pending_cents"]) == \
        (True, 300_000, 400_000, 300_000)
    lines = api.call("GET", "/api/finance/budget", expect=200)[1]["items"]
    assert next(i for i in lines if i["id"] == food["id"])["amount_cents"] == 400_000, "the budget never changes"
    # Lo gastado en su categoría este mes ya no falta
    api.call("POST", "/api/finance/transactions", tx(debit, 100_000, "Súper", cats["Súper"], day=today), expect=201)
    plan = get_plan(api)
    [estimate] = by_kind(plan, "estimate")
    assert (estimate["spent_cents"], estimate["pending_cents"]) == (100_000, 200_000)
    assert plan["start"][0]["cents"] == 900_000
    this_month = plan
    assert api.call("PUT", f"{PLAN}/items/{rent_line['id']}", {"month": today.isoformat(), "included": True})[0] == 422

    # ---- El mes siguiente ----
    plan = get_plan(api, nm)
    assert not plan["current"]
    left_now = sum(e["pending_cents"] * (1 if e["direction"] == "in" else -1) for e in this_month["entries"])
    assert plan["start"][0]["cents"] == 900_000 + left_now, "it starts with what would be left of this month"
    fixed_entries = {(e["name"], e["direction"], e["tx_date"], e["pending_cents"], e["account_name"])
                     for e in by_kind(plan, "fixed")}
    assert fixed_entries == {("Renta", "out", nm.replace(day=5).isoformat(), 300_000, "Débito"),
                             ("Sueldo", "in", nm.replace(day=15).isoformat(), 900_000, "Débito")}, \
        "a fixed one charged to the card goes inside the card payment"
    [card_entry] = by_kind(plan, "card")
    assert card_entry["source"] == "estimated" and card_entry["tx_date"] == nm.replace(day=20).isoformat()
    # El estimado: lo que se debe hoy más el fijo que se carga antes del corte, menos lo que ya pide este mes
    assert card_entry["pending_cents"] == (20_000 if today.day <= 20 else 120_000)
    assert by_kind(plan, "loan")[0]["pending_cents"] == 80_000
    [estimate] = by_kind(plan, "estimate")
    assert not estimate["included"] and estimate["amount_cents"] == 400_000, "each month is chosen apart"
    dates = [e["tx_date"] for e in plan["entries"] if e["tx_date"]]
    assert dates == sorted(dates) and plan["entries"][-1]["kind"] == "estimate"

    # Pagar el préstamo: hecho este mes, pendiente el siguiente
    api.call("POST", "/api/finance/transactions", {**tx(debit, 80_000, "Pago", kind="transfer", to=loan, day=today),
                                                   "interest_cents": 10_000}, expect=201)
    [loan_entry] = by_kind(get_plan(api), "loan")
    assert (loan_entry["status"], loan_entry["pending_cents"]) == ("done", 0)
    assert by_kind(get_plan(api, nm), "loan")[0]["pending_cents"] == 80_000

    # Solo este mes y el siguiente
    get_plan(api, first_of_next(nm), expect=422)
    get_plan(api, today.replace(day=1) - timedelta(days=1), expect=422)

    # Borrar el renglón se lleva lo elegido
    api.call("DELETE", f"/api/finance/budget/items/{food['id']}", expect=204)
    with Session(engine) as session:
        assert not session.exec(select(FinPlanChoice).where(FinPlanChoice.user_id == user_id("plan@test.com"))).all()


def test_only_expenses_are_estimates(api):
    """El ingreso del presupuesto suele ser el mismo sueldo que ya entra como fijo: no se elige."""
    setup(api, "ingreso@test.com")
    _, income = api.call("POST", "/api/finance/budget/items", {"kind": "income", "name": "Sueldo",
                                                               "amount_cents": 1_000_000}, expect=201)
    plan = get_plan(api)
    assert not by_kind(plan, "estimate")
    assert api.call("PUT", f"{PLAN}/items/{income['id']}", {"month": plan["month"], "included": True})[0] == 422
