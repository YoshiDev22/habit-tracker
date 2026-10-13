"""La API del panel (1.27, Fase 1, solo lectura): cuenta, nunca enseña lo que escribe
cada persona; correos enmascarados; todo detrás del JWT de Access."""
import json
from datetime import date

from sqlmodel import Session

from backend.database import engine
from backend.models import AiCall, utc_now_naive
from conftest import log_time
from test_admin_auth import admin, token  # noqa: F401  (la fixture del panel)
from test_finance import maker_on

TODAY = date.today().isoformat()
# Todo lo que un usuario escribe lleva esta marca: no puede salir del panel
MARK = "ZQX"


def sow_marks(api):
    """yoshi@test.com escribe en cada lugar donde se puede escribir algo."""
    api.call("PATCH", "/api/auth/me", {"display_name": f"{MARK}-alias", "first_name": f"{MARK}-nombre"}, expect=200)
    _, p = api.call("POST", "/api/projects", {"name": f"{MARK}-proyecto", "description": f"{MARK}-descr"}, expect=201)
    _, t = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": f"{MARK}-tarea", "notes": f"{MARK}-notas"},
                    expect=201)
    api.call("POST", f"/api/tasks/{t['id']}/comments", {"body": f"{MARK}-comentario"}, expect=201)
    api.call("POST", f"/api/tasks/{t['id']}/checklist", {"text": f"{MARK}-check"}, expect=201)
    api.call("POST", "/api/tags", {"name": f"{MARK}-etiqueta"}, expect=201)
    api.call("POST", "/api/habits/definitions", {"key": "zqx", "label": f"{MARK}-habito"}, expect=201)
    api.call("PUT", f"/api/habits/notes/{TODAY}/zqx", {"text": f"{MARK}-nota-habito"}, expect=200)
    log_time(api, p["id"], t["id"], 600, note=f"{MARK}-sesion")
    maker_on(api, "yoshi@test.com")
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    api.call("POST", "/api/costs", {"project_id": p["id"], "category_id": cats["categories"][0]["id"],
                                    "cost_date": TODAY, "concept": f"{MARK}-gasto", "quantity": 1,
                                    "unit_cost_cents": 1000}, expect=201)
    api.call("POST", "/api/feedback", {"text": f"Falla {MARK}-FEEDBACK <script>alert(1)</script>"}, expect=201)


def sow_ai(user_ids):
    with Session(engine) as session:
        session.add(AiCall(user_id=user_ids[0], purpose="report", model="m", ok=True, input_tokens=100, output_tokens=50))
        session.add(AiCall(user_id=user_ids[0], purpose="costs", model="m", ok=False, error="timeout"))
        session.commit()


def get(admin, path):
    r = admin(path, jwt_token=token())
    assert r.status_code == 200, (path, r.status_code, r.text)
    return r.json()


def test_every_panel_route_needs_the_admin(admin, seeded):
    from backend import admin_main
    paths = [r.path.replace("{user_id}", "1") for r in admin_main.app.routes
             if r.path.startswith("/api") and "GET" in getattr(r, "methods", ())]
    assert len(paths) >= 6, paths
    for path in paths:
        assert admin(path).status_code == 403, path
        assert admin(path, jwt_token=token(email="usuario@test.com")).status_code == 403, path


