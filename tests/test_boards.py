"""Tableros, columnas y cómo is_done / column_id / completed_at van juntos."""
from datetime import date, timedelta

from conftest import client_today


def board_and_columns(api):
    _, bl = api.call("GET", "/api/boards", expect=200)
    board = bl["boards"][0]
    return board, {c["name"]: c for c in board["columns"]}


def test_new_task_goes_to_the_entry_column(seeded):
    api = seeded["api"]
    board, col = board_and_columns(api)
    assert board["name"] == "Mi tablero"
    assert [c["name"] for c in board["columns"]] == ["Por hacer", "Haciendo", "Hecho"]
    _, t = api.call("POST", "/api/tasks", {"project_id": seeded["project"]["id"], "title": "nueva"}, expect=201)
    assert t["board_id"] == board["id"] and t["column_id"] == col["Por hacer"]["id"]


def test_checkbox_and_columns_stay_in_sync(seeded):
    api = seeded["api"]
    _, col = board_and_columns(api)
    yesterday = (client_today() - timedelta(days=1)).isoformat()
    pending = seeded["tasks"]["Revisión de idea para cambiar a kanban"]
    done = seeded["tasks"]["Corrección de Pomodoros"]

    _, r = api.call("PATCH", f"/api/tasks/{pending['id']}?today={yesterday}", {"is_done": True}, expect=200)
    assert r["column_id"] == col["Hecho"]["id"] and r["completed_at"] == yesterday
    _, r = api.call("PATCH", f"/api/tasks/{pending['id']}", {"is_done": False}, expect=200)
    assert r["column_id"] == col["Por hacer"]["id"] and r["completed_at"] is None

    _, r = api.call("PATCH", f"/api/tasks/{done['id']}", {"column_id": col["Haciendo"]["id"]}, expect=200)
    assert r["is_done"] is False and r["completed_at"] is None
    _, r = api.call("PATCH", f"/api/tasks/{done['id']}?today={yesterday}", {"column_id": col["Hecho"]["id"]}, expect=200)
    assert r["is_done"] is True and r["completed_at"] == yesterday

    # Desmarcar dentro de Haciendo no la mueve
    api.call("PATCH", f"/api/tasks/{pending['id']}", {"column_id": col["Haciendo"]["id"]}, expect=200)
    _, r = api.call("PATCH", f"/api/tasks/{pending['id']}", {"is_done": False}, expect=200)
    assert r["column_id"] == col["Haciendo"]["id"]


def test_boards_own_their_columns(seeded):
    api = seeded["api"]
    board, col = board_and_columns(api)
    yesterday = (client_today() - timedelta(days=1)).isoformat()
    _, school = api.call("POST", "/api/boards", {"name": "Escuela"}, expect=201)
    scol = {c["name"]: c for c in school["columns"]}
    assert list(scol) == ["Por hacer", "Haciendo", "Hecho"] and scol["Hecho"]["id"] != col["Hecho"]["id"]
    _, leyendo = api.call("POST", f"/api/boards/{school['id']}/columns",
                          {"category": "doing", "name": "Leyendo", "color": "#123456"}, expect=201)
    assert leyendo["order"] == 3
    assert api.call("POST", "/api/boards", {"name": "Escuela"})[0] == 409
    assert api.call("POST", f"/api/boards/{school['id']}/columns", {"category": "doing", "name": "Leyendo"})[0] == 409
    # El mismo nombre en otro tablero sí vale
    api.call("POST", f"/api/boards/{board['id']}/columns", {"category": "doing", "name": "Leyendo"}, expect=201)

    pid = seeded["project"]["id"]
    _, t = api.call("POST", "/api/tasks", {"project_id": pid, "title": "Cap 3", "board_id": school["id"]}, expect=201)
    assert t["board_id"] == school["id"] and t["column_id"] == scol["Por hacer"]["id"]
    _, r = api.call("PATCH", f"/api/tasks/{t['id']}?today={yesterday}", {"is_done": True}, expect=200)
    assert r["column_id"] == scol["Hecho"]["id"], "the checkbox stays inside the task's own board"
    _, r = api.call("PATCH", f"/api/tasks/{t['id']}", {"column_id": col["Por hacer"]["id"]}, expect=200)
    assert r["board_id"] == board["id"] and not r["is_done"]
    api.call("PATCH", f"/api/tasks/{t['id']}", {"column_id": leyendo["id"]}, expect=200)
    _, bt = api.call("GET", f"/api/tasks?board_id={school['id']}", expect=200)
    assert [x["id"] for x in bt["tasks"]] == [t["id"]]


