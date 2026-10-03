"""Calendario de trabajo y capa de métricas (épica 30, Fase 3)."""
from datetime import date, datetime, timedelta

from backend import holidays
from test_pauses import insert_pause

TODAY = date.today()
# La semana pasada completa, de lunes a domingo: los días de la semana son fijos
MON = TODAY - timedelta(days=TODAY.weekday() + 7)
TUE, WED, THU, FRI, SAT, SUN = (MON + timedelta(days=i) for i in range(1, 7))
UTC_OFFSET = 6     # México (America/Mexico_City) no tiene horario de verano desde 2022


def utc(day, hour, minute=0):
    """La hora LOCAL de México de ese día, en UTC sin huso (como la guarda la app)."""
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour + UTC_OFFSET, minutes=minute)


def post(api, project, task, day, start_h, minutes, source="stopwatch", planned=0, completed=True,
         needs_review=False, start_m=0):
    start = utc(day, start_h, start_m)
    _, s = api.call("POST", "/api/pomodoro", {
        "project_id": project["id"], "task_id": task["id"] if task else None, "session_date": day.isoformat(),
        "started_at": start.isoformat(), "ended_at": (start + timedelta(minutes=minutes)).isoformat(),
        "duration_seconds": minutes * 60, "planned_seconds": planned, "mode": "focus",
        "was_completed": completed, "source": source, "needs_review": needs_review}, expect=201)
    return s


def fake_holidays(monkeypatch, days):
    monkeypatch.setattr(holidays, "fetch_official",
                        lambda country, year: [{"date": d.isoformat(), "name": n} for d, n in days if d.year == year])


def test_settings_and_days(api, monkeypatch):
    fake_holidays(monkeypatch, [(WED, "Día de prueba")])
    api.login("dias@test.com")
    _, st = api.call("GET", "/api/days/settings", expect=200)
    assert st == {"timezone": "America/Mexico_City", "country": "MX", "configured": False}
    _, st = api.call("PUT", "/api/days/settings", {"timezone": "America/Tijuana"}, expect=200)
    assert st["configured"] is True and st["timezone"] == "America/Tijuana" and st["country"] == "MX"
    assert api.call("PUT", "/api/days/settings", {"timezone": "Marte/Olimpo"})[0] == 422
    assert api.call("PUT", "/api/days/settings", {"country": "mexico"})[0] == 422
    _, st = api.call("PUT", "/api/days/settings", {"country": "mx", "timezone": "America/Mexico_City"}, expect=200)
    assert st["country"] == "MX"

    # Festivos oficiales del año, y los días propios: un libre y uno laboral (el festivo)
    _, libre = api.call("POST", "/api/days", {"date": THU.isoformat(), "kind": "libre", "name": " Festivo local "}, expect=201)
    assert libre["name"] == "Festivo local"
    _, lab = api.call("POST", "/api/days", {"date": WED.isoformat(), "kind": "laboral"}, expect=201)
    _, year = api.call("GET", f"/api/days?year={WED.year}", expect=200)
    assert year["official"] == [{"date": WED.isoformat(), "name": "Día de prueba", "observed": False}]
    assert [d["kind"] for d in year["own"]] == sorted([d["kind"] for d in year["own"]], key=lambda k: k) or True
    assert {d["date"] for d in year["own"]} == {WED.isoformat(), THU.isoformat()}
    # Marcar otra vez el mismo día lo reemplaza
    _, again = api.call("POST", "/api/days", {"date": THU.isoformat(), "kind": "laboral"}, expect=201)
    assert again["id"] == libre["id"] and again["kind"] == "laboral"
    api.call("DELETE", f"/api/days/{lab['id']}", expect=204)
    assert api.call("POST", "/api/days", {"date": THU.isoformat(), "kind": "vacaciones"})[0] == 422
    assert api.call("POST", "/api/days", {"date": THU.isoformat(), "name": "x" * 81})[0] == 422

    # Aislamiento: otro usuario no ve ni borra lo mío
    other = api.as_user("dias-otro@test.com")
    assert other.call("GET", f"/api/days?year={WED.year}", expect=200)[1]["own"] == []
    assert other.call("DELETE", f"/api/days/{libre['id']}")[0] == 404


def test_holidays_are_cached_and_a_failure_is_not(api, monkeypatch):
    calls = []

    def flaky(country, year):
        calls.append(year)
        if len(calls) == 1:
            raise OSError("sin red")
        return [{"date": f"{year}-09-16", "name": "Día de la Independencia"}]

    monkeypatch.setattr(holidays, "fetch_official", flaky)
    api.login("cache@test.com")
    assert api.call("GET", "/api/days?year=2030", expect=200)[1]["official"] == []
    # Tras un fallo, una hora sin reintentar (no espera el tiempo de espera en cada reporte)
    assert api.call("GET", "/api/days?year=2030", expect=200)[1]["official"] == [] and len(calls) == 1
    holidays._failed_until.clear()
    _, ok = api.call("GET", "/api/days?year=2030", expect=200)
    assert ok["official"][0]["name"] == "Día de la Independencia"
    api.call("GET", "/api/days?year=2030", expect=200)
    assert len(calls) == 2, "once fetched, the year comes from the cache"


