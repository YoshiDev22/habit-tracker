"""Topes de tamaño: nada de lo que se guarda puede crecer sin límite.

Cada tope se prueba en los dos lados: el máximo entra, uno más no (422). Los topes
siguen a los maxlength de los formularios, así que usando la app nunca se alcanzan.
"""
from datetime import date, timedelta

from conftest import log_time, utc_now


def test_register_email_and_password(api):
    url = "/api/auth/register"
    assert api.call("POST", url, {"email": "sin-arroba", "password": "secret123"})[0] == 422
    assert api.call("POST", url, {"email": "con espacio@test.com", "password": "secret123"})[0] == 422
    assert api.call("POST", url, {"email": "@test.com", "password": "secret123"})[0] == 422
    assert api.call("POST", url, {"email": "x" * 250 + "@t.co", "password": "secret123"})[0] == 422
    assert api.call("POST", url, {"email": "corta@test.com", "password": "12345"})[0] == 422
    assert api.call("POST", url, {"email": "larga@test.com", "password": "x" * 129})[0] == 422
    api.call("POST", url, {"email": "ok@test.com", "password": "x" * 128}, expect=200)
    # El login no pasa por estos topes: una cuenta vieja sigue entrando
    assert api.call("POST", "/api/auth/login", form={"username": "ok@test.com", "password": "x" * 128})[0] == 200


def test_task_title_and_notes(api):
    api.login("tasks@test.com")
    assert api.call("POST", "/api/tasks", {"title": "x" * 201})[0] == 422
    assert api.call("POST", "/api/tasks", {"title": ""})[0] == 422
    assert api.call("POST", "/api/tasks", {"title": "t", "notes": "x" * 5001})[0] == 422
    _, t = api.call("POST", "/api/tasks", {"title": "x" * 200, "notes": "x" * 5000}, expect=201)
    url = f"/api/tasks/{t['id']}"
    assert api.call("PATCH", url, {"title": "x" * 201})[0] == 422
    assert api.call("PATCH", url, {"notes": "x" * 5001})[0] == 422
    api.call("PATCH", url, {"notes": None}, expect=200)
    # Estimado: de 1 minuto a 100 h
    for bad in (0, -5, 6001, "mucho"):
        assert api.call("PATCH", url, {"estimate_minutes": bad})[0] == 422, bad
    assert api.call("PATCH", url, {"estimate_minutes": 6000}, expect=200)[1]["estimate_minutes"] == 6000


def test_project_fields(api):
    api.login("projects@test.com")
    url = "/api/projects"
    assert api.call("POST", url, {"name": "x" * 81})[0] == 422
    assert api.call("POST", url, {"name": "p", "description": "x" * 201})[0] == 422
    assert api.call("POST", url, {"name": "p", "icon": "x" * 17})[0] == 422
    assert api.call("POST", url, {"name": "p", "color": "x" * 5000})[0] == 422
    _, p = api.call("POST", url, {"name": "x" * 80, "description": "x" * 200, "icon": "👨‍👩‍👧‍👦",
                                  "color": "#3498db"}, expect=201)
    assert api.call("PATCH", f"{url}/{p['id']}", {"name": "x" * 81})[0] == 422
    assert api.call("PATCH", f"{url}/{p['id']}", {"color": "red"})[0] == 422
    api.call("PATCH", f"{url}/{p['id']}", {"color": None}, expect=200)


def test_session_note_and_mode(seeded):
    api = seeded["api"]
    pid = seeded["project"]["id"]
    s = log_time(api, pid, None, 60, note="x" * 200)
    assert api.call("PATCH", f"/api/pomodoro/{s['id']}", {"note": "x" * 201})[0] == 422
    start = utc_now() - timedelta(minutes=5)
    body = {"project_id": pid, "session_date": date.today().isoformat(), "started_at": start.isoformat(),
            "ended_at": (start + timedelta(minutes=5)).isoformat(), "duration_seconds": 300,
            "planned_seconds": 300, "source": "timer"}
    assert api.call("POST", "/api/pomodoro", {**body, "note": "x" * 201})[0] == 422
    assert api.call("POST", "/api/pomodoro", {**body, "mode": "x" * 5000})[0] == 422
    for mode in ("focus", "short_break", "long_break"):
        api.call("POST", "/api/pomodoro", {**body, "mode": mode}, expect=201)
    # El sessionId de pomodoro.js mide ~22; el tope deja margen
    assert api.call("POST", "/api/pomodoro", {**body, "idempotency_key": "x" * 65})[0] == 422
    api.call("POST", "/api/pomodoro", {**body, "idempotency_key": "x" * 64}, expect=201)


def test_habit_day(api):
    api.login("days@test.com")
    day = date.today().isoformat()
    assert api.call("POST", "/api/habits", {"date": day, "habits": {f"h{i}": True for i in range(101)}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"x" * 41: True}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"gym": "x" * 5000}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"gym": {"a": 1}}})[0] == 422
    api.call("POST", "/api/habits", {"date": day, "habits": {f"h{i}": i % 2 == 0 for i in range(100)}}, expect=200)
    # Marcar un solo hábito: la clave con el mismo tope, y el día no pasa de 100
    assert api.call("PATCH", f"/api/habits/day/{day}", {"habit_key": "x" * 41, "done": True})[0] == 422
    assert api.call("PATCH", f"/api/habits/day/{day}", {"habit_key": "gym", "done": "x" * 5000})[0] == 422
    api.call("POST", "/api/habits/definitions", {"key": "nuevo", "label": "Nuevo"}, expect=201)
    assert api.call("PATCH", f"/api/habits/day/{day}", {"habit_key": "nuevo", "done": True})[0] == 422


