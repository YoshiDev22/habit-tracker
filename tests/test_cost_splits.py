"""Gastos repartidos entre proyectos y gastos recurrentes (plan Maker, 1.24)."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import ProjectCost, RecurringCost, User
from backend.recurring_costs import generate_due, occurrence
from test_finance import maker_on

TODAY = date.today()


def setup(api, email="reparto@test.com"):
    api.login(email)
    maker_on(api, email)
    _, tesis = api.call("POST", "/api/projects", {"name": "Tesis"}, expect=201)
    _, ht = api.call("POST", "/api/projects", {"name": "Habit Tracker"}, expect=201)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = next(c for c in cats["categories"] if c["name"] == "IA")
    return tesis, ht, cat


def add(api, project, cat, cents, concept="Anthropic", day=TODAY):
    return api.call("POST", "/api/costs", {"project_id": project["id"], "category_id": cat["id"],
                                           "cost_date": day.isoformat(), "concept": concept,
                                           "unit_cost_cents": cents}, expect=201)[1]


def sheet(api, project):
    return api.call("GET", f"/api/costs?project_id={project['id']}", expect=200)[1]


def costs_of(summary, project):
    return next(p for p in summary["projects"] if p["project_id"] == project["id"])["costs_cents"]


def user_id(email):
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().id


# ==================== Repartidos ====================

def test_split_an_expense(api):
    tesis, ht, cat = setup(api)
    cost = add(api, tesis, cat, 2000000)
    _, part = api.call("PUT", f"/api/costs/{cost['id']}/split",
                       {"allocations": [{"project_id": tesis["id"], "bp": 6500}, {"project_id": ht["id"], "bp": 3500}]},
                       expect=200)
    assert part["project_id"] == tesis["id"] and part["total_cents"] == 1300000
    assert part["group_total_cents"] == 2000000 and part["split_bp"] == 6500
    assert [(w["name"], w["bp"]) for w in part["split_with"]] == [("Tesis", 6500), ("Habit Tracker", 3500)]
    assert sheet(api, ht)["costs"][0]["total_cents"] == 700000
    _, summary = api.call("GET", "/api/costs/summary", expect=200)
    assert costs_of(summary, tesis) == 1300000 and costs_of(summary, ht) == 700000

    # Editar una parte edita el gasto entero, y las partes se reparten otra vez
    _, edited = api.call("PATCH", f"/api/costs/{part['id']}", {"unit_cost_cents": 100001, "concept": "Claude"}, expect=200)
    other = sheet(api, ht)["costs"][0]
    assert edited["total_cents"] + other["total_cents"] == 100001
    assert other["concept"] == "Claude" and other["unit_cost_cents"] == 100001

    # Un solo proyecto al 100 %: deja de estar repartido y pasa a ese proyecto
    _, moved = api.call("PUT", f"/api/costs/{part['id']}/split",
                        {"allocations": [{"project_id": ht["id"], "bp": 10000}]}, expect=200)
    assert moved["project_id"] == ht["id"] and moved["split_id"] is None and moved["total_cents"] == 100001
    assert sheet(api, tesis)["costs"] == []


def test_split_parts_always_add_up(api):
    tesis, ht, cat = setup(api)
    _, third = api.call("POST", "/api/projects", {"name": "Otro"}, expect=201)
    cost = add(api, tesis, cat, 100)
    api.call("PUT", f"/api/costs/{cost['id']}/split", {"allocations": [
        {"project_id": tesis["id"], "bp": 3333}, {"project_id": ht["id"], "bp": 3333},
        {"project_id": third["id"], "bp": 3334}]}, expect=200)
    totals = [sheet(api, p)["costs"][0]["total_cents"] for p in (tesis, ht, third)]
    assert sum(totals) == 100 and sorted(totals) == [33, 33, 34]


def test_deleting_a_part_deletes_the_expense(api):
    tesis, ht, cat = setup(api)
    cost = add(api, tesis, cat, 5000)
    _, part = api.call("PUT", f"/api/costs/{cost['id']}/split", {"allocations": [
        {"project_id": tesis["id"], "bp": 5000}, {"project_id": ht["id"], "bp": 5000}]}, expect=200)
    api.call("DELETE", f"/api/costs/{part['id']}", expect=204)
    assert sheet(api, tesis)["costs"] == [] and sheet(api, ht)["costs"] == []


def test_split_rules(api):
    tesis, ht, cat = setup(api)
    cost = add(api, tesis, cat, 5000)
    url = f"/api/costs/{cost['id']}/split"
    # Tienen que sumar 100 %, sin repetir proyecto
    assert api.call("PUT", url, {"allocations": [{"project_id": tesis["id"], "bp": 5000},
                                                 {"project_id": ht["id"], "bp": 4000}]})[0] == 422
    assert api.call("PUT", url, {"allocations": [{"project_id": tesis["id"], "bp": 5000},
                                                 {"project_id": tesis["id"], "bp": 5000}]})[0] == 422
    # Otra moneda: no se reparte (no hay conversión)
    api.call("PUT", f"/api/projects/{ht['id']}/finance", {"currency": "USD"}, expect=200)
    status, body = api.call("PUT", url, {"allocations": [{"project_id": tesis["id"], "bp": 5000},
                                                         {"project_id": ht["id"], "bp": 5000}]})
    assert status == 409 and "moneda" in body["detail"]
    # "Sin asignar" no lleva gastos
    _, projects = api.call("GET", "/api/projects?include_inactive=true", expect=200)
    system = next(p for p in projects["projects"] if p.get("is_system"))
    assert api.call("PUT", url, {"allocations": [{"project_id": system["id"], "bp": 10000}]})[0] == 409


# ==================== Recurrentes ====================

def recurring_body(project, cat, start, **extra):
    return {"category_id": cat["id"], "concept": "Hostinger", "unit_cost_cents": 25000,
            "frequency": "monthly", "start_date": start.isoformat(),
            "allocations": [{"project_id": project["id"], "bp": 10000}], **extra}


def test_occurrences_keep_the_day():
    assert occurrence(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)
    assert occurrence(date(2026, 1, 31), "monthly", 2) == date(2026, 3, 31)
    assert occurrence(date(2024, 2, 29), "yearly", 1) == date(2025, 2, 28)
    assert occurrence(date(2026, 11, 15), "monthly", 3) == date(2027, 2, 15)


def test_recurring_generates_what_is_due_once(api):
    tesis, ht, cat = setup(api)
    start = TODAY - timedelta(days=70)
    _, rc = api.call("POST", "/api/costs/recurring", recurring_body(tesis, cat, start), expect=201)
    due = [occurrence(start, "monthly", n) for n in range(5) if occurrence(start, "monthly", n) <= TODAY]
    rows = sheet(api, tesis)["costs"]
    assert sorted(r["cost_date"] for r in rows) == [d.isoformat() for d in due]
    assert all(r["recurring_id"] == rc["id"] and r["total_cents"] == 25000 for r in rows)
    assert rc["generated"] == len(due) and rc["next_date"] == occurrence(start, "monthly", len(due)).isoformat()
    # Pedirlo otra vez no duplica
    assert len(sheet(api, tesis)["costs"]) == len(due)

    # Un cobro borrado no vuelve
    api.call("DELETE", f"/api/costs/{rows[0]['id']}", expect=204)
    assert len(sheet(api, tesis)["costs"]) == len(due) - 1

    # Cambiarlo solo afecta a los siguientes
    api.call("PATCH", f"/api/costs/recurring/{rc['id']}", {"unit_cost_cents": 30000}, expect=200)
    with Session(engine) as session:
        generate_due(session, user_id("reparto@test.com"), TODAY + timedelta(days=40))
    amounts = sorted(r["total_cents"] for r in sheet(api, tesis)["costs"])
    assert amounts.count(25000) == len(due) - 1 and amounts.count(30000) >= 1

    # El primer cobro y la frecuencia ya no se cambian
    assert api.call("PATCH", f"/api/costs/recurring/{rc['id']}", {"frequency": "yearly"})[0] == 409

    # Borrarlo deja sus gastos, sin el 🔁
    api.call("DELETE", f"/api/costs/recurring/{rc['id']}", expect=204)
    assert all(r["recurring_id"] is None for r in sheet(api, tesis)["costs"])
    assert api.call("GET", "/api/costs/recurring", expect=200)[1]["recurring"] == []


def test_recurring_split_and_yearly(api):
    tesis, ht, cat = setup(api)
    body = recurring_body(tesis, cat, TODAY, frequency="yearly", unit_cost_cents=10001,
                          allocations=[{"project_id": tesis["id"], "bp": 6500}, {"project_id": ht["id"], "bp": 3500}])
    _, rc = api.call("POST", "/api/costs/recurring", body, expect=201)
    a, b = sheet(api, tesis)["costs"], sheet(api, ht)["costs"]
    assert len(a) == len(b) == 1 and a[0]["split_id"] == b[0]["split_id"] is not None
    assert a[0]["total_cents"] + b[0]["total_cents"] == 10001
    assert rc["next_date"] == occurrence(TODAY, "yearly", 1).isoformat()
    assert [x["name"] for x in rc["allocations"]] == ["Tesis", "Habit Tracker"]


def test_pausing_skips_the_paused_charges(api):
    tesis, ht, cat = setup(api)
    start = TODAY + timedelta(days=1)
    _, rc = api.call("POST", "/api/costs/recurring", recurring_body(tesis, cat, start), expect=201)
    api.call("PATCH", f"/api/costs/recurring/{rc['id']}", {"paused": True}, expect=200)
    uid = user_id("reparto@test.com")
    with Session(engine) as session:
        assert generate_due(session, uid, TODAY + timedelta(days=95)) == []
    # Reanudado "hoy" (simulado): lo de la pausa no se cobra
    with Session(engine) as session:
        row = session.get(RecurringCost, rc["id"])
        from backend.recurring_costs import skip_past
        row.paused = False
        skip_past(row, TODAY + timedelta(days=95))
        session.add(row)
        session.commit()
        created = generate_due(session, uid, TODAY + timedelta(days=95))
    assert all(c.cost_date >= TODAY + timedelta(days=95) for c in created)


def test_recurring_rules(api):
    tesis, ht, cat = setup(api)
    assert api.call("POST", "/api/costs/recurring", recurring_body(tesis, cat, TODAY, frequency="weekly"))[0] == 422
    assert api.call("POST", "/api/costs/recurring",
                    recurring_body(tesis, cat, TODAY, end_date=(TODAY - timedelta(days=1)).isoformat()))[0] == 422
    # Una categoría que usa un recurrente no se borra
    other = api.call("POST", "/api/costs/categories", {"name": "Suscripciones"}, expect=201)[1]
    api.call("POST", "/api/costs/recurring", {**recurring_body(tesis, cat, TODAY), "category_id": other["id"]}, expect=201)
    status, body = api.call("DELETE", f"/api/costs/categories/{other['id']}")
    assert status == 409 and "recurrente" in body["detail"]


def test_split_and_recurring_need_the_plan_and_are_private(api):
    tesis, ht, cat = setup(api)
    cost = add(api, tesis, cat, 5000)
    _, rc = api.call("POST", "/api/costs/recurring", recurring_body(tesis, cat, TODAY + timedelta(days=5)), expect=201)
    api.login("ajeno@test.com")
    maker_on(api, "ajeno@test.com")
    _, mine = api.call("POST", "/api/projects", {"name": "Mío"}, expect=201)
    assert api.call("PUT", f"/api/costs/{cost['id']}/split",
                    {"allocations": [{"project_id": mine["id"], "bp": 10000}]})[0] == 404
    assert api.call("PATCH", f"/api/costs/recurring/{rc['id']}", {"concept": "x"})[0] == 404
    assert api.call("DELETE", f"/api/costs/recurring/{rc['id']}")[0] == 404
    assert api.call("GET", "/api/costs/recurring", expect=200)[1]["recurring"] == []
    # Repartir hacia un proyecto ajeno tampoco
    api.login("reparto@test.com")
    assert api.call("PUT", f"/api/costs/{cost['id']}/split",
                    {"allocations": [{"project_id": mine["id"], "bp": 10000}]})[0] == 404
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": False}, expect=200)
    assert api.call("GET", "/api/costs/recurring")[0] == 403


def test_cost_report_counts_shares_and_recurring(api):
    tesis, ht, cat = setup(api)
    start = TODAY.replace(day=1)
    cost = add(api, tesis, cat, 10000, day=start)
    api.call("PUT", f"/api/costs/{cost['id']}/split", {"allocations": [
        {"project_id": tesis["id"], "bp": 7000}, {"project_id": ht["id"], "bp": 3000}]}, expect=200)
    api.call("POST", "/api/costs/recurring", recurring_body(ht, cat, start), expect=201)
    _, rep = api.call("POST", "/api/reports", {"kind": "costs-month", "period_start": start.isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    by_name = {p["name"]: p["costs_cents"] for p in rep["metrics"]["projects"]}
    assert by_name == {"Tesis": 7000, "Habit Tracker": 3000 + 25000}
