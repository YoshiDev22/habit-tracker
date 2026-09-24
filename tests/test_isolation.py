"""
Aislamiento entre usuarios: toda query filtra por el usuario de la sesión. Otro
usuario no puede leer, usar ni tocar tableros, columnas, tareas, etiquetas,
checklist, comentarios, registros de tiempo ni hábitos ajenos (404, no 403: ni
siquiera se entera de que existen).
"""


def mine(seeded):
    api = seeded["api"]
    _, bl = api.call("GET", "/api/boards", expect=200)
    board = bl["boards"][0]
    col = board["columns"][0]
    task = seeded["tasks"]["Corrección de Pomodoros"]
    _, tag = api.call("POST", "/api/tags", {"name": "doc"}, expect=201)
    _, item = api.call("POST", f"/api/tasks/{task['id']}/checklist", {"text": "a"}, expect=201)
    _, comment = api.call("POST", f"/api/tasks/{task['id']}/comments", {"body": "b"}, expect=201)
    _, ss = api.call("GET", f"/api/pomodoro?task_id={task['id']}", expect=200)
    _, habit = api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    return dict(board=board, col=col, task=task, tag=tag, item=item, comment=comment,
                session=ss["sessions"][0], habit=habit)


def test_boards_and_columns(seeded):
    m = mine(seeded)
    other = seeded["other"]
    _, obl = other.call("GET", "/api/boards", expect=200)
    assert obl["total"] == 1 and obl["boards"][0]["id"] != m["board"]["id"]
    assert other.call("GET", f"/api/tasks?board_id={m['board']['id']}", expect=200)[1]["total"] == 0
    assert other.call("PATCH", f"/api/boards/{m['board']['id']}", {"name": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/boards/{m['board']['id']}")[0] == 404
    assert other.call("POST", f"/api/boards/{m['board']['id']}/columns", {"category": "todo", "name": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/boards/{m['board']['id']}/columns/{m['col']['id']}")[0] == 404


def test_tasks(seeded):
    m = mine(seeded)
    other = seeded["other"]
    own = seeded["other_task"]
    assert all(t["id"] != m["task"]["id"] for t in other.call("GET", "/api/tasks", expect=200)[1]["tasks"])
    assert other.call("PATCH", f"/api/tasks/{m['task']['id']}", {"title": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/tasks/{m['task']['id']}")[0] == 404
    # Ni meter su tarea en mi columna, ni crear en mi tablero, ni reordenar mi columna
    assert other.call("PATCH", f"/api/tasks/{own['id']}", {"column_id": m["col"]["id"]})[0] == 404
    assert other.call("POST", "/api/tasks", {"title": "x", "board_id": m["board"]["id"]})[0] == 404
    assert other.call("POST", "/api/tasks/reorder", {"column_id": m["col"]["id"], "task_ids": [m["task"]["id"]]})[0] == 404
    assert other.call("PATCH", f"/api/tasks/{own['id']}", {"project_id": seeded["project"]["id"]})[0] == 404


def test_tags(seeded):
    m = mine(seeded)
    other = seeded["other"]
    own = seeded["other_task"]
    assert other.call("PATCH", f"/api/tasks/{own['id']}", {"tag_ids": [m["tag"]["id"]]})[0] == 404
    assert other.call("PATCH", f"/api/tags/{m['tag']['id']}", {"name": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/tags/{m['tag']['id']}")[0] == 404
    assert other.call("GET", "/api/tags/summary", expect=200)[1]["total"] == 0
    assert other.call("GET", f"/api/tasks?tag_id={m['tag']['id']}", expect=200)[1]["total"] == 0
    other.call("POST", "/api/tags", {"name": "doc"}, expect=201)     # el mismo nombre, suyo: vale


def test_checklist_and_comments(seeded):
    m = mine(seeded)
    other = seeded["other"]
    tid = m["task"]["id"]
    assert other.call("GET", f"/api/tasks/{tid}/checklist")[0] == 404
    assert other.call("POST", f"/api/tasks/{tid}/comments", {"body": "hola"})[0] == 404
    assert other.call("PATCH", f"/api/tasks/{tid}/checklist/{m['item']['id']}", {"is_done": True})[0] == 404
    assert other.call("DELETE", f"/api/tasks/{tid}/comments/{m['comment']['id']}")[0] == 404
    # Tampoco a través del id de una tarea suya
    own = seeded["other_task"]["id"]
    assert other.call("PATCH", f"/api/tasks/{own}/checklist/{m['item']['id']}", {"is_done": True})[0] == 404
    assert other.call("PATCH", f"/api/tasks/{own}/comments/{m['comment']['id']}", {"body": "x"})[0] == 404


def test_time_and_habits(seeded):
    m = mine(seeded)
    other = seeded["other"]
    assert other.call("GET", f"/api/pomodoro?task_id={m['task']['id']}", expect=200)[1]["sessions"] == []
    assert other.call("PATCH", f"/api/pomodoro/{m['session']['id']}", {"note": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/pomodoro/{m['session']['id']}")[0] == 404
    # Registrar tiempo en una tarea ajena
    assert other.call("POST", "/api/pomodoro", {
        "task_id": m["task"]["id"], "session_date": m["session"]["session_date"],
        "started_at": m["session"]["started_at"], "ended_at": m["session"]["ended_at"],
        "duration_seconds": 60, "mode": "focus"})[0] == 404
    assert other.call("GET", "/api/habits/definitions", expect=200)[1]["habits"] == []
    assert other.call("PATCH", f"/api/habits/definitions/{m['habit']['id']}", {"label": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/habits/definitions/{m['habit']['id']}")[0] == 404
