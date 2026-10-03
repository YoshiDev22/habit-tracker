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


def stopwatch_body(task, minutes=30, key="1727712345678-abcd1234"):
    """Lo que manda buildPayload() de pomodoro.js al detener un cronómetro."""
    start = utc_now() - timedelta(minutes=minutes)
    return {"project_id": task["project_id"], "task_id": task["id"], "session_date": date.today().isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + timedelta(minutes=minutes)).isoformat(),
            "duration_seconds": minutes * 60, "planned_seconds": 0, "mode": "focus",
            "source": "stopwatch", "was_completed": True, "idempotency_key": key}


def test_resending_a_session_does_not_duplicate_it(seeded):
    # Backlog 22: el navegador muere justo después de enviar, o la cola reintenta
    # un POST cuya respuesta se perdió. La misma clave es la misma sesión.
    api = seeded["api"]
    task = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    body = stopwatch_body(task)
    _, first = api.call("POST", "/api/pomodoro", body, expect=201)
    _, again = api.call("POST", "/api/pomodoro", body, expect=200)
    assert again["id"] == first["id"]
    _, listed = api.call("GET", f"/api/pomodoro?task_id={task['id']}", expect=200)
    assert [s["id"] for s in listed["sessions"]] == [first["id"]]

    # El reintento no falla aunque la tarea se haya borrado entretanto
    api.call("DELETE", f"/api/tasks/{task['id']}", expect=204)
    _, late = api.call("POST", "/api/pomodoro", body, expect=200)
    assert late["id"] == first["id"] and late["task_id"] is None

    # Otra clave es otra sesión, y sin clave (registro a mano) no se deduplica
    other_task = seeded["tasks"]["Corrección de Pomodoros"]
    api.call("POST", "/api/pomodoro", stopwatch_body(other_task, key="otra"), expect=201)
    no_key = stopwatch_body(other_task, key=None)
    api.call("POST", "/api/pomodoro", no_key, expect=201)
    api.call("POST", "/api/pomodoro", {**no_key, "idempotency_key": "  "}, expect=201)
    _, listed = api.call("GET", f"/api/pomodoro?task_id={other_task['id']}", expect=200)
    assert len(listed["sessions"]) == 4   # la del fixture + estas tres


def test_two_simultaneous_resends_keep_one_session(seeded, monkeypatch):
    # Los dos envíos pasan la búsqueda previa a la vez; el índice único frena al
    # segundo y el endpoint le devuelve la sesión del primero.
    import backend.routers.pomodoro as pomodoro_router

    api = seeded["api"]
    task = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    body = stopwatch_body(task, key="carrera")
    _, first = api.call("POST", "/api/pomodoro", body, expect=201)

    real_lookup = pomodoro_router._session_by_key
    calls = []

    def racing_lookup(*args):
        calls.append(args)
        return None if len(calls) == 1 else real_lookup(*args)

    monkeypatch.setattr(pomodoro_router, "_session_by_key", racing_lookup)
    _, again = api.call("POST", "/api/pomodoro", body, expect=200)
    assert again["id"] == first["id"] and len(calls) == 2
    _, listed = api.call("GET", f"/api/pomodoro?task_id={task['id']}", expect=200)
    assert len(listed["sessions"]) == 1


def test_sessions_to_review(seeded):
    api, p = seeded["api"], seeded["project"]
    task = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    start = utc_now() - timedelta(hours=9)
    body = {"project_id": p["id"], "task_id": task["id"], "session_date": date.today().isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + timedelta(hours=8)).isoformat(),
            "duration_seconds": 8 * H, "planned_seconds": 0, "mode": "focus", "was_completed": True,
            "source": "stopwatch", "note": "Cerrado automáticamente a las 8 h", "needs_review": True}
    _, s1 = api.call("POST", "/api/pomodoro", body, expect=201)
    _, s2 = api.call("POST", "/api/pomodoro", {**body, "started_at": (start - timedelta(days=1)).isoformat(),
                                               "ended_at": (start - timedelta(days=1) + timedelta(hours=8)).isoformat()}, expect=201)
    assert s1["needs_review"] is True
    _, rv = api.call("GET", "/api/pomodoro/review", expect=200)
    assert [s["id"] for s in rv["sessions"]] == [s1["id"], s2["id"]], "newest first"
    # Cuenta en los totales igual que cualquier otra
    _, summ = api.call("GET", "/api/projects/summary", expect=200)
    assert next(x for x in summ["summaries"] if x["project_id"] == p["id"])["total_seconds"] == 417 * 60 + 16 * H

    # Corregir las horas la confirma; "Está bien" también, sin tocar nada más
    _, fixed = api.call("PATCH", f"/api/pomodoro/{s1['id']}", {"duration_seconds": 3 * H,
                        "ended_at": (start + timedelta(hours=3)).isoformat()}, expect=200)
    assert fixed["needs_review"] is False
    _, ok = api.call("PATCH", f"/api/pomodoro/{s2['id']}", {"needs_review": False}, expect=200)
    assert ok["needs_review"] is False and ok["duration_seconds"] == 8 * H
    assert api.call("GET", "/api/pomodoro/review", expect=200)[1]["total"] == 0
    # Cambiar solo la nota o la tarea no la confirma
    _, s3 = api.call("POST", "/api/pomodoro", {**body, "started_at": (start - timedelta(days=2)).isoformat(),
                                               "ended_at": (start - timedelta(days=2) + timedelta(hours=8)).isoformat()}, expect=201)
    _, still = api.call("PATCH", f"/api/pomodoro/{s3['id']}", {"note": "revisar"}, expect=200)
    assert still["needs_review"] is True

    # La de otro usuario no aparece en su campanita ni se confirma desde fuera
    other = seeded["other"]
    assert other.call("GET", "/api/pomodoro/review", expect=200)[1]["total"] == 0
    assert other.call("PATCH", f"/api/pomodoro/{s3['id']}", {"needs_review": False})[0] == 404
