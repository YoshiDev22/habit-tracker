"""Finanzas: préstamos (Finanzas 0.9, BACKLOG 52). Un pago es un solo movimiento: la
deuda baja solo el capital, los intereses son gasto, y el capital también si lo
comprado con el préstamo no estaba anotado. Ningún peso cuenta dos veces."""
from datetime import timedelta

from test_personal_finance import TODAY, setup, tx

URL = "/api/finance/accounts"


def days_ago(n):
    return TODAY - timedelta(days=n)


def account(api, acc):
    return next(a for a in api.call("GET", URL, expect=200)[1]["accounts"] if a["id"] == acc["id"])


def totals(api):
    body = api.call("GET", "/api/finance/summary?all=true", expect=200)[1]
    by_name = {c["name"]: c["cents"] for c in body["categories"]}
    return (body["totals"][0]["expense_cents"] if body["totals"] else 0), by_name


def new_loan(api, name, owed, **extra):
    body = {"name": name, "kind": "loan", "debt_type": "bank", "opening_balance_cents": -owed,
            "opening_date": days_ago(60).isoformat(), **extra}
    return api.call("POST", URL, body, expect=201)[1]


def pay(api, source, loan, amount, interest=None, principal_only=False, day=TODAY, expect=201, charges=None):
    body = {**tx(source, amount, f"Pago {loan['name']}", kind="transfer", to=loan, day=day),
            "interest_cents": interest, "charges_cents": charges, "principal_only": principal_only}
    return api.call("POST", "/api/finance/transactions", body, expect=expect)[1]


def test_a_loan_whose_purchase_is_already_an_expense(api):
    """Lo comprado ya contó como gasto: el capital solo baja la deuda y los intereses son gasto."""
    cash, debit, credit, cats = setup(api, "ya@test.com")
    api.call("POST", "/api/finance/transactions", tx(debit, 5_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=days_ago(30)), expect=201)
    loan = new_loan(api, "Préstamo banco", 1_000_000, interest_rate_bp=2400, loan_payment_cents=100_000,
                    loan_months=12, due_day=10)
    assert loan["kind"] == "loan" and loan["debt_type"] == "bank" and loan["loan_category_id"] is None
    assert loan["due_day"] == 10 and loan["interest_rate_bp"] == 2400
    before_expense, _ = totals(api)

    payment = pay(api, debit, loan, 100_000, interest=20_000)
    assert payment["interest_cents"] == 20_000 and payment["category_id"] is None and not payment["principal_only"]
    assert account(api, loan)["balance_cents"] == -1_000_000 + 80_000, "only the principal lowers the debt"
    assert account(api, debit)["balance_cents"] == 5_000_000 - 100_000, "the whole payment leaves the account"
    expense, by_cat = totals(api)
    assert expense - before_expense == 20_000 and by_cat["Intereses"] == 20_000, "only the interest is an expense"

    # Un abono a capital: completo a la deuda, sin intereses
    pay(api, debit, loan, 50_000, principal_only=True)
    pay(api, debit, loan, 50_000, interest=1, principal_only=True, expect=422)
    pay(api, debit, loan, 100_000, interest=100_001, expect=422)
    assert account(api, loan)["balance_cents"] == -1_000_000 + 80_000 + 50_000
    assert totals(api)[0] - before_expense == 20_000

    _, info = api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)
    assert (info["owed_cents"], info["paid_cents"], info["paid_principal_cents"], info["paid_interest_cents"]) == \
        (870_000, 150_000, 130_000, 20_000)
    assert info["regular_count"] == 1 and info["capital_count"] == 1
    # Sin tabla: el interés del siguiente pago, con la tasa (24 % ÷ 12 sobre lo que se debe)
    assert info["next_interest_cents"] == 17_400 and info["next_payment_cents"] == 100_000 and not info["from_table"]
    assert info["next_due"] and info["ends_on"]


def test_a_loan_whose_purchase_was_not_recorded(api):
    """Lo comprado no estaba anotado: el capital de cada pago es gasto en su categoría, y los
    intereses en Intereses. Pago, deuda y gastos cuadran: nada cuenta dos veces."""
    cash, debit, credit, cats = setup(api, "no@test.com")
    api.call("POST", "/api/finance/transactions", tx(debit, 5_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=days_ago(30)), expect=201)
    loan = new_loan(api, "Préstamo personal", 600_000, debt_type="personal",
                    loan_category_id=cats["Personal"]["id"])
    before_expense, before_cat = totals(api)
    payment = pay(api, debit, loan, 60_000, interest=6_000)
    assert payment["category_id"] == cats["Personal"]["id"], "it takes the loan's category"
    expense, by_cat = totals(api)
    assert expense - before_expense == 60_000, "the payment counts once, whole"
    assert by_cat["Personal"] - before_cat.get("Personal", 0) == 54_000 and by_cat["Intereses"] == 6_000
    assert account(api, loan)["balance_cents"] == -600_000 + 54_000
    assert account(api, debit)["balance_cents"] == 5_000_000 - 60_000
    # Editar el pago: los intereses cambian y todo sigue cuadrando
    api.call("PATCH", f"/api/finance/transactions/{payment['id']}", {"interest_cents": 10_000}, expect=200)
    expense, by_cat = totals(api)
    assert expense - before_expense == 60_000 and by_cat["Intereses"] == 10_000
    assert account(api, loan)["balance_cents"] == -600_000 + 50_000
    # Que deje de ir al préstamo: ya no lleva categoría ni intereses, y no es gasto
    status, _ = api.call("PATCH", f"/api/finance/transactions/{payment['id']}", {"to_account_id": cash["id"]})
    assert status == 422, "interest stays only on a loan payment"
    api.call("PATCH", f"/api/finance/transactions/{payment['id']}", {"to_account_id": cash["id"], "interest_cents": None},
             expect=200)
    assert totals(api)[0] == before_expense and account(api, loan)["balance_cents"] == -600_000


