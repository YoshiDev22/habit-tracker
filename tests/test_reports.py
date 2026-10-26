"""Reportes guardados (épica 30, Fase 4): periodos, generación, texto y el timer."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import Report, User
from backend.report_text import build_text, clock_hour, hours, is_vague
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
    text = rep["text"]
    assert text["summary"].startswith("Registraste 3.5 h en 2 días hábiles")
    assert "más que la semana pasada (1.0 h)" in text["summary"]
    assert text["data_cleanup"].startswith("Limpieza de datos: no hay")
    assert text["closing"]["well_done"] and text["closing"]["tip"]
    assert text["comparison"] == ""          # solo en un mes
    m = rep["metrics"]
    # El estado de cada día, y lo que el reporte compara del periodo anterior
    assert [d["status"] for d in m["days_detail"]][:2] == ["worked", "worked"]
    assert m["days_detail"][5]["status"] == "off" and m["days_detail"][5]["reason"] == "fin de semana"
    assert m["previous"]["by_project"][0]["pct"] == 100 and len(m["previous"]["by_day"]) == 7
    assert m["top_tasks"][0]["sessions"] == 2 and m["top_tasks"][0]["days"] == 2
    assert m["top_project_tags"]["project"] == "Tesis" and m["projected_seconds"] is None

    # Regenerar reemplaza: mismo id, cifras nuevas
    post(api, project, task, WED, 9, 30)
    _, again = api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                                 "today": TODAY.isoformat()}, expect=200)
    assert again["id"] == rep["id"] and again["total_seconds"] == 240 * 60
    _, lst = api.call("GET", "/api/reports", expect=200)
    assert [r["id"] for r in lst["reports"]] == [rep["id"]]
    assert "metrics" not in lst["reports"][0]
    _, one = api.call("GET", f"/api/reports/{rep['id']}", expect=200)
    assert one["total_seconds"] == 240 * 60 and one["text"]["observations"] and one["text"]["patterns"]


def test_current_period_goes_until_today(api):
    project, task = setup(api)
    post(api, project, task, TODAY, 9, 45)
    _, rep = api.call("POST", "/api/reports", {"kind": "month", "period_start": TODAY.replace(day=1).isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    assert rep["through"] == TODAY.isoformat()
    assert rep["period_end"] == period_bounds("month", TODAY)[1].isoformat()
    m = rep["metrics"]
    # Las semanas del mes, recortadas a él; los días que faltan, pendientes
    assert m["by_week"][0]["start"] == TODAY.replace(day=1).isoformat()
    assert sum(w["seconds"] for w in m["by_week"]) == 45 * 60
    statuses = {d["date"]: d["status"] for d in m["days_detail"]}
    tomorrow = TODAY + timedelta(days=1)
    if tomorrow.month == TODAY.month:
        assert statuses[tomorrow.isoformat()] == "pending"
    assert "Llevas 0.8 h" in rep["text"]["summary"] or TODAY.weekday() >= 5


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
    assert hours(0) == "0 h" and hours(3 * 3600 + 300) == "3.1 h" and hours(3600) == "1.0 h"
    assert clock_hour(9.0) == "9" and clock_hour(9.5) == "9:30" and clock_hour(24.5) == "0:30"
    assert is_vague("Ajustes Habits") and is_vague("Tarea 08/09/26") and not is_vague("Deducción fórmula Fourier")
    empty = build_text("week", {"total_seconds": 0, "previous": {}})
    assert empty["summary"] == "No registraste tiempo en la semana." and empty["next_steps"] == []


def test_projection_and_comparison(api):
    project, task = setup(api, "proyeccion@test.com")
    with Session(engine) as session:
        from backend.reports import projection
        days = [{"date": f"2026-10-0{i}", "seconds": s, "status": st, "workday": True}
                for i, (s, st) in enumerate([(3600, "worked"), (7200, "worked"), (5400, "worked"),
                                             (0, "pending"), (0, "pending")], start=1)]
        # 4.5 h en tres días hábiles: 1.5 h por día, y faltan dos
        assert projection(days, 16200) == 16200 + 5400 * 2
        assert projection(days[:3], 16200) is None             # ya no falta nada
        assert projection(days[1:], 12600) is None             # solo dos días: aún no hay base
    # Un mes con un mes anterior: la comparativa dice cuánto cambió
    month_start = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    before = (month_start - timedelta(days=1)).replace(day=10)
    post(api, project, task, month_start.replace(day=10), 9, 120)
    post(api, project, task, before, 9, 60)
    _, rep = api.call("POST", "/api/reports", {"kind": "month", "period_start": month_start.isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    # Por día de trabajo: cada mes con sus hábiles más los días con tiempo que no lo eran
    m = rep["metrics"]
    n = m["workdays"] + m["active_days"] - m["active_workdays"]
    prev_n = m["previous"]["workdays"] + m["previous"]["active_days"] - m["previous"]["active_workdays"]
    avg, prev_avg = round(7200 / n), round(3600 / prev_n)
    change = (avg - prev_avg) / prev_avg
    assert rep["text"]["comparison"] == (
        f"Frente al mes anterior (1.0 h en {prev_n} días de trabajo): registraste 2.0 h en {n} días de trabajo. "
        f"Por día de trabajo, {hours(avg)} frente a {hours(prev_avg)} ({round(abs(change) * 100)} % más).")


def test_month_comparison_uses_working_days():
    """Un mes en curso se compara por día de trabajo: con la mitad de los días,
    el mismo ritmo no sale como "menos" que el mes anterior completo. Un día de
    descanso con tiempo cuenta como de trabajo; uno sin tiempo, no."""
    from backend.report_text import _closing, _comparison
    days = ([{"date": f"2026-10-{i:02d}", "status": "worked", "workday": True} for i in range(1, 10)]
            + [{"date": "2026-10-11", "status": "today", "workday": True, "seconds": 0},
               {"date": "2026-10-12", "status": "off", "workday": False, "seconds": 3 * 3600},
               {"date": "2026-10-13", "status": "off", "workday": False, "seconds": 0}]
            + [{"date": f"2026-10-{i:02d}", "status": "pending", "workday": True} for i in range(12, 22)])
    m = {"date_from": "2026-10-01", "date_to": "2026-10-31", "through": "2026-10-11",
         "total_seconds": 10 * 3 * 3600, "workdays": 10, "active_workdays": 9, "night_sessions": [],
         "days_detail": days, "top_tasks": [], "unconfirmed_seconds": 0, "missing_workdays": [], "active_days": 10,
         "previous": {"total_seconds": 20 * 3 * 3600, "workdays": 19, "active_days": 19, "active_workdays": 18}}
    text = _comparison("month", m)
    assert text == ("Frente al mes anterior (60.0 h en 20 días de trabajo): llevas 30.0 h en 10 días de trabajo. "
                    "Por día de trabajo, casi lo mismo: 3.0 h frente a 3.0 h.")
    # Con más ritmo por día hábil, el cierre lo dice aunque el total aún sea menor
    m["total_seconds"] = 10 * 4 * 3600
    assert _closing("month", m)["well_done"] == "Subiste de 3.0 h a 4.0 h por día de trabajo."


def test_timer_script(api, capsys):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import generate_reports

    project, task = setup(api, "script@test.com")
    post(api, project, task, MON, 9, 60)
    uid = api.call("GET", "/api/auth/me", expect=200)[1]["id"]
    assert generate_reports.main(["--email", "script@test.com", "--today", TODAY.isoformat(), "--dry-run"]) == 0
    out = capsys.readouterr().out
    # Va al registro del servidor: el número de la cuenta, nunca su correo
    assert f"would generate account {uid}: week from {MON.isoformat()}" in out and "@" not in out
    assert api.call("GET", "/api/reports", expect=200)[1]["reports"] == []

    assert generate_reports.main(["--email", "script@test.com", "--today", TODAY.isoformat()]) == 0
    out = capsys.readouterr().out
    assert f"generated account {uid}: week from {MON.isoformat()}" in out and "@" not in out
    _, lst = api.call("GET", "/api/reports", expect=200)
    assert any(r["kind"] == "week" and r["period_start"] == MON.isoformat() and r["trigger"] == "auto"
               for r in lst["reports"])
    # La segunda vez no hay nada que hacer
    assert generate_reports.main(["--email", "script@test.com", "--today", TODAY.isoformat()]) == 0
    assert "0 report(s) generated." in capsys.readouterr().out
    assert generate_reports.main(["--email", "nadie@test.com"]) == 1


def test_habit_steps_anchor_a_weak_habit_to_the_most_constant_one():
    from backend.habit_report import _next_steps

    def habit(label, done, possible, icon=""):
        return {"label": label, "icon": icon, "days_done": done, "days_possible": possible,
                "pct": round(done * 100 / possible), "best_weekday": None, "weak_weekday": None}
    m = {"habits": [habit("Proyectos", 4, 5, "💻"), habit("Ejercicio", 0, 5, "💪"), habit("Dieta", 0, 5, "🥗")],
         "missed_days": []}
    steps = _next_steps("week", m)
    assert steps[:2] == ["💪 Ejercicio: hazlo justo después de 💻 Proyectos, que ya haces 4 de 5 días.",
                         "🥗 Dieta: hazlo justo después de 💻 Proyectos, que ya haces 4 de 5 días."]
    # Sin un hábito constante al cual atarlos, dos frases distintas (antes, la misma dos veces)
    m["habits"] = [habit("Ejercicio", 1, 5), habit("Dieta", 0, 5)]
    first, second = _next_steps("week", m)[:2]
    assert first.startswith("Dieta: átalo") and second.startswith("Ejercicio: hazlo a la misma hora")


def test_time_steps_are_never_empty_with_time_logged():
    from backend.report_text import _next_steps
    m = {"to_review": {"unconfirmed": 0, "long_sessions": [], "overlaps": [], "inconsistent": []},
         "missing_workdays": [], "top_tasks": [], "night_sessions": [], "pomodoros": 0, "pomodoros_cut": 0,
         "total_seconds": 7200, "untagged_seconds": 0,
         "by_project": [{"name": "Tesis", "seconds": 5400, "pct": 75}, {"name": "VPS", "seconds": 1800, "pct": 25}]}
    assert _next_steps("week", m) == ["Ponle una meta de horas a Tesis para la próxima semana (llevó 1.5 h "
                                      "esta semana) y revisa en el próximo reporte si la cumpliste."]
    # Con algo que corregir, eso va primero y no se agrega la meta
    m["missing_workdays"] = ["2026-10-13"]
    assert len(_next_steps("week", m)) == 1 and "anótalos a mano" in _next_steps("week", m)[0]
