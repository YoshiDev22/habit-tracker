"""Finanzas: el aviso del pago de una tarjeta (Finanzas 0.8, BACKLOG 45)."""
from datetime import timedelta

from test_personal_finance import TODAY, setup, tx

URL = "/api/finance/accounts"


def card_due_in_three_days(api, debit):
    """Una tarjeta con su corte hace 10 días y el pago en 3, que debe $1,000 desde antes del corte."""
    cut, due = TODAY - timedelta(days=10), TODAY + timedelta(days=3)
    _, card = api.call("POST", URL, {"name": "Oro", "kind": "credit", "statement_day": min(cut.day, 28),
                                     "due_day": due.day, "opening_balance_cents": -100_000,
                                     "opening_date": (TODAY - timedelta(days=20)).isoformat()}, expect=201)
    return card


def finance_bell(api):
    return api.call("GET", f"/api/notices?today={TODAY.isoformat()}&finance=true", expect=200)[1]


def card_notices(body):
    return [n for n in body["notices"] if n["kind"] == "card_due"]


def test_a_card_payment_close_to_its_due_date_is_announced(api):
    cash, debit, credit, cats = setup(api, "pago@test.com")
    card = card_due_in_three_days(api, debit)
    st = api.call("GET", f"{URL}/{card['id']}/statement", expect=200)[1]
    assert st["remaining_cents"] == 100_000 and st["due_soon"] == (0 <= st["due_in_days"] <= 5)
    assert st["due_in_days"] == 3 and st["due_soon"]

    # En la campana de Finanzas, pendiente y contado; en la de Habit Tracker, nada
    body = finance_bell(api)
    [notice] = card_notices(body)
    assert notice["status"] == "pending" and notice["amount_cents"] == 100_000 and notice["account_id"] == card["id"]
    assert "Vence en 3 días" in notice["detail"] and "$1,000.00" in notice["detail"]
    assert body["unread"] >= 1
    app = api.call("GET", f"/api/notices?today={TODAY.isoformat()}", expect=200)[1]
    assert not card_notices(app) and app["unread"] == body["unread"] - 1

    # Los ajustes: por defecto 5 días y en la campana; 3 días todavía avisa; apagar la campana lo quita
    assert api.call("GET", "/api/finance/reminder-settings", expect=200)[1] == {"due_days": 5, "due_bell": True}
    api.call("PUT", "/api/finance/reminder-settings", {"due_days": 3, "due_bell": True}, expect=200)
    assert card_notices(finance_bell(api))[0]["status"] == "pending"
    api.call("PUT", "/api/finance/reminder-settings", {"due_days": 3, "due_bell": False}, expect=200)
    assert not card_notices(finance_bell(api))
    assert api.call("GET", f"{URL}/{card['id']}/statement", expect=200)[1]["due_soon"], "the card still turns red"
    api.call("PUT", "/api/finance/reminder-settings", {"due_days": 5, "due_bell": True}, expect=200)
    assert card_notices(finance_bell(api))[0]["status"] == "pending", "turning the bell back on brings it back"
    assert api.call("PUT", "/api/finance/reminder-settings", {"due_days": 4, "due_bell": True})[0] == 422

    # Pagado, el aviso pasa a hecho y la tarjeta deja de avisar
    api.call("POST", "/api/finance/transactions", tx(debit, 100_000, "Pago", kind="transfer", to=card), expect=201)
    [notice] = card_notices(finance_bell(api))
    assert notice["status"] == "done" and notice["detail"] == "Pagado."
    assert not api.call("GET", f"{URL}/{card['id']}/statement", expect=200)[1]["due_soon"]


def test_no_notice_far_from_the_due_date_or_without_finance(api):
    cash, debit, credit, cats = setup(api, "lejos@test.com")
    cut, due = TODAY - timedelta(days=2), TODAY + timedelta(days=15)
    _, card = api.call("POST", URL, {"name": "Plata", "kind": "credit", "statement_day": min(cut.day, 28),
                                     "due_day": due.day, "opening_balance_cents": -50_000,
                                     "opening_date": (TODAY - timedelta(days=20)).isoformat()}, expect=201)
    st = api.call("GET", f"{URL}/{card['id']}/statement", expect=200)[1]
    assert st["due_soon"] == (0 <= st["due_in_days"] <= 5)
    if not st["due_soon"]:
        assert not card_notices(finance_bell(api))
    # Con Finanzas apagada, la campana no pide sus avisos aunque los pida
    card_due_in_three_days(api, debit)
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": False}, expect=200)
    assert not card_notices(finance_bell(api))