def test_loan_rules(api):
    cash, debit, credit, cats = setup(api, "reglas@test.com")
    loan = new_loan(api, "Hipoteca", 2_000_000, debt_type="mortgage")
    # Solo una transferencia a un préstamo lleva categoría, intereses o abono a capital
    body = {**tx(debit, 1_000, "x", kind="transfer", to=cash), "category_id": cats["Personal"]["id"]}
    assert api.call("POST", "/api/finance/transactions", body)[0] == 422
    assert api.call("POST", "/api/finance/transactions",
                    {**tx(debit, 1_000, "x", kind="transfer", to=cash), "interest_cents": 10})[0] == 422
    assert api.call("POST", "/api/finance/transactions",
                    {**tx(debit, 1_000, "x", cats["Personal"]), "principal_only": True})[0] == 422
    body = {**tx(debit, 1_000, "x", kind="transfer", to=loan), "category_id": cats["Sueldo"]["id"]}
    assert api.call("POST", "/api/finance/transactions", body)[0] == 422, "an income category"
    # Un préstamo no es apartado, ni la cuenta por defecto, ni tiene apartados
    assert api.call("POST", URL, {"name": "P2", "kind": "loan", "parent_id": debit["id"]})[0] == 409
    assert api.call("POST", URL, {"name": "P3", "kind": "loan", "is_default": True})[0] == 409
    assert api.call("POST", URL, {"name": "Ap", "kind": "debit", "parent_id": loan["id"]})[0] == 409
    assert api.call("POST", URL, {"name": "P4", "kind": "loan", "debt_type": "boat"})[0] == 422
    assert api.call("POST", URL, {"name": "P5", "kind": "loan", "loan_category_id": cats["Sueldo"]["id"]})[0] == 422
    # Con movimientos no se vuelve préstamo ni deja de serlo; los datos de préstamo, solo en uno
    pay(api, debit, loan, 1_000)
    assert api.call("PATCH", f"{URL}/{loan['id']}", {"kind": "debit"})[0] == 409
    _, plain = api.call("POST", URL, {"name": "Otra", "kind": "debit", "debt_type": "bank", "loan_months": 3}, expect=201)
    assert plain["debt_type"] is None and plain["loan_months"] is None
    # La categoría de un préstamo no se borra
    _, cat = api.call("POST", "/api/finance/categories", {"name": "Estudios", "kind": "expense"}, expect=201)
    api.call("PATCH", f"{URL}/{loan['id']}", {"loan_category_id": cat["id"]}, expect=200)
    assert api.call("DELETE", f"/api/finance/categories/{cat['id']}")[0] == 409
    # Ni "Intereses" mientras un pago la use
    pay(api, debit, loan, 2_000, interest=500)
    interest = next(c for c in api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
                    if c["name"] == "Intereses")
    assert api.call("DELETE", f"/api/finance/categories/{interest['id']}")[0] == 409
    # La página del préstamo, solo de un préstamo
    assert api.call("GET", f"{URL}/{debit['id']}/loan")[0] == 409


def test_amortization_table(api):
    cash, debit, credit, cats = setup(api, "tabla@test.com")
    loan = new_loan(api, "Crédito bancario", 300_000, interest_rate_bp=1200)
    first = TODAY + timedelta(days=5)
    rows = [{"number": n + 1, "due_date": (first + timedelta(days=30 * n)).isoformat(), "payment_cents": 102_000,
             "principal_cents": 100_000 - n * 10, "interest_cents": 2_000 + n * 10,
             "balance_cents": 300_000 - (n + 1) * 100_000} for n in range(3)]
    _, info = api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": rows}, expect=200)
    assert len(info["rows"]) == 3 and not any(r["paid"] for r in info["rows"])
    assert (info["next_number"], info["next_payment_cents"], info["next_interest_cents"], info["from_table"]) == \
        (1, 102_000, 2_000, True)
    assert info["ends_on"] == rows[-1]["due_date"]
    # Una mensualidad cubre la primera fila y propone la segunda; un abono a capital no cuenta como mensualidad
    pay(api, debit, loan, 102_000, interest=2_000)
    pay(api, debit, loan, 10_000, principal_only=True)
    _, info = api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)
    assert [r["paid"] for r in info["rows"]] == [True, False, False] and info["next_number"] == 2
    # Reglas de la tabla
    bad = [dict(rows[0]), dict(rows[1])]
    bad[1]["number"] = 1
    assert api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": bad})[0] == 422
    bad = [dict(rows[0], payment_cents=1)]
    assert api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": bad})[0] == 422
    bad = [dict(rows[1]), dict(rows[0], number=3)]
    assert api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": bad})[0] == 422, "dates out of order"
    # Vacía, la quita
    _, info = api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": []}, expect=200)
    assert info["rows"] == [] and not info["from_table"]


