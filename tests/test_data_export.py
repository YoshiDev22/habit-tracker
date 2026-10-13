"""Descargar mis datos (1.28, BACKLOG 39): GET /api/auth/me/export."""
import json

from sqlmodel import Session, select

from backend.database import engine
from backend.models import SecurityEvent, User
from test_accounts import rows_of


def user_id(email):
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().id


def test_the_export_has_everything_a_deletion_would_remove(seeded):
    api = seeded["api"]
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer", "icon": "📚", "color": "#27ae60"},
             expect=201)
    api.call("POST", "/api/feedback", {"text": "Algo falló al guardar"}, expect=201)
    uid = user_id("yoshi@test.com")

    _, data = api.call("GET", "/api/auth/me/export", expect=200)

    # Lo mismo que borra purge_user(): cada tabla con user_id, con todas sus filas
    expected = rows_of(uid)
    assert set(data["tables"]) == set(expected)
    assert {name: len(rows) for name, rows in data["tables"].items()} == expected
    assert expected["habits"] >= 1 and expected["feedback"] == 1 and expected["tasks"] == 5

    # La cuenta, sin lo que solo sirve para la sesión
    account = data["account"]
    assert account["email"] == "yoshi@test.com" and account["display_name"] == "Yoshio"
    assert "hashed_password" not in account and "token_version" not in account
    assert data["version"] and data["exported_at"]

    # Nada de la otra cuenta
    dump = json.dumps(data, ensure_ascii=False)
    assert "Tarea ajena" not in dump and "Ajeno" not in dump and "otro@test.com" not in dump
    assert all(row["user_id"] == uid for rows in data["tables"].values() for row in rows)


def test_the_export_needs_a_session_and_has_a_daily_limit(api):
    assert api.call("GET", "/api/auth/me/export")[0] == 401
    api.login("limite@test.com")
    for _ in range(5):
        api.call("GET", "/api/auth/me/export", expect=200)
    status, body = api.call("GET", "/api/auth/me/export")
    assert status == 429 and "5 veces hoy" in body["detail"]
    with Session(engine) as session:
        events = session.exec(select(SecurityEvent).where(SecurityEvent.kind == "export_limit")).all()
    assert len(events) == 1 and events[0].user_id == user_id("limite@test.com")