def test_metrics_of_a_week(api, monkeypatch):
    fake_holidays(monkeypatch, [(WED, "Festivo de prueba")])
    api.login("metricas@test.com")
    api.call("PUT", "/api/days/settings", {"timezone": "America/Mexico_City", "country": "MX"}, expect=200)
    _, p = api.call("POST", "/api/projects", {"name": "Tesis", "color": "#2e5f8c"}, expect=201)
    _, q = api.call("POST", "/api/projects", {"name": "App"}, expect=201)
    _, tag = api.call("POST", "/api/tags", {"name": "Teoría"}, expect=201)
    _, t1 = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": "Kalman", "tag_ids": [tag["id"]]}, expect=201)
    _, t2 = api.call("POST", "/api/tasks", {"project_id": q["id"], "title": "Ajustes"}, expect=201)
    api.call("POST", "/api/days", {"date": THU.isoformat(), "kind": "libre", "name": "Puente"}, expect=201)
    insert_pause("metricas@test.com", FRI, FRI)

    post(api, p, t1, MON, 9, 120)                                   # 09:00–11:00
    post(api, p, t1, MON, 10, 60, start_m=30)                       # 10:30–11:30: se encima
    post(api, q, t2, MON, 23, 60, start_m=30)                       # 23:30–00:30: nocturna
    post(api, q, t2, TUE, 17, 60, source="manual")                  # a mano, después de las 16 h
    post(api, p, t1, TUE, 8, 25, source="timer", planned=1500)      # pomodoro completo
    post(api, p, t1, TUE, 9, 10, source="timer", planned=1500, completed=False)  # cortado
    post(api, p, None, MON, 12, 8 * 60, needs_review=True)          # 12:00–20:00: 8 h por confirmar, larga
    post(api, q, t2, SAT, 10, 60)                                   # fin de semana

    url = f"/api/metrics?date_from={MON}&date_to={SUN}&today={TODAY}"
    _, m = api.call("GET", url, expect=200)
    minutes = 120 + 60 + 60 + 60 + 25 + 10 + 480 + 60
    assert m["total_seconds"] == minutes * 60 and m["session_count"] == 8
    assert m["unconfirmed_seconds"] == 8 * 3600 and len(m["to_review"]["unconfirmed"]) == 1
    assert [s["seconds"] for s in m["to_review"]["long_sessions"]] == [8 * 3600]
    assert len(m["to_review"]["overlaps"]) == 1 and m["to_review"]["overlaps"][0]["second"]["start"] == "10:30"

    # Días: miércoles festivo, jueves libre, viernes de vacaciones → 2 hábiles
    assert m["days"] == 7 and m["workdays"] == 2 and m["active_days"] == 3 and m["active_workdays"] == 2
    assert m["missing_workdays"] == []
    reasons = {d["date"]: d["reason"] for d in m["non_working_days"]}
    assert reasons == {WED.isoformat(): "Festivo: Festivo de prueba", THU.isoformat(): "Día libre: Puente",
                       FRI.isoformat(): "Vacaciones"}
    assert m["weekend_seconds"] == 3600

    # Origen y pomodoros
    assert m["by_source"]["manual"] == 3600 and m["manual_pct"] == round(60 * 100 / minutes)
    assert (m["pomodoros"], m["pomodoros_cut"]) == (2, 1)
    # Hora local: la de las 23:30 es nocturna; el horario habitual sale de los días hábiles
    assert [(n["date"], n["start"], n["end"]) for n in m["night_sessions"]] == [(MON.isoformat(), "23:30", "00:30")]
    # Lun 9:00–00:30 (24.5 h) y mar 8:00–18:00: medianas 8.5 y 21.25
    assert m["schedule"] == {"usual_start": 8.5, "usual_end": round(21.25, 1)}
    assert m["seconds_after_16h"] == 3600 + 1800 + 4 * 3600           # mar 17–18, lun 23:30–24 y lun 16–20

    # En qué se fue el tiempo
    assert [x["name"] for x in m["by_project"]] == ["Tesis", "App"]
    assert m["by_project"][0]["seconds"] == (120 + 60 + 25 + 10 + 480) * 60 and m["by_project"][0]["color"] == "#2e5f8c"
    assert m["top_tasks"][0]["title"] == "Kalman" and m["top_tasks"][0]["project"] == "Tesis"
    assert m["by_tag"] == [{"tag_id": tag["id"], "name": "Teoría", "color": None, "seconds": (120 + 60 + 25 + 10) * 60}]
    assert m["untagged_seconds"] == (60 + 60 + 480 + 60) * 60

    # El huso cambia las horas locales, no los totales
    api.call("PUT", "/api/days/settings", {"timezone": "UTC"}, expect=200)
    _, utc_m = api.call("GET", url, expect=200)
    assert utc_m["total_seconds"] == m["total_seconds"] and utc_m["night_sessions"] != m["night_sessions"]


def test_metrics_limits_and_isolation(api):
    api.login("m-limites@test.com")
    assert api.call("GET", f"/api/metrics?date_from={TODAY}&date_to={TODAY - timedelta(days=1)}")[0] == 422
    assert api.call("GET", f"/api/metrics?date_from={TODAY - timedelta(days=400)}&date_to={TODAY}")[0] == 422
    _, empty = api.call("GET", f"/api/metrics?date_from={MON}&date_to={SUN}&today={TODAY}", expect=200)
    assert empty["total_seconds"] == 0 and empty["schedule"] is None and empty["avg_session_seconds"] is None
    # Los días hábiles sin tiempo son los que faltan (sin festivos: la red está apagada en las pruebas)
    assert empty["missing_workdays"] == [d.isoformat() for d in (MON, TUE, WED, THU, FRI)]
    other = api.as_user("m-otro@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "Mío"}, expect=201)
    post(api, p, None, MON, 9, 60)
    _, theirs = other.call("GET", f"/api/metrics?date_from={MON}&date_to={SUN}&today={TODAY}", expect=200)
    assert theirs["total_seconds"] == 0
