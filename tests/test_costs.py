"""Pestaña Costos (plan maker, épica 24 Fase 3): gastos, categorías y resumen."""
from datetime import date, timedelta

from conftest import log_time
from test_finance import maker_on

TODAY = date.today().isoformat()


def setup(api, email="costos@test.com"):
    api.login(email)
    maker_on(api, email)
    _, p = api.call("POST", "/api/projects", {"name": "Lámpara"}, expect=201)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    by_name = {c["name"]: c["id"] for c in cats["categories"]}
    return p, by_name


def add(api, project_id, category_id, concept, unit_cents, quantity=1, day=TODAY):
    _, c = api.call("POST", "/api/costs", {
        "project_id": project_id, "category_id": category_id, "cost_date": day,
        "concept": concept, "quantity": quantity, "unit_cost_cents": unit_cents,
    }, expect=201)
    return c


def test_needs_the_maker_plan(api):
    api.login("sin@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    for method, url, body in [
        ("GET", "/api/costs/categories", None),
        ("GET", "/api/costs/summary", None),
        ("GET", f"/api/costs?project_id={p['id']}", None),
        ("POST", "/api/costs", {"project_id": p["id"], "category_id": 1, "cost_date": TODAY, "concept": "x"}),
        ("POST", "/api/costs/categories", {"name": "x"}),
    ]:
        assert api.call(method, url, body)[0] == 403, url


def test_default_categories_once_and_editable(api):
    _, cats = setup(api)
    assert list(cats) == ["Material", "Licencia / software", "Servicio", "IA", "Otro"]
    _, again = api.call("GET", "/api/costs/categories", expect=200)
    assert len(again["categories"]) == 5, "seeded only once"

    _, new = api.call("POST", "/api/costs/categories", {"name": "  Hosting ", "color": "#123456"}, expect=201)
    assert new["name"] == "Hosting" and new["order"] == 5
    assert api.call("POST", "/api/costs/categories", {"name": "Hosting"})[0] == 409
    _, ren = api.call("PATCH", f"/api/costs/categories/{cats['IA']}", {"name": "Inteligencia artificial", "order": 0}, expect=200)
    assert ren["name"] == "Inteligencia artificial"
    assert api.call("PATCH", f"/api/costs/categories/{cats['Otro']}", {"name": "Material"})[0] == 409
    _, listed = api.call("GET", "/api/costs/categories", expect=200)
    assert listed["categories"][0]["name"] in ("Material", "Inteligencia artificial"), "order is editable"


def test_a_category_with_costs_is_not_deleted(api):
    p, cats = setup(api)
    add(api, p["id"], cats["Material"], "Base de madera", 25000)
    s, body = api.call("DELETE", f"/api/costs/categories/{cats['Material']}")
    assert s == 409 and "1 gasto" in body["detail"]
    _, listed = api.call("GET", "/api/costs/categories", expect=200)
    assert next(c for c in listed["categories"] if c["name"] == "Material")["cost_count"] == 1
    api.call("DELETE", f"/api/costs/categories/{cats['Otro']}", expect=204)
    # La última no se borra
    for name in ("Licencia / software", "Servicio", "IA"):
        api.call("DELETE", f"/api/costs/categories/{cats[name]}", expect=204)
    only = api.call("GET", f"/api/costs?project_id={p['id']}", expect=200)[1]["costs"][0]
    api.call("DELETE", f"/api/costs/{only['id']}", expect=204)
    s, body = api.call("DELETE", f"/api/costs/categories/{cats['Material']}")
    assert s == 409 and "al menos una" in body["detail"]


def test_costs_rows_and_totals(api):
    p, cats = setup(api)
    old = (date.today() - timedelta(days=3)).isoformat()
    add(api, p["id"], cats["Material"], "Tela", 1999, quantity=2.5, day=old)   # 49.975 → 49.98
    lic = add(api, p["id"], cats["Licencia / software"], "Fusion 360", 50000)
    assert lic["total_cents"] == 50000
    _, lst = api.call("GET", f"/api/costs?project_id={p['id']}", expect=200)
    assert [c["concept"] for c in lst["costs"]] == ["Fusion 360", "Tela"], "most recent first"
    assert lst["costs"][1]["total_cents"] == 4998, "half up, like money"
    assert lst["total_cents"] == 54998 and lst["currency"] == "MXN"

    # Edición celda por celda
    _, ed = api.call("PATCH", f"/api/costs/{lic['id']}", {"quantity": 2, "concept": " Fusion 360 (2) "}, expect=200)
    assert ed["total_cents"] == 100000 and ed["concept"] == "Fusion 360 (2)"
    assert api.call("PATCH", f"/api/costs/{lic['id']}", {"concept": "  "})[0] == 422
    assert api.call("PATCH", f"/api/costs/{lic['id']}", {"quantity": None})[0] == 422
    assert api.call("PATCH", f"/api/costs/{lic['id']}", {"category_id": 999999})[0] == 404
    api.call("DELETE", f"/api/costs/{lic['id']}", expect=204)
    assert api.call("GET", f"/api/costs?project_id={p['id']}", expect=200)[1]["total_cents"] == 4998


