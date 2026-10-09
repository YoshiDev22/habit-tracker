"""El centro de avisos (1.26): pendientes que se calculan de los datos, avisos
informativos que se leen, guardado por cuenta."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend import main
from backend.database import engine
from backend.models import User
from backend.reports import generate_report, period_bounds
from test_metrics import post

TODAY = date.today()


def notices(api):
    return api.call("GET", f"/api/notices?today={TODAY}", expect=200)[1]


def by_kind(data, kind):
    return [n for n in data["notices"] if n["kind"] == kind]


def no_novedades(monkeypatch):
    monkeypatch.setattr(main, "NOVEDADES", [])


def test_a_session_to_review_is_pending_until_confirmed(api, monkeypatch):
    no_novedades(monkeypatch)
    api.login("avisos@test.com")
    _, project = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    s = post(api, project, None, TODAY - timedelta(days=2), 9, 480, needs_review=True)
    data = notices(api)
    [review] = by_kind(data, "review")
    assert review["status"] == "pending" and review["session_id"] == s["id"] and data["unread"] == 1
    api.call("PATCH", f"/api/pomodoro/{s['id']}", {"needs_review": False}, expect=200)
    data = notices(api)
    assert by_kind(data, "review")[0]["status"] == "done" and data["unread"] == 0


def test_a_missed_day_is_pending_until_marked_or_dismissed(api, monkeypatch):
    no_novedades(monkeypatch)
    api.login("ayer@test.com")
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer"}, expect=201)
    # Racha hasta anteayer; ayer vacío
    for i in (2, 3):
        api.call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": "leer", "done": True}, expect=200)
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    [missed] = by_kind(notices(api), "missed_day")
    assert missed["status"] == "pending" and missed["date"] == yesterday
    # Descartarlo deja de contar; marcar ese día lo vuelve "hecho"
    api.call("POST", f"/api/notices/{missed['id']}/dismiss", expect=204)
    data = notices(api)
    assert by_kind(data, "missed_day")[0]["status"] == "dismissed" and data["unread"] == 0
    api.call("PATCH", f"/api/habits/day/{yesterday}", {"habit_key": "leer", "done": True}, expect=200)
    assert by_kind(notices(api), "missed_day")[0]["status"] == "done"


def test_info_notices_are_read(api, monkeypatch):
    api.login("info@test.com")
    _, project = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    monday = TODAY - timedelta(days=TODAY.weekday() + 7)
    post(api, project, None, monday, 9, 60)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "info@test.com")).one()
        report_id = generate_report(session, user, "week", monday, TODAY, trigger="auto").id
        manual_id = generate_report(session, user, "month", period_bounds("month", monday)[0], TODAY).id
    monkeypatch.setattr(main, "NOVEDADES", [{"version": main.APP_VERSION, "date": None, "sections": [
        {"title": "Nuevas funciones", "items": ["algo"]}]}])
    data = notices(api)
    [ready] = by_kind(data, "report_ready")
    assert ready["report_id"] == report_id and "semanal de tiempo" in ready["title"] and not ready["read"]
    assert not any(n.get("report_id") == manual_id for n in data["notices"])   # el de a mano no avisa
    [news] = by_kind(data, "novedades")
    assert news["version"] == main.APP_VERSION and data["unread"] == 2
    api.call("POST", "/api/notices/read", {"ids": [ready["id"]]}, expect=204)
    assert notices(api)["unread"] == 1
    api.call("POST", "/api/notices/read", {}, expect=204)
    data = notices(api)
    assert data["unread"] == 0 and all(n["read"] for n in data["notices"] if n["status"] == "info")
    # Un informativo no se descarta: se lee
    assert api.call("POST", f"/api/notices/{news['id']}/dismiss")[0] == 409


def test_notices_are_private(api, monkeypatch):
    no_novedades(monkeypatch)
    api.login("dueno-avisos@test.com")
    _, project = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    post(api, project, None, TODAY - timedelta(days=1), 9, 480, needs_review=True)
    [mine] = by_kind(notices(api), "review")
    api.login("otro-avisos@test.com")
    assert notices(api)["notices"] == []
    assert api.call("POST", f"/api/notices/{mine['id']}/dismiss")[0] == 404
    api.call("POST", "/api/notices/read", {"ids": [mine["id"]]}, expect=204)   # no toca lo ajeno
    api.login("dueno-avisos@test.com")
    assert by_kind(notices(api), "review")[0]["status"] == "pending"
