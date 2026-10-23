"""Finanzas: apartados de una cuenta y rendimientos
(docs/specs/finanzas-apartados-rendimientos.md)."""
from datetime import timedelta

from test_personal_finance import TODAY, setup, tx

URL = "/api/finance/accounts"


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def compound(balance, rate_bp, days, basis=365):
    """Lo que gana un saldo fijo con interés diario compuesto, en centavos."""
    return balance * ((1 + rate_bp / 10_000 / basis) ** days - 1)


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


def test_a_card_keeps_its_interest_rate_for_reference(api):
    cash, debit, credit, cats = setup(api, "tasa@test.com")
    _, card = api.call("POST", URL, {"name": "Oro", "kind": "credit", "interest_rate_bp": 4550}, expect=201)
    assert card["interest_rate_bp"] == 4550
    _, card = api.call("PATCH", f"{URL}/{card['id']}", {"interest_rate_bp": 6000}, expect=200)
    assert card["interest_rate_bp"] == 6000
    # Solo de crédito: en otra cuenta se vacía
    _, other = api.call("POST", URL, {"name": "Otra", "kind": "debit", "interest_rate_bp": 4550}, expect=201)
    assert other["interest_rate_bp"] is None
    assert api.call("PATCH", f"{URL}/{card['id']}", {"interest_rate_bp": -1})[0] == 422
    assert api.call("PATCH", f"{URL}/{card['id']}", {"interest_rate_bp": 100_001})[0] == 422


def test_daily_yield_is_estimated_and_recorded(api):
    cash, debit, credit, cats = setup(api, "rendimiento@test.com")
    _, bank = api.call("POST", URL, {"name": "Banco", "kind": "debit", "opening_balance_cents": 1_000_000,
                                     "opening_date": days_ago(10)}, expect=201)
    y = f"{URL}/{bank['id']}/yield"
    # Sin tasa no hay estimado ni nada que anotar
    assert api.call("GET", y, expect=200)[1]["estimate_cents"] is None
    assert api.call("POST", y, {})[0] == 422

    # 12 % anual desde hace 10 días: diez días de interés diario compuesto, hasta ayer
    _, body = api.call("PUT", f"{y}-rates", {"from_date": days_ago(10), "rate_bp": 1200}, expect=200)
    expected = compound(1_000_000, 1200, 10)
    assert body["since"] == days_ago(10) and body["through"] == days_ago(1)
    assert abs(body["estimate_cents"] - expected) <= 1 and body["rate_bp"] == 1200
    listed = accounts(api)["Banco"]
    assert listed["yield_rate_bp"] == 1200 and listed["yield_estimate_cents"] == body["estimate_cents"]

    # Con tope, solo esa parte gana (y lo ganado no lo pasa)
    _, body = api.call("PUT", f"{y}-rates", {"from_date": days_ago(10), "rate_bp": 1200, "cap_cents": 500_000},
                       expect=200)
    assert len(body["rates"]) == 1, "the same day replaces the rate"
    assert body["estimate_cents"] == round(500_000 * 0.12 / 365 * 10)

    # Un cambio de tasa vale desde su día; lo de antes no cambia
    api.call("PUT", f"{y}-rates", {"from_date": days_ago(10), "rate_bp": 1200}, expect=200)
    _, body = api.call("PUT", f"{y}-rates", {"from_date": days_ago(5), "rate_bp": 0}, expect=200)
    assert abs(body["estimate_cents"] - compound(1_000_000, 1200, 5)) <= 1
    assert api.call("PUT", f"{y}-rates", {"from_date": (TODAY + timedelta(days=1)).isoformat(), "rate_bp": 100})[0] == 422
    assert api.call("PUT", f"{y}-rates", {"from_date": days_ago(1), "rate_bp": 100, "day_basis": 300})[0] == 422
    api.call("DELETE", f"{y}-rates/{body['rates'][1]['id']}", expect=200)

    # Lo que sale de la cuenta deja de ganar desde ese día
    api.call("POST", "/api/finance/transactions", tx(bank, 400_000, "Renta", cats["Casa y servicios"], day=TODAY - timedelta(days=4)),
             expect=201)
    _, body = api.call("GET", y, expect=200)
    six = compound(1_000_000, 1200, 6)
    assert abs(body["estimate_cents"] - (six + compound(1_000_000 + six - 400_000, 1200, 4))) <= 1

    # Anotarlo: un ingreso en "Rendimientos" con el estimado; el siguiente empieza hoy
    _, record = api.call("POST", y, {}, expect=201)
    assert (record["kind"], record["amount_cents"], record["source"], record["tx_date"]) == (
        "income", body["estimate_cents"], "yield", TODAY.isoformat())
    _, after = api.call("GET", y, expect=200)
    assert after["since"] == TODAY.isoformat() and after["estimate_cents"] == 0
    assert api.call("POST", y, {})[0] == 422, "nothing to record yet"
    # Con la cifra del banco, esa; la categoría se usa la misma
    _, bank_says = api.call("POST", y, {"amount_cents": 12_345}, expect=201)
    assert bank_says["amount_cents"] == 12_345 and bank_says["category_id"] == record["category_id"]
    names = [c["name"] for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]]
    assert names.count("Rendimientos") == 1
    assert accounts(api)["Banco"]["balance_cents"] == 600_000 + body["estimate_cents"] + 12_345

    # Una tarjeta no da rendimiento, ni se vuelve tarjeta con tasa
    assert api.call("PUT", f"{URL}/{credit['id']}/yield-rates", {"from_date": days_ago(1), "rate_bp": 100})[0] == 409
    assert api.call("PATCH", f"{URL}/{bank['id']}", {"kind": "credit"})[0] == 409


