"""Avisos desde el panel (1.27, Fase 2, paso 6): para todas las cuentas, con las mismas
reglas que scripts/announce.py, y para una sola cuenta."""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from sqlmodel import Session, select

from backend import announcement_rules
from backend.database import engine
from backend.models import AccountMessage, User
from test_admin_actions import PANEL
from test_admin_auth import admin, token  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today().isoformat()


def send(admin, path, body=None):
    return admin.client.post(path, content=json.dumps(body or {}),
                             headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL,
                                      "Content-Type": "application/json"})


def bell(api, kind):
    data = api.call("GET", f"/api/notices?today={TODAY}", expect=200)[1]
    return [n for n in data["notices"] if n["kind"] == kind]


def me(api):
    return api.call("GET", "/api/auth/me", expect=200)[1]["id"]


def test_publish_for_everyone_and_end_it(admin, api):
    api.login("aviso-uno@test.com")
    r = send(admin, "/api/announcements", {"title": "Mantenimiento", "body": "Hoy a las 22:00, 5 min.", "hours": 24})
    assert r.status_code == 200
    ann_id = r.json()["id"]
    for email in ("aviso-uno@test.com", "aviso-dos@test.com"):
        api.login(email)
        [notice] = bell(api, "announcement")
        assert notice["title"] == "Mantenimiento" and notice["detail"] == "Hoy a las 22:00, 5 min."
    listed = admin("/api/announcements", jwt_token=token()).json()
    assert listed["max_current"] == 3 and [(a["id"], a["current"]) for a in listed["announcements"]] == [(ann_id, True)]

    assert send(admin, f"/api/announcements/{ann_id}/end").status_code == 200
    assert bell(api, "announcement") == []
    assert send(admin, f"/api/announcements/{ann_id}/end").status_code == 409        # ya terminó
    assert send(admin, "/api/announcements/999999/end").status_code == 404
    log = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert [a["action"] for a in log] == ["announcement_end", "announcement"]


def test_the_cap_and_the_wait_are_the_same_as_the_script(admin, monkeypatch):
    # Un doble clic: el segundo espera
    assert send(admin, "/api/announcements", {"title": "Uno"}).status_code == 200
    r = send(admin, "/api/announcements", {"title": "Dos"})
    assert r.status_code == 429 and "espera" in r.json()["detail"]
    monkeypatch.setattr(announcement_rules, "COOLDOWN_SECONDS", 0)
    assert send(admin, "/api/announcements", {"title": "Dos"}).status_code == 200
    assert send(admin, "/api/announcements", {"title": "Tres"}).status_code == 200
    r = send(admin, "/api/announcements", {"title": "Cuatro"})
    assert r.status_code == 409 and "vigentes" in r.json()["detail"]
    # announce.py, en el servidor, se niega igual
    from backend.database import engine as db_engine
    env = {"PATH": "", "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "DATABASE_URL": str(db_engine.url)}
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "announce.py"), "--title", "Cuatro"], cwd=ROOT,
                         env=env, capture_output=True, text=True)
    assert out.returncode == 1 and "vigentes" in out.stderr, (out.stdout, out.stderr)


def test_bad_announcements_are_refused(admin):
    for bad in ({"title": ""}, {"title": "   "}, {"title": "x" * 81}, {"title": "t", "body": "x" * 501},
                {"title": "t", "hours": 0}, {"title": "t", "hours": "24"}, {"title": "t", "hours": 721}):
        assert send(admin, "/api/announcements", bad).status_code == 422, bad
    assert admin("/api/announcements", jwt_token=token()).json()["announcements"] == []


def test_a_message_for_one_account(admin, api):
    api.login("mensaje@test.com")
    target = me(api)
    r = send(admin, f"/api/accounts/{target}/messages", {"title": "Revisa tu racha", "body": "Hay un día raro."})
    assert r.status_code == 200
    [msg] = bell(api, "message")
    assert (msg["title"], msg["detail"], msg["read"]) == ("Revisa tu racha", "Hay un día raro.", False)
    api.login("otra-mensaje@test.com")
    assert bell(api, "message") == []
    for bad in ({"title": ""}, {"title": "x" * 81}, {"title": "t", "body": "x" * 501}):
        assert send(admin, f"/api/accounts/{target}/messages", bad).status_code == 422, bad
    assert send(admin, "/api/accounts/999999/messages", {"title": "Hola"}).status_code == 404
    assert [a["action"] for a in admin("/api/actions", jwt_token=token()).json()["actions"]] == ["message"]


def test_giving_ai_or_a_module_tells_the_person(admin, api):
    api.login("regalo@test.com")
    target = me(api)
    send(admin, f"/api/accounts/{target}/ai-grants", {"pool": "report", "extra": 5})
    admin.client.put(f"/api/accounts/{target}/modules/maker", content=json.dumps({"allowed": True}),
                     headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL, "Content-Type": "application/json"})
    # Quitar el acceso no avisa
    admin.client.put(f"/api/accounts/{target}/modules/maker", content=json.dumps({"allowed": False}),
                     headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL, "Content-Type": "application/json"})
    titles = sorted(n["title"] for n in bell(api, "message"))
    assert titles == ["Te dimos 5 textos más de IA hoy", "Ya tienes acceso al plan Maker"]


def test_messages_go_with_the_account(admin, api):
    api.login("mensaje-se-va@test.com")
    target = me(api)
    send(admin, f"/api/accounts/{target}/messages", {"title": "Hola"})
    api.call("POST", "/api/auth/me/delete", {"password": "secret123", "mode": "now", "confirm": "BORRAR"}, expect=204)
    with Session(engine) as session:
        assert session.exec(select(AccountMessage)).all() == [] and session.get(User, target) is None
