"""Checklist y comentarios del detalle de tarjeta."""
from datetime import datetime, timezone


def test_checklist(seeded):
    api = seeded["api"]
    tid = seeded["tasks"]["Revisión de idea para cambiar a kanban"]["id"]
    _, a = api.call("POST", f"/api/tasks/{tid}/checklist", {"text": "3.1 Intro"}, expect=201)
    _, b = api.call("POST", f"/api/tasks/{tid}/checklist", {"text": "  3.2 Funciones  "}, expect=201)
    _, c = api.call("POST", f"/api/tasks/{tid}/checklist", {"text": "3.3 Decoradores"}, expect=201)
    assert (a["order"], b["order"], c["order"]) == (0, 1, 2) and b["text"] == "3.2 Funciones"
    api.call("PATCH", f"/api/tasks/{tid}/checklist/{a['id']}", {"is_done": True}, expect=200)
    api.call("PATCH", f"/api/tasks/{tid}/checklist/{b['id']}", {"is_done": True}, expect=200)
    # Editar el texto no cambia si estaba marcado
    _, r = api.call("PATCH", f"/api/tasks/{tid}/checklist/{a['id']}", {"text": "3.1 Introducción"}, expect=200)
    assert r["text"] == "3.1 Introducción" and r["is_done"] is True
    _, r = api.call("PATCH", f"/api/tasks/{tid}/checklist/{c['id']}", {"text": "3.3 Decoradores y closures", "order": 0}, expect=200)
    assert not r["is_done"]
    _, cl = api.call("GET", f"/api/tasks/{tid}/checklist", expect=200)
    assert [i["id"] for i in cl["items"]] == [a["id"], c["id"], b["id"]]
    assert api.call("POST", f"/api/tasks/{tid}/checklist", {"text": "   "})[0] == 422
    assert api.call("POST", f"/api/tasks/{tid}/checklist", {"text": "x" * 201})[0] == 422

    _, tl = api.call("GET", "/api/tasks", expect=200)
    t = next(x for x in tl["tasks"] if x["id"] == tid)
    assert (t["checklist_total"], t["checklist_done"]) == (3, 2)


def test_comments(seeded):
    api = seeded["api"]
    tid = seeded["tasks"]["Revisión de idea para cambiar a kanban"]["id"]
    _, c1 = api.call("POST", f"/api/tasks/{tid}/comments", {"body": "Empecé el capítulo"}, expect=201)
    _, c2 = api.call("POST", f"/api/tasks/{tid}/comments", {"body": "Me atoré en decoradores"}, expect=201)
    assert c1["author_name"] == "Yoshio"
    age = datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(c1["created_at"])
    assert abs(age.total_seconds()) < 60, "created_at is UTC now"
    _, r = api.call("PATCH", f"/api/tasks/{tid}/comments/{c1['id']}", {"body": "Empecé el capítulo 3"}, expect=200)
    assert r["edited_at"] and r["created_at"] == c1["created_at"]
    _, cm = api.call("GET", f"/api/tasks/{tid}/comments", expect=200)
    assert [x["id"] for x in cm["comments"]] == [c1["id"], c2["id"]]
    assert api.call("POST", f"/api/tasks/{tid}/comments", {"body": ""})[0] == 422

    _, r = api.call("PATCH", f"/api/tasks/{tid}", {"title": "otro título"}, expect=200)
    assert r["comment_count"] == 2
    api.call("DELETE", f"/api/tasks/{tid}/comments/{c2['id']}", expect=204)
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(x for x in tl["tasks"] if x["id"] == tid)["comment_count"] == 1


def test_deleting_a_task_or_project_takes_its_details(seeded):
    api = seeded["api"]
    _, p = api.call("POST", "/api/projects", {"name": "Temporal"}, expect=201)
    _, t = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": "x"}, expect=201)
    api.call("POST", f"/api/tasks/{t['id']}/checklist", {"text": "a"}, expect=201)
    api.call("POST", f"/api/tasks/{t['id']}/comments", {"body": "b"}, expect=201)
    api.call("DELETE", f"/api/projects/{p['id']}", expect=204)
    api.call("DELETE", f"/api/tasks/{t['id']}", expect=204)
    assert api.call("GET", f"/api/tasks/{t['id']}/checklist")[0] == 404