def test_pause_length(api):
    api.login("pausas-tope@test.com")
    today = date.today()
    far = lambda n: str(today + timedelta(days=n))
    url = f"/api/habits/pauses?today={today}"
    assert api.call("POST", url, {"start_date": far(0), "end_date": far(365)})[0] == 422
    assert api.call("POST", url, {"start_date": "x" * 5000, "end_date": far(1)})[0] == 422
    api.call("POST", url, {"start_date": far(0), "end_date": far(29)}, expect=201)


def test_module_toggle(api):
    api.login("modulos-tope@test.com")
    # Solo los módulos de backend/modules.py, y solo un sí o un no
    assert api.call("PUT", "/api/auth/me/modules/" + "x" * 300, {"enabled": True})[0] == 404
    assert api.call("PUT", "/api/auth/me/modules/habits", {"enabled": "x" * 5000})[0] == 422
    api.call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)


def test_project_finance(api):
    from test_finance import maker_on
    api.login("topes@test.com")
    maker_on(api, "topes@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    url = f"/api/projects/{p['id']}/finance"
    for currency in ("MXN", "USD", "EUR", "CAD", "GBP", "COP", "ARS", "CLP", "PEN"):
        api.call("PUT", url, {"currency": currency}, expect=200)
    assert api.call("PUT", url, {"currency": "BTC"})[0] == 422
    assert api.call("PUT", url, {"currency": "usd"})[0] == 422
    assert api.call("PUT", url, {"hourly_rate_cents": -1})[0] == 422
    assert api.call("PUT", url, {"hourly_rate_cents": 1.5})[0] == 422, "cents are whole numbers"
    assert api.call("PUT", url, {"budget_cents": 100_000_000_001})[0] == 422
    api.call("PUT", url, {"budget_cents": 100_000_000_000}, expect=200)
    assert api.call("PUT", url, {"budget_minutes": 1_000_001})[0] == 422
    assert api.call("PUT", url, {"client_name": "x" * 121})[0] == 422
    api.call("PUT", url, {"client_name": "x" * 120}, expect=200)
    assert api.call("GET", "/api/projects/999999/finance")[0] == 404


def test_costs_and_categories(api):
    from test_finance import maker_on
    api.login("gastos-tope@test.com")
    maker_on(api, "gastos-tope@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = cats["categories"][0]["id"]
    ok = {"project_id": p["id"], "category_id": cat, "cost_date": date.today().isoformat(), "concept": "x"}
    assert api.call("POST", "/api/costs/categories", {"name": "x" * 41})[0] == 422
    api.call("POST", "/api/costs/categories", {"name": "x" * 40}, expect=201)
    assert api.call("POST", "/api/costs/categories", {"name": "y", "color": "rojo"})[0] == 422
    assert api.call("PATCH", f"/api/costs/categories/{cat}", {"order": -1})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "concept": "x" * 201})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "concept": ""})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "note": "x" * 501})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "quantity": 0})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "quantity": 1_000_001})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "unit_cost_cents": -1})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "unit_cost_cents": 100_000_000_001})[0] == 422
    assert api.call("POST", "/api/costs", {**ok, "cost_date": "ayer"})[0] == 422
    api.call("POST", "/api/costs", {**ok, "concept": "x" * 200, "note": "x" * 500, "quantity": 1_000_000,
                                    "unit_cost_cents": 100_000_000_000}, expect=201)


def test_work_calendar(api):
    api.login("calendario-tope@test.com")
    assert api.call("PUT", "/api/days/settings", {"timezone": "x" * 65})[0] == 422
    assert api.call("PUT", "/api/days/settings", {"timezone": "No/Existe"})[0] == 422
    assert api.call("PUT", "/api/days/settings", {"country": "MEX"})[0] == 422
    assert api.call("PUT", "/api/days/settings", {"country": "1X"})[0] == 422
    day = date.today().isoformat()
    assert api.call("POST", "/api/days", {"date": day, "name": "x" * 81})[0] == 422
    assert api.call("POST", "/api/days", {"date": day, "kind": "otro"})[0] == 422
    assert api.call("POST", "/api/days", {"date": "ayer"})[0] == 422
    api.call("POST", "/api/days", {"date": day, "name": "x" * 80}, expect=201)
    assert api.call("GET", "/api/days?year=1999")[0] == 422


def test_saved_report(api):
    api.login("reporte-tope@test.com")
    monday = date.today() - timedelta(days=date.today().weekday())
    assert api.call("POST", "/api/reports", {"kind": "anual", "period_start": monday.isoformat()})[0] == 422
    assert api.call("POST", "/api/reports", {"kind": "week", "period_start": "lunes"})[0] == 422
    assert api.call("POST", "/api/reports", {"kind": "week", "period_start": (monday + timedelta(days=2)).isoformat()})[0] == 422
