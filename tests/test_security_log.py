"""Eventos de seguridad (1.27, paso 8 del panel): solo lo que falla o delata un abuso,
agrupado por hora, IP y cuenta, 30 días."""
import json
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from backend import security_log
from backend.database import engine
from backend.models import SecurityEvent, User, utc_now_naive
from conftest import PASSWORD
from test_admin_actions import PANEL
from test_admin_auth import admin, token  # noqa: F401
from test_report_ai import MON, TODAY, generate, grant, provider, setup  # noqa: F401


# El cliente de las pruebas de API no trae IP: la app anota la que ve, "unknown"
CLIENT = "unknown"


def events():
    with Session(engine) as session:
        rows = [(e.kind, e.ip, e.user_id, e.count) for e in session.exec(select(SecurityEvent)).all()]
    return sorted(rows, key=lambda e: (e[0], e[1], e[2] or 0, e[3]))


def user_id(email):
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().id


def login(api, email, password):
    return api.call("POST", "/api/auth/login", form={"username": email, "password": password})[0]


def test_normal_use_writes_nothing(api):
    api.login("normal@test.com")                     # crea la cuenta: el único evento
    api.call("GET", "/api/auth/me", expect=200)
    api.call("GET", "/api/projects", expect=200)
    assert login(api, "normal@test.com", PASSWORD) == 200
    assert events() == [("register", CLIENT, user_id("normal@test.com"), 1)]


def test_wrong_passwords_are_one_row_per_hour(api):
    api.login("victima@test.com")
    for _ in range(3):
        assert login(api, "victima@test.com", "equivocada") == 401
    assert login(api, "no-existe@test.com", "equivocada") == 401
    uid = user_id("victima@test.com")
    assert [e for e in events() if e[0] == "login_failed"] == [
        ("login_failed", CLIENT, None, 1), ("login_failed", CLIENT, uid, 3)]
    # Al pasarse del límite, el bloqueo también queda
    for _ in range(10):
        login(api, "victima@test.com", "equivocada")
    assert ("login_blocked", CLIENT, None, 4) in events()
    with Session(engine) as session:
        assert len(session.exec(select(SecurityEvent).where(SecurityEvent.kind == "login_failed")).all()) == 2


def test_rejected_tokens_say_why(api):
    api.login("tokens@test.com")
    uid = user_id("tokens@test.com")
    good = api.token
    api.token = good[:-4] + ("aaaa" if not good.endswith("aaaa") else "bbbb")
    assert api.call("GET", "/api/auth/me")[0] == 401
    api.token = good
    with Session(engine) as session:
        user = session.get(User, uid)
        user.token_version = (user.token_version or 0) + 1
        session.add(user)
        session.commit()
    assert api.call("GET", "/api/auth/me")[0] == 401
    api.login("tokens@test.com")
    with Session(engine) as session:
        user = session.get(User, uid)
        user.is_active = False
        session.add(user)
        session.commit()
    assert api.call("GET", "/api/auth/me")[0] == 401
    kinds = {(e[0], e[2]) for e in events()}
    assert {("token_invalid", None), ("token_revoked", uid), ("account_inactive", uid)} <= kinds


def test_password_in_my_profile_and_the_limits(api):
    api.login("perfil@test.com")
    uid = user_id("perfil@test.com")
    assert api.call("POST", "/api/auth/me/password", {"current_password": "mal", "new_password": "nueva123"})[0] == 400
    for i in range(6):
        api.call("POST", "/api/feedback", {"text": f"Un problema número {i}"})
    found = events()
    assert ("password_failed", CLIENT, uid, 1) in found and ("feedback_limit", CLIENT, uid, 1) in found


def test_ai_limit(api, provider):
    setup(api)
    grant("ia@test.com")
    for _ in range(3):
        generate(api)
    api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(), "today": TODAY.isoformat()})
    assert ("ai_limit", "", user_id("ia@test.com"), 1) in events()


def test_the_panel_logs_its_rejections(admin):
    assert admin("/api/me").status_code == 403
    r = admin.client.post("/api/no-existe", content="{}", headers={"Cf-Access-Jwt-Assertion": token(),
                                                                  "Content-Type": "application/json"})
    assert r.status_code == 403
    found = {e[0] for e in events()}
    assert {"admin_denied", "admin_csrf"} <= found
    # Con el Tunnel, la IP real llega en Cf-Connecting-Ip
    admin("/api/me", **{"Cf-Connecting-Ip": "203.0.113.9"})
    assert ("admin_denied", "203.0.113.9", None, 1) in events()


def test_a_failing_log_never_breaks_the_request(api, monkeypatch):
    api.login("robusta@test.com")

    def broken(*args, **kwargs):
        raise RuntimeError("la base se cayó")

    monkeypatch.setattr(security_log, "Session", broken)
    assert login(api, "robusta@test.com", "equivocada") == 401      # la respuesta de siempre
    assert login(api, "robusta@test.com", PASSWORD) == 200
    with pytest.raises(ValueError):
        security_log.record("un-tipo-que-no-existe")


def test_kept_30_days_and_gone_with_the_account(admin, api):
    api.login("se-va-seg@test.com")
    uid = user_id("se-va-seg@test.com")
    login(api, "se-va-seg@test.com", "equivocada")
    login(api, "nadie@test.com", "equivocada")
    with Session(engine) as session:
        session.add(SecurityEvent(hour=utc_now_naive() - timedelta(days=31), kind="login_failed", ip="198.51.100.1",
                                  count=5))
        session.commit()
    admin("/api/security", jwt_token=token())                      # el panel limpia lo viejo al leer
    assert all(e[1] != "198.51.100.1" for e in events())
    api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "now", "confirm": "BORRAR"}, expect=204)
    left = events()
    assert all(e[2] != uid for e in left) and ("login_failed", CLIENT, None, 1) in left


def seed(kind, ip, count, user=None, hours_ago=0):
    with Session(engine) as session:
        hour = (utc_now_naive() - timedelta(hours=hours_ago)).replace(minute=0, second=0, microsecond=0)
        session.add(SecurityEvent(hour=hour, kind=kind, ip=ip, user_id=user, count=count))
        session.commit()


def test_panel_alerts_and_counts(admin, api):
    api.login("alertas@test.com")
    uid = user_id("alertas@test.com")
    seed("login_failed", "203.0.113.50", 25)
    seed("login_failed", "203.0.113.60", 5)
    seed("register", "203.0.113.70", 6)
    seed("token_revoked", "203.0.113.80", 30, user=uid)
    data = admin("/api/security", jwt_token=token()).json()
    texts = [a["text"] for a in data["alerts"]]
    assert "25 contraseñas equivocadas desde 203.0.113.50 en una hora" in texts
    assert not any("203.0.113.60" in t for t in texts)                         # 5 no llega al umbral
    assert "6 cuentas nuevas desde 203.0.113.70 en un día" in texts
    assert "30 tokens de sesiones cerradas de a•••@test.com en un día" in texts
    assert data["top_ips"][0] == {"ip": "203.0.113.80", "count": 30, "kinds": {"token_revoked": 30}}
    assert data["proxy_warning"] is False
    assert "alertas@test.com" not in json.dumps(data, ensure_ascii=False)          # enmascarada


def test_the_panel_warns_when_it_sees_the_proxy(admin):
    seed("login_failed", "127.0.0.1", 15)
    seed("token_invalid", "10.0.0.2", 3)
    seed("login_failed", "203.0.113.5", 1)
    assert admin("/api/security", jwt_token=token()).json()["proxy_warning"] is True
