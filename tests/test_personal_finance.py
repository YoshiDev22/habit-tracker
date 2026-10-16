"""Finanzas personales (épica 37, fase 1): el módulo, cuentas, categorías,
movimientos, fijos y el periodo. test_finance.py es otra cosa: el costeo de
proyectos del plan maker."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.finance import DEFAULT_CATEGORIES, generate_due
from backend.models import FinRecurring, User
from backend.series import occurrence, period_bounds
from test_modules import grant

TODAY = date.today()


def finance_on(api, email):
    """Cuenta con Finanzas: acceso dado por el script y módulo encendido."""
    api.login(email)
    assert grant("--email", email, "--module", "finance").returncode == 0
    api.call("PUT", "/api/auth/me/modules/finance", {"enabled": True}, expect=200)


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
    api.call("GET", "/api/finance/accounts", expect=200)


def test_starts_with_cash_and_the_categories_once(api):
    finance_on(api, "inicio@test.com")
    for _ in range(2):
        accounts = api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]
        cats = api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
    assert [(a["name"], a["kind"], a["is_default"]) for a in accounts] == [("Efectivo", "cash", True)]
    assert [(c["name"], c["kind"]) for c in cats] == [(name, kind) for name, _, kind in DEFAULT_CATEGORIES]


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
    assert api.call("GET", "/api/finance/transactions?date_from=2026-01-01&date_to=2027-01-02")[0] == 422


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