def test_it_counts_and_never_shows_what_people_write(admin, seeded):
    api = seeded["api"]
    sow_marks(api)
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    other = seeded["other"].call("GET", "/api/auth/me", expect=200)[1]
    sow_ai([me["id"]])

    summary = get(admin, "/api/summary")
    assert summary["accounts"] == 2 and summary["new_7d"] == 2 and summary["active_7d"] == 2
    assert summary["feedback_open"] == 1 and summary["ai_today"] == {"ok": 1, "failed": 1}
    # Las gráficas del Resumen (paso 7): solo conteos
    weeks = summary["signups_by_week"]
    assert len(weeks) == 12 and weeks[-1]["count"] == 2 and sum(w["count"] for w in weeks) == 2
    assert summary["activity"] == {"day": 2, "week": 0, "month": 0, "older": 0, "never": 0}
    assert summary["modules_in_use"]["habits"] == 2 and summary["modules_in_use"]["maker"] == 1

    accounts = {a["id"]: a for a in get(admin, "/api/accounts")["accounts"]}
    mine = accounts[me["id"]]
    assert mine["email"] == "y•••@test.com" and accounts[other["id"]]["email"] == "o•••@test.com"
    assert mine["counts"]["tasks"] == 6 and mine["counts"]["habits"] == 1 and mine["counts"]["costs"] == 1
    assert mine["counts"]["sessions"] == 5 and mine["counts"]["boards"] >= 1
    assert accounts[other["id"]]["counts"]["tasks"] == 1
    assert mine["modules"]["maker"] == {"enabled": True, "allowed": True}
    assert mine["ai"]["today"] == {"ok": 1, "failed": 1, "tokens": 150}

    ai = get(admin, "/api/ai")
    assert {(d["purpose"], d["ok"], d["failed"]) for d in ai["days"]} == {("report", 1, 0), ("costs", 0, 1)}
    assert ai["errors"] == [{"error": "timeout", "count": 1}]

    from backend.admin_api import record_action
    with Session(engine) as session:
        # Un administrador que no es ninguna de las cuentas: así un correo de cuenta en la
        # bitácora sería una fuga, no el "quién lo hizo"
        record_action(session, "admin@panel.test", "module", me["id"], {"maker": {"enabled": False, "allowed": False}},
                      {"maker": {"enabled": False, "allowed": True}})
        session.commit()
    log = get(admin, "/api/actions")
    assert [(a["account"], a["admin"]) for a in log["actions"]] == [("y•••@test.com", "admin@panel.test")]

    feedback = get(admin, "/api/feedback")["feedback"]
    assert [f["text"] for f in feedback] == [f"Falla {MARK}-FEEDBACK <script>alert(1)</script>"]
    assert feedback[0]["account"] == {"id": me["id"], "email": "y•••@test.com"}

    # Todo lo que escribieron las dos cuentas, leído de la app: lo sembrado aquí y lo de `seeded`
    written = set()
    for client in (api, seeded["other"]):
        written |= {t["title"] for t in client.call("GET", "/api/tasks", expect=200)[1]["tasks"]}
        written |= {p["name"] for p in client.call("GET", "/api/projects?include_inactive=true", expect=200)[1]["projects"]}
        written |= {h["label"] for h in client.call("GET", "/api/habits/definitions?include_inactive=true", expect=200)[1]["habits"]}
        written |= {t["name"] for t in client.call("GET", "/api/tags", expect=200)[1]["tags"]}
    written = {w for w in written if len(w) >= 4 and w != "Sin asignar"}   # "Sin asignar" lo pone la app
    assert {"Corrección de Pomodoros", "Tarea ajena", f"{MARK}-tarea"} <= written

    # Nada de lo escrito sale, ni el correo completo; del reporte de problema, solo su texto
    for path, body in [("/api/summary", summary), ("/api/accounts", accounts), ("/api/ai", ai),
                       ("/api/feedback", feedback), ("/api/actions", log)]:
        text = json.dumps(body, ensure_ascii=False, default=str)
        leaked = text.replace(f"{MARK}-FEEDBACK", "")
        assert MARK not in leaked, (path, leaked[leaked.index(MARK) - 60:leaked.index(MARK) + 40])
        assert not [w for w in written if w in leaked], (path, [w for w in written if w in leaked])
        assert "yoshi@test.com" not in text and "otro@test.com" not in text, path


def test_the_full_email_only_when_asked(admin, seeded):
    me = seeded["api"].call("GET", "/api/auth/me", expect=200)[1]
    assert get(admin, f"/api/accounts/{me['id']}/email") == {"id": me["id"], "email": "yoshi@test.com"}
    assert admin("/api/accounts/999999/email", jwt_token=token()).status_code == 404


def test_feedback_filter(admin, api):
    api.login("filtro@test.com")
    api.call("POST", "/api/feedback", {"text": "Un problema abierto"}, expect=201)
    assert len(get(admin, "/api/feedback?status=open")["feedback"]) == 1
    assert get(admin, "/api/feedback?status=closed")["feedback"] == []
    assert admin("/api/feedback?status=borrado", jwt_token=token()).status_code == 422


def test_accounts_from_before_have_no_signup_date(admin, api):
    from sqlmodel import select
    from backend.models import User
    api.login("vieja@test.com")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "vieja@test.com")).one()
        user.created_at = None
        session.add(user)
        session.commit()
    summary = get(admin, "/api/summary")
    assert summary["unknown_signup"] == 1 and summary["new_7d"] == 0


def test_activity_groups_never_overlap(admin, api):
    from datetime import timedelta
    from sqlmodel import select
    from backend.models import User, utc_now_naive
    now = utc_now_naive()
    ages = {"hoy@test.com": timedelta(hours=3), "semana@test.com": timedelta(days=3),
            "mes@test.com": timedelta(days=20), "vieja@test.com": timedelta(days=90), "nunca@test.com": None}
    for email in ages:
        api.login(email)
    with Session(engine) as session:
        for email, age in ages.items():
            user = session.exec(select(User).where(User.email == email)).one()
            user.last_seen_at = None if age is None else now - age
            session.add(user)
        session.commit()
    assert get(admin, "/api/summary")["activity"] == {"day": 1, "week": 1, "month": 1, "older": 1, "never": 1}
