"""Proyectos como etiqueta de la tarea: "Sin asignar", y el tiempo que sigue a la tarea."""
from datetime import date, timedelta

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


def test_project_overview(seeded):
    api, p = seeded["api"], seeded["project"]
    tasks = seeded["tasks"]
    # Etiquetas: una tarea con dos, otra con una, y tiempo sin tarea
    _, doc = api.call("POST", "/api/tags", {"name": "doc"}, expect=201)
    _, back = api.call("POST", "/api/tags", {"name": "backend"}, expect=201)
    big = tasks["Corrección de Pomodoros"]
    api.call("PATCH", f"/api/tasks/{big['id']}", {"tag_ids": [doc["id"], back["id"]]}, expect=200)
    small = tasks["Confirmación de cambios datos y cancelación pomodoro"]
    api.call("PATCH", f"/api/tasks/{small['id']}", {"tag_ids": [doc["id"]]}, expect=200)
    last_month = date.today().replace(day=1) - timedelta(days=1)
    log_time(api, p["id"], None, 30 * 60, day=last_month)
    # Un descanso no cuenta, igual que en /summary
    log_time(api, p["id"], big["id"], 5 * 60, mode="short_break")

    _, ov = api.call("GET", f"/api/projects/{p['id']}/overview", expect=200)
    _, summ = api.call("GET", "/api/projects/summary", expect=200)
    ht = next(x for x in summ["summaries"] if x["project_id"] == p["id"])
    assert ov["total_seconds"] == ht["total_seconds"] == 417 * 60 + 30 * 60, "same total as the List"
    assert ov["session_count"] == ht["session_count"]
    assert (ov["task_done"], ov["task_total"]) == (4, 5)
    assert ov["project"]["name"] == "Habit Tracker"

    assert [t["title"] for t in ov["tasks"]][:2] == ["Corrección de Pomodoros", "modificación de tiempo de pomodoros"]
    assert ov["tasks"][0]["seconds"] == 4 * H and ov["tasks"][-1]["seconds"] == 0, "most time first, all tasks listed"
    assert ov["seconds_no_task"] == 30 * 60
    assert sum(t["seconds"] for t in ov["tasks"]) + ov["seconds_no_task"] == ov["total_seconds"]

    by_tag = {t["name"]: t["seconds"] for t in ov["tags"]}
    assert by_tag == {"doc": 4 * H + 25 * 60, "backend": 4 * H}, "a session counts in each tag of its task"
    assert ov["untagged_seconds"] == (35 + 117 + 30) * 60

    months = {m["month"]: m["seconds"] for m in ov["months"]}
    assert months == {last_month.strftime("%Y-%m"): 30 * 60, date.today().strftime("%Y-%m"): 417 * 60}
    assert [m["month"] for m in ov["months"]] == sorted(months), "oldest month first"
    assert (ov["first_date"], ov["last_date"]) == (last_month.isoformat(), date.today().isoformat())


def test_project_overview_archived_and_empty(seeded):
    api = seeded["api"]
    _, ov = api.call("GET", f"/api/projects/{seeded['archived']['id']}/overview", expect=200)
    assert ov["total_seconds"] == 0 and ov["tasks"] == [] and ov["months"] == []
    assert ov["first_date"] is None and ov["project"]["is_active"] is False
    assert api.call("GET", "/api/projects/999999/overview")[0] == 404
