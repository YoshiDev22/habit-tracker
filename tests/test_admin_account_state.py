"""Desactivar, reactivar y cancelar un borrado desde el panel (1.27, Fase 2)."""
import json

from sqlmodel import Session, select

from backend.database import engine
from backend.models import Task, User
from conftest import PASSWORD
from test_admin_actions import PANEL
from test_admin_auth import admin, token  # noqa: F401


def send(admin, method, path, body=None):
    return admin.client.request(method, path, content=json.dumps(body or {}),
                                headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL,
                                         "Content-Type": "application/json"})


def login(api, email, password=PASSWORD):
    return api.call("POST", "/api/auth/login", form={"username": email, "password": password})


def test_deactivating_logs_out_at_once_and_keeps_the_data(admin, api):
    api.login("desactivar@test.com")
    api.call("POST", "/api/tasks", {"title": "Algo mío"}, expect=201)
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    old_token = api.token

    r = send(admin, "PUT", f"/api/accounts/{me['id']}/active", {"active": False})
    assert r.status_code == 200 and r.json() == {"id": me["id"], "active": False}
    assert api.call("GET", "/api/auth/me")[0] == 401                    # fuera en la siguiente petición
    status, body = login(api, "desactivar@test.com")
    assert status == 403 and "desactivada" in body["detail"]
    # Con la contraseña equivocada no dice nada de la cuenta
    status, body = login(api, "desactivar@test.com", "otra-cosa")
    assert status == 401 and "desactivada" not in body["detail"]
    with Session(engine) as session:
        assert len(session.exec(select(Task).where(Task.user_id == me["id"])).all()) >= 1

    assert send(admin, "PUT", f"/api/accounts/{me['id']}/active", {"active": True}).json()["active"] is True
    api.token = old_token
    assert api.call("GET", "/api/auth/me")[0] == 401                    # el token de antes no revive
    status, body = login(api, "desactivar@test.com")
    assert status == 200
    api.token = body["access_token"]
    assert api.call("GET", "/api/tasks", expect=200)[1]["total"] >= 1   # todo sigue ahí

    log = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert [(a["action"], a["before"], a["after"]) for a in log] == [
        ("account", {"active": False}, {"active": True}), ("account", {"active": True}, {"active": False})]
    # Lo mismo otra vez no se anota
    send(admin, "PUT", f"/api/accounts/{me['id']}/active", {"active": True})
    assert len(admin("/api/actions", jwt_token=token()).json()["actions"]) == 2
    accounts = {a["id"]: a for a in admin("/api/accounts", jwt_token=token()).json()["accounts"]}
    assert accounts[me["id"]]["active"] is True


def test_cancel_a_scheduled_deletion(admin, api):
    api.login("se-iba@test.com")
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    assert send(admin, "POST", f"/api/accounts/{me['id']}/keep").status_code == 409     # no tenía borrado
    api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "later"}, expect=200)
    with Session(engine) as session:
        assert session.get(User, me["id"]).delete_after is not None
    r = send(admin, "POST", f"/api/accounts/{me['id']}/keep")
    assert r.status_code == 200 and r.json()["delete_after"] is None
    with Session(engine) as session:
        assert session.get(User, me["id"]).delete_after is None
    [entry] = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert entry["action"] == "keep" and entry["after"] == {"delete_after": None}


def test_state_changes_refuse_bad_input(admin, api):
    api.login("estado@test.com")
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    for bad in ({"active": "no"}, {"active": 0}, {}):
        assert send(admin, "PUT", f"/api/accounts/{me['id']}/active", bad).status_code == 422, bad
    assert send(admin, "PUT", "/api/accounts/999999/active", {"active": False}).status_code == 404
    assert send(admin, "POST", "/api/accounts/999999/keep").status_code == 404
    assert api.call("GET", "/api/auth/me")[0] == 200
