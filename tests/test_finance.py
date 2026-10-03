"""Costeo de proyectos (plan maker, épica 24 Fase 2): tarifa, moneda y presupuesto."""
from conftest import H, log_time
from test_modules import grant


def maker_on(api, email):
    """Cuenta con el plan maker: acceso dado por el script y módulo encendido."""
    assert grant("--email", email, "--module", "maker").returncode == 0
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)


def test_needs_the_maker_plan(seeded):
    api, p = seeded["api"], seeded["project"]
    url = f"/api/projects/{p['id']}/finance"
    s, body = api.call("GET", url)
    assert s == 403 and "acceso" in body["detail"]
    assert api.call("PUT", url, {"hourly_rate_cents": 35000})[0] == 403
    _, ov = api.call("GET", f"/api/projects/{p['id']}/overview", expect=200)
    assert ov["finance"] is None, "the overview has no money without the plan"

    # Con acceso pero apagado, tampoco; el mensaje dice cómo encenderlo
    assert grant("--email", "yoshi@test.com", "--module", "maker").returncode == 0
    s, body = api.call("GET", url)
    assert s == 403 and "Configuración › Módulos" in body["detail"]
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    api.call("GET", url, expect=200)


def test_rate_labor_and_budget(seeded):
    api, p = seeded["api"], seeded["project"]
    maker_on(api, "yoshi@test.com")
    url = f"/api/projects/{p['id']}/finance"

    _, f = api.call("GET", url, expect=200)
    assert f["currency"] == "MXN" and f["hourly_rate_cents"] is None and f["labor_cents"] is None
    assert f["total_seconds"] == 417 * 60

    # 417 min × $350.00/h = $2,432.50, en centavos y sin float
    _, f = api.call("PUT", url, {"client_name": "  Acme  ", "hourly_rate_cents": 35000}, expect=200)
    assert f["client_name"] == "Acme" and f["labor_cents"] == 243250
    assert f["budget_money_pct"] is None and f["budget_time_pct"] is None and f["is_quote"] is False

    _, f = api.call("PUT", url, {"budget_cents": 500000, "budget_minutes": 10 * 60, "currency": "USD"}, expect=200)
    assert f["budget_money_pct"] == 49 and f["budget_time_pct"] == 70   # 2432.50/5000, 417/600
    assert f["currency"] == "USD" and f["client_name"] == "Acme", "partial: what is not sent is kept"

    # null borra un dato; la moneda vuelve a la de por defecto
    _, f = api.call("PUT", url, {"budget_cents": None, "currency": None}, expect=200)
    assert f["budget_cents"] is None and f["budget_money_pct"] is None and f["currency"] == "MXN"

    # La ficha trae lo mismo
    _, ov = api.call("GET", f"/api/projects/{p['id']}/overview", expect=200)
    assert ov["finance"]["labor_cents"] == 243250 and ov["finance"]["budget_time_pct"] == 70

    # Más tiempo, más mano de obra: se calcula, no se guarda
    log_time(api, p["id"], None, H)
    assert api.call("GET", url, expect=200)[1]["labor_cents"] == 243250 + 35000


def test_a_budget_without_time_is_a_quote(api):
    api.login("cotiza@test.com")
    maker_on(api, "cotiza@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "Tienda en línea"}, expect=201)
    url = f"/api/projects/{p['id']}/finance"
    _, f = api.call("PUT", url, {"hourly_rate_cents": 40000}, expect=200)
    assert f["is_quote"] is False, "a rate alone is not a quote"
    _, f = api.call("PUT", url, {"budget_minutes": 40 * 60}, expect=200)
    assert f["is_quote"] is True and f["budget_time_pct"] == 0 and f["labor_cents"] == 0
    log_time(api, p["id"], None, 30 * 60)
    assert api.call("GET", url, expect=200)[1]["is_quote"] is False, "once worked on, no longer a quote"


def test_unassigned_and_archived(seeded):
    api = seeded["api"]
    maker_on(api, "yoshi@test.com")
    _, allp = api.call("GET", "/api/projects?include_inactive=true", expect=200)
    system = next(p for p in allp["projects"] if p["is_system"])
    assert api.call("PUT", f"/api/projects/{system['id']}/finance", {"hourly_rate_cents": 1})[0] == 409
    assert api.call("GET", f"/api/projects/{system['id']}/overview", expect=200)[1]["finance"] is None
    # Un archivado conserva su costeo y se puede seguir ajustando
    arch = seeded["archived"]
    api.call("PUT", f"/api/projects/{arch['id']}/finance", {"budget_cents": 100}, expect=200)
    assert api.call("GET", f"/api/projects/{arch['id']}/finance", expect=200)[1]["budget_cents"] == 100


def test_deleting_the_project_deletes_its_costing(seeded):
    api, p = seeded["api"], seeded["project"]
    maker_on(api, "yoshi@test.com")
    api.call("PUT", f"/api/projects/{p['id']}/finance", {"hourly_rate_cents": 35000}, expect=200)
    api.call("DELETE", f"/api/projects/{p['id']}", expect=204)
    # Otro con el mismo nombre empieza sin costeo
    _, again = api.call("POST", "/api/projects", {"name": "Habit Tracker"}, expect=201)
    assert api.call("GET", f"/api/projects/{again['id']}/finance", expect=200)[1]["hourly_rate_cents"] is None
