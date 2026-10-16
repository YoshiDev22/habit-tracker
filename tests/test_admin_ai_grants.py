"""Textos de IA extra solo por hoy, desde el panel (1.27, Fase 2)."""
import json
from datetime import timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import AiGrant, User, utc_now_naive
from test_admin_actions import PANEL
from test_admin_auth import admin, token  # noqa: F401
from test_report_ai import MON, TODAY, generate, grant, provider, setup  # noqa: F401


def give(admin, user_id, pool="report", extra=2):
    return admin.client.post(f"/api/accounts/{user_id}/ai-grants", content=json.dumps({"pool": pool, "extra": extra}),
                             headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL,
                                      "Content-Type": "application/json"})


def me(api):
    return api.call("GET", "/api/auth/me", expect=200)[1]


def try_generate(api):
    return api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                             "today": TODAY.isoformat()})


def test_extra_texts_only_today(admin, api, provider):
    setup(api)
    grant("ia@test.com")
    user_id = me(api)["id"]
    for _ in range(3):                                  # el límite de la instancia (3 en las pruebas)
        assert generate(api)["text_source"] == "ai"
    status, err = try_generate(api)
    assert status == 502 and "límite de 3" in err["detail"]

    r = give(admin, user_id, extra=2)
    assert r.status_code == 200 and r.json()["extra"] == 2
    usage = api.call("GET", "/api/reports/ai-usage", expect=200)[1]
    assert usage["limit"] == 5 and usage["remaining"] == 2      # el aviso y el bloqueo dicen lo mismo
    for _ in range(2):
        assert generate(api)["text_source"] == "ai"
    status, err = try_generate(api)
    assert status == 502 and "límite de 5" in err["detail"]
    assert len(provider["sent"]) == 5

    # El panel ve el uso de hoy con su extra; los costos no cambiaron
    pools = admin(f"/api/accounts/{user_id}/ai", jwt_token=token()).json()["pools"]
    assert (pools["report"]["used_today"], pools["report"]["limit"], pools["report"]["extra_today"]) == (5, 5, 2)
    assert pools["costs"]["extra_today"] == 0

    # Mañana: la fila es de ayer y vuelve el límite normal
    with Session(engine) as session:
        row = session.exec(select(AiGrant).where(AiGrant.user_id == user_id)).one()
        row.day = row.day - timedelta(days=1)
        session.add(row)
        session.commit()
    assert api.call("GET", "/api/reports/ai-usage", expect=200)[1]["limit"] == 3

    log = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert [(a["action"], a["account_id"], a["before"]["extra"], a["after"]["extra"]) for a in log] == \
        [("ai_grant", user_id, 0, 2)]


def test_giving_more_the_same_day_adds_up_to_a_cap(admin, api):
    api.login("extra@test.com")
    user_id = me(api)["id"]
    assert give(admin, user_id, extra=30).json()["extra"] == 30
    assert give(admin, user_id, extra=20).json()["extra"] == 50
    r = give(admin, user_id, extra=1)
    assert r.status_code == 409 and "50" in r.json()["detail"]
    assert give(admin, user_id, pool="costs", extra=5).json()["extra"] == 5      # otro contador, aparte
    for bad in ({"pool": "report", "extra": 0}, {"pool": "report", "extra": 51}, {"pool": "otro", "extra": 1},
                {"pool": "report", "extra": "3"}):
        r = admin.client.post(f"/api/accounts/{user_id}/ai-grants", content=json.dumps(bad),
                              headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL,
                                       "Content-Type": "application/json"})
        assert r.status_code == 422, (bad, r.status_code)
    assert give(admin, 999999).status_code == 404
    with Session(engine) as session:
        rows = session.exec(select(AiGrant).where(AiGrant.user_id == user_id)).all()
        assert sorted((g.pool, g.extra, g.day) for g in rows) == [("costs", 5, utc_now_naive().date()),
                                                                   ("report", 50, utc_now_naive().date())]


def test_grants_go_with_the_account(admin, api):
    api.login("extra-se-va@test.com")
    user_id = me(api)["id"]
    give(admin, user_id)
    api.call("POST", "/api/auth/me/delete", {"password": "secret123", "mode": "now", "confirm": "BORRAR"}, expect=204)
    with Session(engine) as session:
        assert session.exec(select(AiGrant)).all() == [] and session.get(User, user_id) is None
