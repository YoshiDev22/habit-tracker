"""Reportes guardados (épica 30, Fase 4): periodos, generación, texto y el timer."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import Report, User
from backend.report_text import build_text, clock, hours
from backend.reports import due_periods, generate_due_reports, period_bounds
from test_metrics import MON, TUE, WED, SUN, post

TODAY = date.today()
THIS_MON = TODAY - timedelta(days=TODAY.weekday())


def setup(api, email="reportes@test.com"):
    api.login(email)
    _, project = api.call("POST", "/api/projects", {"name": "Tesis", "color": "#8e44ad"}, expect=201)
    _, task = api.call("POST", "/api/tasks", {"project_id": project["id"], "title": "Capítulo 2"}, expect=201)
    return project, task


def user_row(session, email):
    return session.exec(select(User).where(User.email == email)).one()


def test_periods():
    assert period_bounds("week", date(2026, 10, 8)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert period_bounds("month", date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert period_bounds("month", date(2028, 2, 14)) == (date(2028, 2, 1), date(2028, 2, 29))
    # El lunes 12 ya terminó la semana del 5; el 1 de noviembre, octubre
    assert due_periods("week", date(2026, 10, 12))[-1] == date(2026, 10, 5)
    assert due_periods("week", date(2026, 10, 11))[-1] == date(2026, 9, 28)
    assert due_periods("month", date(2026, 11, 1)) == [date(2026, 9, 1), date(2026, 10, 1)]
    assert due_periods("month", date(2026, 1, 5)) == [date(2025, 11, 1), date(2025, 12, 1)]


def test_generate_list_and_replace(api):
    project, task = setup(api)
    post(api, project, task, MON, 9, 120)
    post(api, project, task, TUE, 10, 90)
    post(api, project, task, MON - timedelta(days=7), 9, 60)   # semana anterior: para comparar

    _, rep = api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    assert rep["period_end"] == SUN.isoformat() and rep["through"] == SUN.isoformat()
    assert rep["total_seconds"] == 210 * 60 and rep["trigger"] == "manual" and rep["text_source"] == "rules"
    assert rep["metrics"]["previous"]["total_seconds"] == 3600
    assert rep["metrics"]["by_project"][0]["name"] == "Tesis"
    assert rep["text"]["summary"].startswith("Registraste 3 h 30 min en 2 días")
    assert "250 % más que la semana anterior (1 h)" in rep["text"]["summary"]

    # Regenerar reemplaza: mismo id, cifras nuevas
    post(api, project, task, WED, 9, 30)
    _, again = api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                                 "today": TODAY.isoformat()}, expect=200)
    assert again["id"] == rep["id"] and again["total_seconds"] == 240 * 60
    _, lst = api.call("GET", "/api/reports", expect=200)
    assert [r["id"] for r in lst["reports"]] == [rep["id"]]
    assert "metrics" not in lst["reports"][0]
    _, one = api.call("GET", f"/api/reports/{rep['id']}", expect=200)
    assert one["total_seconds"] == 240 * 60 and one["text"]["observations"]


def test_current_period_goes_until_today(api):
    project, task = setup(api)
    post(api, project, task, TODAY, 9, 45)
    _, rep = api.call("POST", "/api/reports", {"kind": "month", "period_start": TODAY.replace(day=1).isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    assert rep["through"] == TODAY.isoformat()
    assert rep["period_end"] == period_bounds("month", TODAY)[1].isoformat()


def test_rejects_bad_periods(api):
    setup(api)
    tue = THIS_MON + timedelta(days=1)
    assert api.call("POST", "/api/reports", {"kind": "week", "period_start": tue.isoformat(),
                                             "today": TODAY.isoformat()})[0] == 422
    second = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=2)   # un día 2 del mes pasado
    assert api.call("POST", "/api/reports", {"kind": "month", "period_start": second.isoformat(),
                                             "today": TODAY.isoformat()})[0] == 422
    future = THIS_MON + timedelta(days=7)
    assert api.call("POST", "/api/reports", {"kind": "week", "period_start": future.isoformat(),
                                             "today": TODAY.isoformat()})[0] == 422
    assert api.call("POST", "/api/reports", {"kind": "year", "period_start": THIS_MON.isoformat()})[0] == 422


def test_isolation(api):
    project, task = setup(api)
    post(api, project, task, MON, 9, 60)
    _, rep = api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    other = api.as_user("otro-reportes@test.com")
    assert other.call("GET", f"/api/reports/{rep['id']}")[0] == 404
    assert other.call("GET", "/api/reports", expect=200)[1]["reports"] == []
    # Generar el mismo periodo no toca el reporte ajeno
    _, own = other.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                                 "today": TODAY.isoformat()}, expect=200)
    assert own["id"] != rep["id"] and own["total_seconds"] == 0
    assert api.call("GET", f"/api/reports/{rep['id']}", expect=200)[1]["total_seconds"] == 3600


def test_due_reports_for_the_timer(api):
    project, task = setup(api, "timer@test.com")
    setup(api, "sin-actividad@test.com")
    api.login("timer@test.com")
    post(api, project, task, MON, 9, 60)        # la semana pasada
    # Un reporte a medio periodo (hecho con el botón el martes) se rehace completo
    with Session(engine) as session:
        user = user_row(session, "timer@test.com")
        from backend.reports import generate_report
        partial = generate_report(session, user, "week", MON, TUE)
        assert partial.through == TUE

        made = generate_due_reports(session, user, TODAY)
        weeks = [r for r in made if r.kind == "week"]
        assert [r.period_start for r in weeks] == [MON] and weeks[0].id == partial.id
        assert weeks[0].through == SUN and weeks[0].trigger == "auto"
        # Correrlo otra vez no hace nada
        assert generate_due_reports(session, user, TODAY) == []
        # Sin tiempo registrado, no hay reporte
        idle = user_row(session, "sin-actividad@test.com")
        assert generate_due_reports(session, idle, TODAY) == []
        assert session.exec(select(Report).where(Report.user_id == idle.id)).all() == []


def test_text_rules():
    assert hours(0) == "0 min" and hours(3 * 3600 + 300) == "3 h 05 min" and hours(7200) == "2 h"
    assert clock(9.5) == "09:30" and clock(24.5) == "00:30"
    empty = build_text("week", {"total_seconds": 0, "previous": {}})
    assert empty["summary"] == "No hubo tiempo registrado en la semana." and empty["recommendations"] == []
