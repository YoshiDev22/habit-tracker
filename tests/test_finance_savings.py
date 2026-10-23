"""Finanzas: apartados de una cuenta y rendimientos
(docs/specs/finanzas-apartados-rendimientos.md)."""
from test_personal_finance import setup, tx

URL = "/api/finance/accounts"


def accounts(api):
    return {a["name"]: a for a in api.call("GET", URL, expect=200)[1]["accounts"]}


def test_a_savings_pocket_hangs_from_its_account(api):
    cash, debit, credit, cats = setup(api)
    # Un apartado toma la moneda y el tipo de su cuenta, aunque pida otros
    _, pocket = api.call("POST", URL, {"name": "Viaje", "kind": "cash", "currency": "USD",
                                       "parent_id": debit["id"]}, expect=201)
    assert (pocket["parent_id"], pocket["kind"], pocket["currency"]) == (debit["id"], "debit", "MXN")

    # Mover dinero al apartado es una transferencia: cada saldo una vez
    api.call("POST", "/api/finance/transactions", tx(debit, 1_000_000, "Nómina", cats["Sueldo"], kind="income"),
             expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 300_000, "Al apartado", kind="transfer", to=pocket),
             expect=201)
    mine = accounts(api)
    assert mine["Débito"]["balance_cents"] == 700_000 and mine["Viaje"]["balance_cents"] == 300_000
    assert mine["Viaje"]["parent_id"] == debit["id"] and mine["Débito"]["parent_id"] is None

    # Un solo nivel, nunca de crédito, y la cuenta madre activa
    assert api.call("POST", URL, {"name": "Sub", "parent_id": pocket["id"]})[0] == 409
    assert api.call("POST", URL, {"name": "Sub", "parent_id": credit["id"]})[0] == 409
    assert api.call("POST", URL, {"name": "Tarjeta 2", "kind": "credit", "parent_id": debit["id"]})[0] == 409
    assert api.call("PATCH", f"{URL}/{debit['id']}", {"parent_id": debit["id"]})[0] == 422
    assert api.call("PATCH", f"{URL}/{debit['id']}", {"parent_id": cash["id"]})[0] == 409, "it has pockets"
    assert api.call("PATCH", f"{URL}/{credit['id']}", {"parent_id": debit["id"]})[0] == 409

    # La cuenta madre no se vuelve de crédito, ni cambia de moneda, ni se archiva o borra con apartados
    assert api.call("PATCH", f"{URL}/{debit['id']}", {"kind": "credit"})[0] == 409
    assert api.call("PATCH", f"{URL}/{debit['id']}", {"currency": "USD"})[0] == 409
    assert api.call("PATCH", f"{URL}/{debit['id']}", {"is_active": False})[0] == 409
    _, empty = api.call("POST", URL, {"name": "Débito 2", "kind": "debit"}, expect=201)
    api.call("POST", URL, {"name": "Colchón", "parent_id": empty["id"]}, expect=201)
    status, body = api.call("DELETE", f"{URL}/{empty['id']}")
    assert status == 409 and "apartados" in body["detail"]
    # El apartado no cambia su tipo ni su moneda por su cuenta
    assert api.call("PATCH", f"{URL}/{pocket['id']}", {"kind": "cash"})[0] == 409
    # La cuenta pasa de débito a efectivo y sus apartados la siguen
    api.call("PATCH", f"{URL}/{debit['id']}", {"kind": "cash"}, expect=200)
    assert accounts(api)["Viaje"]["kind"] == "cash"

    # Archivar el apartado y luego la cuenta; el apartado no vuelve antes que ella
    api.call("PATCH", f"{URL}/{pocket['id']}", {"is_active": False}, expect=200)
    api.call("PATCH", f"{URL}/{debit['id']}", {"is_active": False}, expect=200)
    assert api.call("PATCH", f"{URL}/{pocket['id']}", {"is_active": True})[0] == 409
    api.call("PATCH", f"{URL}/{debit['id']}", {"is_active": True}, expect=200)
    api.call("PATCH", f"{URL}/{pocket['id']}", {"is_active": True}, expect=200)

    # Sacarlo: vuelve a ser cuenta suelta, con su saldo
    _, loose = api.call("PATCH", f"{URL}/{pocket['id']}", {"parent_id": None}, expect=200)
    assert loose["parent_id"] is None and loose["balance_cents"] == 300_000
    # Y volver a meterlo en otra cuenta de la misma moneda
    _, back = api.call("PATCH", f"{URL}/{pocket['id']}", {"parent_id": cash["id"]}, expect=200)
    assert back["parent_id"] == cash["id"]


def test_a_pocket_with_movements_keeps_its_currency(api):
    cash, debit, credit, cats = setup(api, "moneda@test.com")
    _, dollars = api.call("POST", URL, {"name": "Dólares", "kind": "debit", "currency": "USD"}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(dollars, 100, "x", cats["Sueldo"], kind="income"), expect=201)
    status, body = api.call("PATCH", f"{URL}/{dollars['id']}", {"parent_id": debit["id"]})
    assert status == 409 and "USD" in body["detail"]
