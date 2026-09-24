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


def test_habit_day(api):
    api.login("days@test.com")
    day = date.today().isoformat()
    assert api.call("POST", "/api/habits", {"date": day, "habits": {f"h{i}": True for i in range(101)}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"x" * 41: True}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"gym": "x" * 5000}})[0] == 422
    assert api.call("POST", "/api/habits", {"date": day, "habits": {"gym": {"a": 1}}})[0] == 422
    api.call("POST", "/api/habits", {"date": day, "habits": {f"h{i}": i % 2 == 0 for i in range(100)}}, expect=200)
