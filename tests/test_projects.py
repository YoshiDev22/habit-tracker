"""Proyectos como etiqueta de la tarea: "Sin asignar", y el tiempo que sigue a la tarea."""
from conftest import H, log_time


def totals(api):
    _, s = api.call("GET", "/api/projects/summary", expect=200)
    return {x["name"]: x["total_seconds"] for x in s["summaries"]}


def sin_asignar(api):
    _, pl = api.call("GET", "/api/projects", expect=200)
    return next(p for p in pl["projects"] if p["is_system"])


def test_one_sin_asignar_per_user(seeded):
    api = seeded["api"]
    _, pl = api.call("GET", "/api/projects", expect=200)
    system = [p for p in pl["projects"] if p["is_system"]]
    assert len(system) == 1 and system[0]["name"] == "Sin asignar"
    _, again = api.call("GET", "/api/projects", expect=200)
    assert sum(p["is_system"] for p in again["projects"]) == 1


def test_task_without_project_goes_to_sin_asignar(seeded):
    api = seeded["api"]
    un = sin_asignar(api)
    _, t = api.call("POST", "/api/tasks", {"title": "suelta"}, expect=201)
    assert t["project_id"] == un["id"]
    _, r = api.call("PATCH", f"/api/tasks/{t['id']}", {"project_id": seeded["project"]["id"]}, expect=200)
    assert r["project_id"] == seeded["project"]["id"]
    _, r = api.call("PATCH", f"/api/tasks/{t['id']}", {"project_id": None}, expect=200)
    assert r["project_id"] == un["id"]


def test_sin_asignar_is_protected(seeded):
    api = seeded["api"]
    un = sin_asignar(api)
    assert api.call("PATCH", f"/api/projects/{un['id']}", {"name": "Otro"})[0] == 409
    assert api.call("PATCH", f"/api/projects/{un['id']}", {"is_active": False})[0] == 409
    assert api.call("DELETE", f"/api/projects/{un['id']}")[0] == 409
    _, r = api.call("PATCH", f"/api/projects/{un['id']}", {"color": "#000000", "name": "Sin asignar"}, expect=200)
    assert r["color"] == "#000000"
    assert api.call("POST", "/api/projects", {"name": "Sin asignar"})[0] == 409


def test_time_follows_the_task(seeded):
    api = seeded["api"]
    un = sin_asignar(api)
    ht = seeded["project"]
    _, t = api.call("POST", "/api/tasks", {"title": "sin proyecto"}, expect=201)
    log_time(api, un["id"], t["id"], 2 * H)
    before = totals(api)
    assert before["Sin asignar"] == 2 * H and before["Habit Tracker"] == 417 * 60
    api.call("PATCH", f"/api/tasks/{t['id']}", {"project_id": ht["id"]}, expect=200)
    after = totals(api)
    assert after["Sin asignar"] == 0 and after["Habit Tracker"] == 417 * 60 + 2 * H
    api.call("PATCH", f"/api/tasks/{t['id']}", {"project_id": None}, expect=200)
    assert totals(api)["Sin asignar"] == 2 * H


def test_deleting_a_project_keeps_its_tasks_and_time(seeded):
    api = seeded["api"]
    un = sin_asignar(api)
    _, p = api.call("POST", "/api/projects", {"name": "Curso"}, expect=201)
    _, c1 = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": "Cap 1"}, expect=201)
    api.call("POST", f"/api/tasks/{c1['id']}/comments", {"body": "nota"}, expect=201)
    log_time(api, p["id"], c1["id"], H)
    log_time(api, p["id"], None, 30 * 60)
    before = totals(api)["Sin asignar"]
    api.call("DELETE", f"/api/projects/{p['id']}", expect=204)
    _, tl = api.call("GET", "/api/tasks", expect=200)
    moved = next(x for x in tl["tasks"] if x["id"] == c1["id"])
    assert moved["project_id"] == un["id"] and moved["column_id"] == c1["column_id"] and moved["comment_count"] == 1
    assert totals(api)["Sin asignar"] == before + H + 30 * 60


def test_deleting_a_project_with_its_time(seeded):
    api = seeded["api"]
    un = sin_asignar(api)
    _, p = api.call("POST", "/api/projects", {"name": "Descartado"}, expect=201)
    _, d1 = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": "idea mala"}, expect=201)
    log_time(api, p["id"], d1["id"], H)
    before = totals(api)["Sin asignar"]
    api.call("DELETE", f"/api/projects/{p['id']}?delete_sessions=true", expect=204)
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(x for x in tl["tasks"] if x["id"] == d1["id"])["project_id"] == un["id"]
    assert totals(api)["Sin asignar"] == before
    _, ss = api.call("GET", "/api/pomodoro", expect=200)
    assert all(s["task_id"] != d1["id"] for s in ss["sessions"])
    api.call("DELETE", f"/api/tasks/{d1['id']}", expect=204)


def test_archived_project_tasks_keep_their_time(seeded):
    api = seeded["api"]
    task = seeded["tasks"]["Corrección de Pomodoros"]
    api.call("PATCH", f"/api/projects/{seeded['project']['id']}", {"is_active": False}, expect=200)
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(t for t in tl["tasks"] if t["id"] == task["id"])["seconds"] == 4 * H