def test_fixed_terms_mature_once(api):
    cash, debit, credit, cats = setup(api, "plazos@test.com")
    _, cetes = api.call("POST", URL, {"name": "CETES", "kind": "debit"}, expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 2_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=TODAY - timedelta(days=40)), expect=201)
    api.call("POST", "/api/finance/transactions", tx(debit, 1_000_000, "A CETES", kind="transfer", to=cetes,
                                                     day=TODAY - timedelta(days=40)), expect=201)
    term = {"account_id": cetes["id"], "concept": "CETES 28", "principal_cents": 1_000_000,
            "start_date": days_ago(40), "days": 28, "rate_bp": 1100}
    # Abierto (vence en el futuro): no anota nada y la cuenta dice cuánto no está disponible
    _, open_term = api.call("POST", "/api/finance/terms", {**term, "start_date": days_ago(1)}, expect=201)
    assert open_term["interest_cents"] == round(1_000_000 * 0.11 * 28 / 360) and not open_term["matured"]
    assert open_term["maturity_date"] == (TODAY + timedelta(days=27)).isoformat()
    mine = accounts(api)
    assert mine["CETES"]["term_locked_cents"] == 1_000_000 and mine["CETES"]["term_until"] == open_term["maturity_date"]
    api.call("DELETE", f"/api/finance/terms/{open_term['id']}", expect=204)

    # Vencido hace 12 días, y regresa a Débito: rendimiento como ingreso y la transferencia de vuelta
    _, done = api.call("POST", "/api/finance/terms", {**term, "on_maturity": "return",
                                                      "return_account_id": debit["id"]}, expect=201)
    interest = round(1_000_000 * 0.11 * 28 / 360)
    assert done["matured"] and done["interest_cents"] == interest
    for _ in range(2):  # pedirlo otra vez no anota de nuevo
        mine = accounts(api)
    assert mine["CETES"]["balance_cents"] == 0 and mine["CETES"]["term_locked_cents"] == 0
    assert mine["Débito"]["balance_cents"] == 1_000_000 + 1_000_000 + interest
    moves = [t for t in api.call("GET", f"/api/finance/transactions?date_from={days_ago(60)}&date_to={days_ago(0)}",
                                 expect=200)[1]["transactions"] if t["source"] == "yield"]
    assert sorted((t["kind"], t["amount_cents"], t["tx_date"]) for t in moves) == sorted([
        ("income", interest, days_ago(12)), ("transfer", 1_000_000 + interest, days_ago(12))])
    # Un plazo vencido ya no se corrige (sus movimientos sí); borrarlo deja lo anotado
    assert api.call("PUT", f"/api/finance/terms/{done['id']}", term)[0] == 409
    api.call("DELETE", f"/api/finance/terms/{done['id']}", expect=204)
    assert accounts(api)["Débito"]["balance_cents"] == 2_000_000 + interest

    # Reinvertir: cada vencimiento anota su rendimiento y empieza otro con capital + rendimiento
    _, renew = api.call("POST", "/api/finance/terms", {**term, "principal_cents": 100_000, "days": 10,
                                                       "start_date": days_ago(25), "on_maturity": "renew"}, expect=201)
    terms = api.call("GET", "/api/finance/terms", expect=200)[1]["terms"]
    first = round(100_000 * 0.11 * 10 / 360)
    second = round((100_000 + first) * 0.11 * 10 / 360)
    assert [(t["principal_cents"], t["matured"]) for t in terms] == [
        (100_000 + first + second, False), (100_000 + first, True), (100_000, True)]
    assert terms[0]["maturity_date"] == (TODAY + timedelta(days=5)).isoformat()

    # Las reglas
    assert api.call("POST", "/api/finance/terms", {**term, "account_id": credit["id"]})[0] == 409
    assert api.call("POST", "/api/finance/terms", {**term, "on_maturity": "return"})[0] == 422
    assert api.call("POST", "/api/finance/terms", {**term, "return_account_id": debit["id"]})[0] == 422
    assert api.call("POST", "/api/finance/terms", {**term, "on_maturity": "x"})[0] == 422
    assert api.call("PATCH", f"{URL}/{cetes['id']}", {"is_active": False})[0] == 409, "it has an open term"
    status, body = api.call("DELETE", f"{URL}/{cetes['id']}")
    assert status == 409