def test_import_is_all_or_nothing(api):
    p, cats = setup(api)
    row = {"category_id": cats["Material"], "cost_date": TODAY, "concept": "Tornillos", "quantity": 100, "unit_cost_cents": 150}
    _, done = api.call("POST", "/api/costs/import", {"project_id": p["id"], "rows": [row, {**row, "concept": "Pintura", "quantity": 1, "unit_cost_cents": 32050}]}, expect=201)
    assert done["total_cents"] == 15000 + 32050 and len(done["costs"]) == 2
    # Una fila con categoría ajena o inexistente: no entra ninguna
    bad = [row, {**row, "category_id": 999999}]
    assert api.call("POST", "/api/costs/import", {"project_id": p["id"], "rows": bad})[0] == 404
    assert len(api.call("GET", f"/api/costs?project_id={p['id']}", expect=200)[1]["costs"]) == 2
    assert api.call("POST", "/api/costs/import", {"project_id": p["id"], "rows": []})[0] == 422
    assert api.call("POST", "/api/costs/import", {"project_id": p["id"], "rows": [row] * 501})[0] == 422


def test_summary_finance_and_margin(api):
    p, cats = setup(api)
    api.call("PUT", f"/api/projects/{p['id']}/finance", {"hourly_rate_cents": 30000, "budget_cents": 1_000_000}, expect=200)
    log_time(api, p["id"], None, 2 * 3600)                     # 2 h × $300 = $600
    add(api, p["id"], cats["Material"], "Base", 150000)        # $1,500
    add(api, p["id"], cats["IA"], "Tokens", 31000)             # $310

    # La ficha suma los gastos
    _, fin = api.call("GET", f"/api/projects/{p['id']}/finance", expect=200)
    assert (fin["labor_cents"], fin["costs_cents"], fin["total_cost_cents"]) == (60000, 181000, 241000)
    assert fin["margin_cents"] == 1_000_000 - 241000 and fin["budget_money_pct"] == 24

    # Otro proyecto en USD, y uno archivado sin costeo que no aparece
    _, usd = api.call("POST", "/api/projects", {"name": "App cliente"}, expect=201)
    api.call("PUT", f"/api/projects/{usd['id']}/finance", {"currency": "USD", "budget_cents": 200000}, expect=200)
    add(api, usd["id"], cats["Licencia / software"], "Apple Developer", 9900)
    _, gone = api.call("POST", "/api/projects", {"name": "Viejo"}, expect=201)
    api.call("PATCH", f"/api/projects/{gone['id']}", {"is_active": False}, expect=200)

    _, sm = api.call("GET", "/api/costs/summary", expect=200)
    rows = {r["name"]: r for r in sm["projects"]}
    assert "Viejo" not in rows and "Sin asignar" not in rows
    lamp = rows["Lámpara"]
    assert (lamp["labor_cents"], lamp["costs_cents"], lamp["total_cost_cents"], lamp["margin_cents"]) == (60000, 181000, 241000, 759000)
    assert rows["App cliente"]["currency"] == "USD" and rows["App cliente"]["is_quote"] is True
    totals = {t["currency"]: t for t in sm["totals"]}
    assert totals["MXN"]["total_cost_cents"] == 241000 and totals["USD"]["costs_cents"] == 9900, "never mixed"
    cat = {(c["name"], c["currency"]): c["cents"] for c in sm["categories"]}
    assert cat == {("Material", "MXN"): 150000, ("IA", "MXN"): 31000, ("Licencia / software", "USD"): 9900}


def test_unassigned_has_no_costs_and_delete_removes_them(api):
    p, cats = setup(api)
    _, allp = api.call("GET", "/api/projects?include_inactive=true", expect=200)
    system = next(x for x in allp["projects"] if x["is_system"])
    body = {"project_id": system["id"], "category_id": cats["Otro"], "cost_date": TODAY, "concept": "x"}
    assert api.call("POST", "/api/costs", body)[0] == 409
    add(api, p["id"], cats["Material"], "Base", 100)
    api.call("DELETE", f"/api/projects/{p['id']}", expect=204)
    _, listed = api.call("GET", "/api/costs/categories", expect=200)
    assert all(c["cost_count"] == 0 for c in listed["categories"]), "the project's costs went with it"
