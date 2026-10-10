"""Fase 2 del panel (1.27): lo que cambia algo pasa por la protección CSRF y queda en
la bitácora, que sobrevive al borrado de la cuenta."""
import pytest
from sqlmodel import Session, select

from backend.admin_api import record_action
from backend.database import engine
from backend.models import AdminAction, User
from test_admin_auth import admin, token  # noqa: F401

PANEL = "http://testserver"   # el host del TestClient


def post(admin, path, body=None, origin=PANEL, content_type="application/json", jwt_token=None):
    headers = {"Cf-Access-Jwt-Assertion": jwt_token or token()}
    if origin is not None:
        headers["Origin"] = origin
    if content_type is not None:
        headers["Content-Type"] = content_type
    data = "{}" if body is None else body
    return admin.client.post(path, content=data, headers=headers)


@pytest.mark.parametrize("case, kwargs", [
    ("no Origin", {"origin": None}),
    ("another site", {"origin": "https://sitio-malo.example"}),
    ("same name, other port", {"origin": "http://testserver:8080"}),
    ("a form, not JSON", {"content_type": "application/x-www-form-urlencoded", "body": "a=1"}),
    ("text/plain (no preflight)", {"content_type": "text/plain"}),
    ("no Content-Type", {"content_type": None}),
])
def test_a_change_from_elsewhere_is_403_before_any_route(admin, case, kwargs):
    r = post(admin, "/api/no-existe", **kwargs)
    assert r.status_code == 403 and r.json() == {"detail": "Acceso denegado"}, (case, r.status_code)
    assert r.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_from_the_panel_it_reaches_the_route(admin):
    # Pasa la protección y llega al enrutador (que no tiene esa ruta: 404, no 403)
    assert post(admin, "/api/no-existe").status_code == 404
    assert post(admin, "/api/no-existe", content_type="application/json; charset=utf-8").status_code == 404


def test_the_log_lists_actions_and_survives_the_account(admin, api):
    api.login("se-ira@test.com")
    with Session(engine) as session:
        user_id = session.exec(select(User).where(User.email == "se-ira@test.com")).one().id
        record_action(session, "yoshi@test.com", "module", user_id, {"maker": False}, {"maker": True})
        session.commit()
    rows = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert [(a["action"], a["account_id"], a["before"], a["after"], a["admin"]) for a in rows] == \
        [("module", user_id, {"maker": False}, {"maker": True}, "yoshi@test.com")]
    assert admin(f"/api/actions?account_id={user_id + 999}", jwt_token=token()).json()["actions"] == []

    api.call("POST", "/api/auth/me/delete", {"password": "secret123", "mode": "now", "confirm": "BORRAR"}, expect=204)
    with Session(engine) as session:
        assert session.get(User, user_id) is None
        assert [a.account_id for a in session.exec(select(AdminAction)).all()] == [user_id]
