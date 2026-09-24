"""Registros de tiempo: el proyecto sigue a la tarea, filtros y el "Hoy"."""
from datetime import date, timedelta

from conftest import H, log_time, utc_now


def test_the_task_decides_the_project(seeded):
    api = seeded["api"]
    ht = seeded["project"]
    _, t = api.call("POST", "/api/tasks", {"title": "suelta"}, expect=201)   # en Sin asignar
    # Un project_id equivocado del cliente se cambia por el de la tarea
    s = log_time(api, ht["id"], t["id"], 40 * 60)
    assert s["project_id"] == t["project_id"] != ht["id"]
    # Pasar el registro a una tarea de otro proyecto lo pasa a ese proyecto
    kanban = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    _, s2 = api.call("PATCH", f"/api/pomodoro/{s['id']}", {"task_id": kanban["id"]}, expect=200)
    assert s2["task_id"] == kanban["id"] and s2["project_id"] == ht["id"]


def test_filter_sessions_by_task_and_date(seeded):
    api = seeded["api"]
    kanban = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    yesterday = date.today() - timedelta(days=1)
    log_time(api, seeded["project"]["id"], kanban["id"], 30 * 60, day=yesterday)
    _, ss = api.call("GET", f"/api/pomodoro?task_id={kanban['id']}", expect=200)
    assert [s["duration_seconds"] for s in ss["sessions"]] == [30 * 60]
    _, ss = api.call("GET", f"/api/pomodoro?date_from={yesterday}&date_to={yesterday}", expect=200)
    assert [s["task_id"] for s in ss["sessions"]] == [kanban["id"]]


def test_today_uses_the_client_date(seeded):
    api = seeded["api"]
    _, st = api.call("GET", f"/api/pomodoro/stats?today={date.today()}", expect=200)
    assert st["today_seconds"] == 417 * 60
    _, st = api.call("GET", f"/api/pomodoro/stats?today={date.today() + timedelta(days=1)}", expect=200)
    assert st["today_seconds"] == 0
    # Una fecha a más de un día de la de UTC no es un huso horario: se rechaza
    assert api.call("GET", "/api/pomodoro/stats?today=2001-01-01")[0] == 422


def test_edit_and_delete_a_session(seeded):
    api = seeded["api"]
    s = log_time(api, seeded["project"]["id"], None, H)
    start = utc_now() - timedelta(hours=3)
    _, r = api.call("PATCH", f"/api/pomodoro/{s['id']}", {
        "started_at": start.isoformat(), "ended_at": (start + timedelta(minutes=90)).isoformat(),
        "duration_seconds": 90 * 60, "note": "corregido"}, expect=200)
    assert r["duration_seconds"] == 90 * 60 and r["note"] == "corregido"
    assert api.call("PATCH", f"/api/pomodoro/{s['id']}", {"duration_seconds": 0})[0] == 400
    assert api.call("PATCH", f"/api/pomodoro/{s['id']}", {"ended_at": start.isoformat()})[0] == 400
    api.call("DELETE", f"/api/pomodoro/{s['id']}", expect=204)
    assert api.call("DELETE", f"/api/pomodoro/{s['id']}")[0] == 404


def test_completed_range_filter(seeded):
    api = seeded["api"]
    today = date.today()
    _, t = api.call("POST", "/api/tasks", {"title": "de ayer"}, expect=201)
    api.call("PATCH", f"/api/tasks/{t['id']}?today={today - timedelta(days=1)}", {"is_done": True}, expect=200)
    _, done_today = api.call("GET", f"/api/tasks?completed_from={today}&completed_to={today}", expect=200)
    assert len(done_today["tasks"]) == 4
    y = today - timedelta(days=1)
    _, done_yesterday = api.call("GET", f"/api/tasks?completed_from={y}&completed_to={y}", expect=200)
    assert [x["title"] for x in done_yesterday["tasks"]] == ["de ayer"]
    # Desmarcar la saca del filtro
    api.call("PATCH", f"/api/tasks/{t['id']}", {"is_done": False}, expect=200)
    assert api.call("GET", f"/api/tasks?completed_from={y}&completed_to={y}", expect=200)[1]["total"] == 0


def test_task_seconds_are_focus_only(seeded):
    api = seeded["api"]
    kanban = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    log_time(api, seeded["project"]["id"], kanban["id"], 20 * 60)
    log_time(api, seeded["project"]["id"], kanban["id"], 5 * 60, mode="short_break")
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(t for t in tl["tasks"] if t["id"] == kanban["id"])["seconds"] == 20 * 60