def test_delete_and_archive_rules(seeded):
    api = seeded["api"]
    board, col = board_and_columns(api)
    _, school = api.call("POST", "/api/boards", {"name": "Escuela"}, expect=201)
    scol = {c["name"]: c for c in school["columns"]}
    _, leyendo = api.call("POST", f"/api/boards/{school['id']}/columns", {"category": "doing", "name": "Leyendo"}, expect=201)
    _, t = api.call("POST", "/api/tasks", {"title": "x", "board_id": school["id"]}, expect=201)
    api.call("PATCH", f"/api/tasks/{t['id']}", {"column_id": leyendo["id"]}, expect=200)

    assert api.call("DELETE", f"/api/boards/{school['id']}/columns/{leyendo['id']}")[0] == 409   # tiene tareas
    assert api.call("DELETE", f"/api/boards/{school['id']}/columns/{scol['Hecho']['id']}")[0] == 409  # última "hecha"
    assert api.call("DELETE", f"/api/boards/{school['id']}")[0] == 409  # tiene tareas
    api.call("PATCH", f"/api/tasks/{t['id']}", {"column_id": col["Por hacer"]["id"]}, expect=200)
    api.call("DELETE", f"/api/boards/{school['id']}/columns/{leyendo['id']}", expect=204)
    api.call("PATCH", f"/api/boards/{school['id']}", {"is_active": False}, expect=200)
    assert api.call("PATCH", f"/api/boards/{board['id']}", {"is_active": False})[0] == 409  # último activo
    assert api.call("DELETE", f"/api/boards/{board['id']}")[0] == 409
    assert [b["name"] for b in api.call("GET", "/api/boards", expect=200)[1]["boards"]] == ["Mi tablero"]
    assert len(api.call("GET", "/api/boards?include_inactive=true", expect=200)[1]["boards"]) == 2
    api.call("DELETE", f"/api/boards/{school['id']}", expect=204)


def test_validation(seeded):
    api = seeded["api"]
    board, _ = board_and_columns(api)
    url = f"/api/boards/{board['id']}/columns"
    assert api.call("POST", url, {"category": "idea", "name": "X"})[0] == 422
    assert api.call("POST", url, {"category": "todo", "name": "X", "color": "red"})[0] == 422
    assert api.call("POST", url, {"category": "todo", "name": "   "})[0] == 422
    assert api.call("POST", "/api/boards", {"name": "x" * 61})[0] == 422
    assert api.call("GET", "/api/project-statuses")[0] == 404


def test_reorder_cards_in_a_column(seeded):
    api = seeded["api"]
    _, col = board_and_columns(api)
    hecho = col["Hecho"]["id"]

    def titles(column_id):
        _, tl = api.call("GET", "/api/tasks", expect=200)
        return [t["title"] for t in tl["tasks"] if t["column_id"] == column_id]

    first = titles(hecho)
    _, new = api.call("POST", "/api/tasks", {"title": "Nueva al final", "column_id": hecho}, expect=201)
    assert titles(hecho)[-1] == "Nueva al final"
    _, tl = api.call("GET", "/api/tasks", expect=200)
    ids = {t["title"]: t["id"] for t in tl["tasks"]}
    order = [ids["Nueva al final"]] + [ids[t] for t in first]
    api.call("POST", "/api/tasks/reorder", {"column_id": hecho, "task_ids": order}, expect=204)
    assert titles(hecho)[0] == "Nueva al final"
    assert api.call("POST", "/api/tasks/reorder", {"column_id": hecho, "task_ids": order + [order[0]]})[0] == 422
    assert api.call("POST", "/api/tasks/reorder", {"column_id": col["Por hacer"]["id"], "task_ids": order})[0] == 422
    # Moverla a otra columna o marcarla la manda al final
    api.call("PATCH", f"/api/tasks/{new['id']}", {"column_id": col["Por hacer"]["id"]}, expect=200)
    assert titles(col["Por hacer"]["id"])[-1] == "Nueva al final"
    api.call("PATCH", f"/api/tasks/{new['id']}", {"is_done": True}, expect=200)
    assert titles(hecho)[-1] == "Nueva al final"