def test_capital_note_can_be_hidden(api):
    cash, debit, credit, cats = setup(api, "nota@test.com")
    loan = new_loan(api, "Préstamo", 100_000)
    assert api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)[1]["capital_note_hidden"] is False
    assert api.call("PUT", "/api/finance/capital-note", {"hidden": True}, expect=200)[1] == {"hidden": True}
    assert api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)[1]["capital_note_hidden"] is True
    api.call("PUT", "/api/finance/capital-note", {"hidden": False}, expect=200)
    assert api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)[1]["capital_note_hidden"] is False


def test_insurance_apart_from_interest_and_charges_that_raise_the_debt(api):
    """Un pago con intereses y seguro: cada uno en su categoría, solo el capital baja la deuda.
    Un cargo (el seguro del año) sube la deuda y es gasto; y como se debe más, el interés que
    se propone también sube."""
    cash, debit, credit, cats = setup(api, "seguro@test.com")
    api.call("POST", "/api/finance/transactions", tx(debit, 5_000_000, "Nómina", cats["Sueldo"], kind="income",
                                                     day=days_ago(30)), expect=201)
    loan = new_loan(api, "Hipotecario", 1_200_000, debt_type="mortgage", interest_rate_bp=1200,
                    loan_payment_cents=50_000)
    before, _ = totals(api)
    payment = pay(api, debit, loan, 50_000, interest=12_000, charges=3_000)
    assert payment["interest_cents"] == 12_000 and payment["charges_cents"] == 3_000
    expense, by_cat = totals(api)
    assert expense - before == 15_000 and by_cat["Intereses"] == 12_000 and by_cat["Seguros y comisiones"] == 3_000
    assert account(api, loan)["balance_cents"] == -1_200_000 + 35_000
    pay(api, debit, loan, 10_000, interest=6_000, charges=5_000, expect=422)
    pay(api, debit, loan, 10_000, charges=1, principal_only=True, expect=422)
    _, info = api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)
    assert (info["paid_principal_cents"], info["paid_interest_cents"], info["paid_charges_cents"]) == (35_000, 12_000, 3_000)
    estimate = info["next_interest_cents"]
    assert estimate == 11_650   # 1 % al mes de 1,165,000

    # El seguro del año, anotado en el préstamo: sube la deuda, es gasto, y el interés propuesto sube
    _, cat = api.call("POST", "/api/finance/categories", {"name": "Seguro anual", "kind": "expense"}, expect=201)
    _, charge = api.call("POST", "/api/finance/transactions", tx(loan, 100_000, "Seguro", cat), expect=201)
    assert account(api, loan)["balance_cents"] == -1_200_000 + 35_000 - 100_000
    assert totals(api)[0] - before == 115_000
    _, info = api.call("GET", f"{URL}/{loan['id']}/loan", expect=200)
    assert info["added_cents"] == 100_000 and [c["id"] for c in info["charges"]] == [charge["id"]]
    assert info["next_interest_cents"] == 12_650 > estimate
    # Y la hoja del monto no propone el préstamo como la cuenta de un gasto
    _, listed = api.call("GET", "/api/finance/categories", expect=200)
    assert listed["last_expense_account_id"] != loan["id"]
    assert next(c for c in listed["categories"] if c["id"] == cat["id"])["usual_account_id"] is None

    # Ajustar la deuda (lo que dice el banco): cambia el punto de partida, sin gasto ni movimiento
    real = 1_250_000
    current = account(api, loan)
    api.call("PATCH", f"{URL}/{loan['id']}",
             {"opening_balance_cents": current["opening_balance_cents"] + (-real - current["balance_cents"])}, expect=200)
    assert account(api, loan)["balance_cents"] == -real and totals(api)[0] - before == 115_000

    # La tabla con seguros aparte: el pago es capital + intereses + seguros
    row = {"number": 1, "due_date": (TODAY + timedelta(days=10)).isoformat(), "payment_cents": 50_000,
           "principal_cents": 35_000, "interest_cents": 12_000, "charges_cents": 3_000}
    _, info = api.call("PUT", f"{URL}/{loan['id']}/loan-schedule", {"rows": [row]}, expect=200)
    assert info["rows"][0]["charges_cents"] == 3_000
    assert api.call("PUT", f"{URL}/{loan['id']}/loan-schedule",
                    {"rows": [dict(row, charges_cents=0)]})[0] == 422, "they no longer add up to the payment"