def test_a_pocket_earns_its_own_rate(api):
    """Como un banco digital: 12 % a la vista y 15 % en el apartado, moviendo el
    dinero cuando sea. Cada cuenta gana con su tasa sobre lo que tiene ese día."""
    cash, debit, credit, cats = setup(api, "apartado@test.com")
    _, bank = api.call("POST", URL, {"name": "Banco", "kind": "debit", "opening_balance_cents": 1_000_000,
                                     "opening_date": days_ago(10)}, expect=201)
    _, pocket = api.call("POST", URL, {"name": "Ahorro", "parent_id": bank["id"], "opening_date": days_ago(10)},
                         expect=201)
    api.call("PUT", f"{URL}/{bank['id']}/yield-rates", {"from_date": days_ago(10), "rate_bp": 1200}, expect=200)
    api.call("PUT", f"{URL}/{pocket['id']}/yield-rates", {"from_date": days_ago(10), "rate_bp": 1500}, expect=200)
    api.call("POST", "/api/finance/transactions", tx(bank, 600_000, "Al apartado", kind="transfer", to=pocket,
                                                     day=TODAY - timedelta(days=5)), expect=201)
    mine = accounts(api)
    five = compound(1_000_000, 1200, 5)
    assert abs(mine["Banco"]["yield_estimate_cents"] - (five + compound(400_000 + five, 1200, 5))) <= 1
    assert abs(mine["Ahorro"]["yield_estimate_cents"] - compound(600_000, 1500, 5)) <= 1
    assert mine["Ahorro"]["yield_since"] == days_ago(10)
