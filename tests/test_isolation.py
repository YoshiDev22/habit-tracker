"""
Aislamiento entre usuarios: toda query filtra por el usuario de la sesión. Otro
usuario no puede leer, usar ni tocar tableros, columnas, tareas, etiquetas,
checklist, comentarios, registros de tiempo ni hábitos ajenos (404, no 403: ni
siquiera se entera de que existen).
"""
from datetime import date


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


def test_project_overview(seeded):
    other = seeded["other"]
    # La ficha de un proyecto ajeno (activo o archivado) no existe para mí
    assert other.call("GET", f"/api/projects/{seeded['project']['id']}/overview")[0] == 404
    assert other.call("GET", f"/api/projects/{seeded['archived']['id']}/overview")[0] == 404
    _, own = other.call("GET", f"/api/projects/{seeded['other_project']['id']}/overview", expect=200)
    assert own["total_seconds"] == 0 and [t["title"] for t in own["tasks"]] == ["Tarea ajena"]


def test_project_finance(seeded):
    from test_finance import maker_on
    api, other = seeded["api"], seeded["other"]
    maker_on(api, "yoshi@test.com")
    maker_on(other, "otro@test.com")
    url = f"/api/projects/{seeded['project']['id']}/finance"
    api.call("PUT", url, {"hourly_rate_cents": 35000}, expect=200)
    # Con el plan maker encendido, el costeo ajeno sigue sin existir para mí
    assert other.call("GET", url)[0] == 404
    assert other.call("PUT", url, {"hourly_rate_cents": 1})[0] == 404
    assert api.call("GET", url, expect=200)[1]["hourly_rate_cents"] == 35000


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
    # La clave de idempotencia es de cada usuario: la misma clave en otra cuenta
    # crea su propia sesión, no le devuelve la ajena
    key_body = {"session_date": m["session"]["session_date"], "started_at": m["session"]["started_at"],
                "ended_at": m["session"]["ended_at"], "duration_seconds": 60, "mode": "focus",
                "idempotency_key": "misma-clave"}
    _, own = seeded["api"].call("POST", "/api/pomodoro", key_body, expect=201)
    _, theirs = other.call("POST", "/api/pomodoro", key_body, expect=201)
    assert theirs["id"] != own["id"]
    assert other.call("GET", "/api/habits/definitions", expect=200)[1]["habits"] == []
    assert other.call("PATCH", f"/api/habits/definitions/{m['habit']['id']}", {"label": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/habits/definitions/{m['habit']['id']}")[0] == 404
    assert other.call("GET", f"/api/habits/definitions/{m['habit']['id']}/delete-impact")[0] == 404
    today = date.today()
    _, mh = other.call("GET", f"/api/habits/month-habits?year={today.year}&month={today.month}", expect=200)
    assert all(h["id"] != m["habit"]["id"] for h in mh["habits"])
    # Las pausas de otro no se ven ni se cancelan
    _, mine_pause = seeded["api"].call("POST", f"/api/habits/pauses?today={today}",
                                       {"start_date": str(today), "end_date": str(today)}, expect=201)
    assert other.call("GET", "/api/habits/pauses", expect=200)[1]["pauses"] == []
    assert other.call("DELETE", f"/api/habits/pauses/{mine_pause['id']}?today={today}")[0] == 404
    # Marcar un día toca solo los registros propios: el hábito ajeno no existe para él
    assert other.call("PATCH", "/api/habits/day/2026-01-05", {"habit_key": "gym", "done": True})[0] == 404
