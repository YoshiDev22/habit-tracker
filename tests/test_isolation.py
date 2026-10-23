"""
Aislamiento entre usuarios: toda query filtra por el usuario de la sesión. Otro
usuario no puede leer, usar ni tocar tableros, columnas, tareas, etiquetas,
checklist, comentarios, registros de tiempo ni hábitos ajenos (404, no 403: ni
siquiera se entera de que existen).
"""
from datetime import date, timedelta


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
    assert other.call("PATCH", f"/api/tasks/{m['task']['id']}", {"estimate_minutes": 60})[0] == 404


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


def test_costs(seeded):
    from test_finance import maker_on
    api, other = seeded["api"], seeded["other"]
    maker_on(api, "yoshi@test.com")
    maker_on(other, "otro@test.com")
    pid = seeded["project"]["id"]
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = cats["categories"][0]["id"]
    row = {"category_id": cat, "cost_date": date.today().isoformat(), "concept": "Base", "unit_cost_cents": 100}
    _, cost = api.call("POST", "/api/costs", {"project_id": pid, **row}, expect=201)
    _, theirs = other.call("GET", "/api/costs/categories", expect=200)
    their_cat = theirs["categories"][0]["id"]
    their_pid = seeded["other_project"]["id"]
    # Ni ver, ni tocar, ni usar mis gastos, mis categorías o mis proyectos
    assert other.call("GET", f"/api/costs?project_id={pid}")[0] == 404
    assert other.call("POST", "/api/costs", {"project_id": pid, **row, "category_id": their_cat})[0] == 404
    assert other.call("POST", "/api/costs/import", {"project_id": pid, "rows": [{**row, "category_id": their_cat}]})[0] == 404
    assert other.call("POST", "/api/costs", {"project_id": their_pid, **row})[0] == 404, "my category in their project"
    assert other.call("PATCH", f"/api/costs/{cost['id']}", {"concept": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/costs/{cost['id']}")[0] == 404
    assert other.call("PATCH", f"/api/costs/categories/{cat}", {"name": "hack"})[0] == 404
    assert other.call("DELETE", f"/api/costs/categories/{cat}")[0] == 404
    _, sm = other.call("GET", "/api/costs/summary", expect=200)
    assert all(r["project_id"] != pid for r in sm["projects"]) and sm["categories"] == []
    assert api.call("GET", f"/api/costs?project_id={pid}", expect=200)[1]["costs"][0]["concept"] == "Base"

    # Mis estimados (con mi etiqueta) no salen en los suyos
    task_id = seeded["tasks"]["Corrección de Pomodoros"]["id"]
    _, tag = api.call("POST", "/api/tags", {"name": "doc"}, expect=201)
    api.call("PATCH", f"/api/tasks/{task_id}", {"estimate_minutes": 60, "tag_ids": [tag["id"]]}, expect=200)
    assert api.call("GET", "/api/costs/estimates", expect=200)[1]["overall"]["tasks"] == 1
    _, theirs = other.call("GET", "/api/costs/estimates", expect=200)
    assert theirs["overall"]["tasks"] == 0 and theirs["tags"] == []



def test_personal_finance(seeded):
    from test_personal_finance import finance_on, tx
    api, other = seeded["api"], seeded["other"]
    finance_on(api, "yoshi@test.com")
    finance_on(other, "otro@test.com")
    mine = {a["name"]: a for a in api.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"]}["Efectivo"]
    cats = api.call("GET", "/api/finance/categories", expect=200)[1]["categories"]
    cat = cats[0]
    _, card = api.call("POST", "/api/finance/accounts", {"name": "Tarjeta", "kind": "credit"}, expect=201)
    _, t = api.call("POST", "/api/finance/transactions", tx(mine, 23000, "Tacos", cat), expect=201)
    _, rc = api.call("POST", "/api/finance/recurring", {
        "account_id": mine["id"], "category_id": cat["id"], "concept": "Renta", "amount_cents": 100,
        "start_date": (date.today() + timedelta(days=5)).isoformat()}, expect=201)
    api.call("PATCH", f"/api/finance/accounts/{card['id']}", {"statement_day": 5, "due_day": 25}, expect=200)
    _, laptop = api.call("POST", "/api/finance/transactions", tx(card, 1200, "Laptop", cat), expect=201)
    _, msi = api.call("POST", "/api/finance/installments", {"transaction_id": laptop["id"], "months": 3}, expect=201)
    theirs = other.call("GET", "/api/finance/accounts", expect=200)[1]["accounts"][0]
    their_cat = other.call("GET", "/api/finance/categories", expect=200)[1]["categories"][0]
    _, group = api.call("POST", "/api/finance/budget/groups", {"name": "Necesarios", "percent_bp": 4500}, expect=201)
    _, line = api.call("POST", "/api/finance/budget/items", {"group_id": group["id"], "name": "Renta",
                                                             "amount_cents": 450_000}, expect=201)
    _, their_group = other.call("POST", "/api/finance/budget/groups", {"name": "Suyo"}, expect=201)
    my_rate = api.call("PUT", f"/api/finance/accounts/{mine['id']}/yield-rates", {"from_date": "2020-01-01",
                                                                                  "rate_bp": 1500}, expect=200)[1]["rates"][0]["id"]
    term_body = {"account_id": mine["id"], "principal_cents": 100, "start_date": date.today().isoformat(), "days": 28,
                 "rate_bp": 1100}
    my_term = api.call("POST", "/api/finance/terms", term_body, expect=201)[1]["id"]

    # Ni ver, ni tocar, ni usar mis cuentas, categorías, movimientos, fijos o presupuesto
    for method, path, body in [
        ("PATCH", f"/api/finance/accounts/{mine['id']}", {"name": "hack"}),
        ("DELETE", f"/api/finance/accounts/{card['id']}", None),
        ("PATCH", f"/api/finance/categories/{cat['id']}", {"name": "hack"}),
        ("DELETE", f"/api/finance/categories/{cat['id']}", None),
        ("PATCH", f"/api/finance/transactions/{t['id']}", {"concept": "hack"}),
        ("DELETE", f"/api/finance/transactions/{t['id']}", None),
        ("PATCH", f"/api/finance/recurring/{rc['id']}", {"concept": "hack"}),
        ("DELETE", f"/api/finance/recurring/{rc['id']}", None),
        ("POST", "/api/finance/transactions", tx(mine, 1, "x", their_cat)),
        ("POST", "/api/finance/transactions", tx(theirs, 1, "x", cat)),
        ("POST", "/api/finance/transactions", tx(theirs, 1, "x", kind="transfer", to=card)),
        ("POST", "/api/finance/transactions/import", {"rows": [tx(theirs, 1, "x", cat)]}),
        ("POST", "/api/finance/recurring", {"account_id": theirs["id"], "category_id": cat["id"], "concept": "x",
                                            "amount_cents": 1, "start_date": date.today().isoformat()}),
        ("GET", f"/api/finance/accounts/{card['id']}/statement", None),
        ("DELETE", f"/api/finance/installments/{msi['id']}", None),
        ("POST", "/api/finance/installments", {"transaction_id": laptop["id"], "months": 2}),
        ("POST", "/api/finance/installments", {"account_id": card["id"], "concept": "x", "total_cents": 100,
                                               "months": 1, "purchase_date": date.today().isoformat()}),
        ("PUT", "/api/finance/categories/order", {"kind": cat["kind"], "ids": [cat["id"]]}),
        ("PUT", f"/api/finance/accounts/{card['id']}/statement", {"cut_date": date.today().isoformat(),
                                                                  "pay_no_interest_cents": 1}),
        ("DELETE", f"/api/finance/accounts/{card['id']}/statement?cut_date={date.today().isoformat()}", None),
        ("PATCH", f"/api/finance/budget/groups/{group['id']}", {"name": "hack"}),
        ("DELETE", f"/api/finance/budget/groups/{group['id']}", None),
        ("PATCH", f"/api/finance/budget/items/{line['id']}", {"name": "hack"}),
        ("DELETE", f"/api/finance/budget/items/{line['id']}", None),
        ("POST", "/api/finance/budget/items", {"group_id": group["id"], "name": "x"}),
        ("POST", "/api/finance/budget/items", {"group_id": their_group["id"], "name": "x", "category_id": cat["id"]}),
        ("POST", "/api/finance/budget/items", {"group_id": their_group["id"], "name": "x", "recurring_id": rc["id"]}),
        ("POST", "/api/finance/transactions", {**tx(theirs, 2, "x"), "category_id": None,
                                               "splits": [{"category_id": cat["id"], "amount_cents": 1},
                                                          {"category_id": their_cat["id"], "amount_cents": 1}]}),
        # Ni colgar un apartado suyo de mi cuenta
        ("POST", "/api/finance/accounts", {"name": "Apartado", "parent_id": mine["id"]}),
        ("PATCH", f"/api/finance/accounts/{theirs['id']}", {"parent_id": mine["id"]}),
        # Ni ver ni tocar el rendimiento de mis cuentas
        ("GET", f"/api/finance/accounts/{mine['id']}/yield", None),
        ("PUT", f"/api/finance/accounts/{mine['id']}/yield-rates", {"from_date": "2020-01-01", "rate_bp": 1}),
        ("DELETE", f"/api/finance/accounts/{mine['id']}/yield-rates/{my_rate}", None),
        ("DELETE", f"/api/finance/accounts/{theirs['id']}/yield-rates/{my_rate}", None),
        ("POST", f"/api/finance/accounts/{mine['id']}/yield", {"amount_cents": 1}),
        # Ni mis plazos fijos, ni poner uno en mi cuenta o que regrese a ella
        ("PUT", f"/api/finance/terms/{my_term}", {**term_body, "account_id": theirs["id"]}),
        ("DELETE", f"/api/finance/terms/{my_term}", None),
        ("POST", "/api/finance/terms", term_body),
        ("POST", "/api/finance/terms", {**term_body, "account_id": theirs["id"], "on_maturity": "return",
                                        "return_account_id": mine["id"]}),
    ]:
        assert other.call(method, path, body)[0] == 404, (method, path)
    _, their_tx = other.call("POST", "/api/finance/transactions", tx(theirs, 1, "suyo", their_cat), expect=201)
    assert other.call("PATCH", f"/api/finance/transactions/{their_tx['id']}", {"account_id": mine["id"]})[0] == 404

    _, sm = other.call("GET", "/api/finance/summary", expect=200)
    assert [a["name"] for a in sm["accounts"]] == ["Efectivo"] and sm["totals"][0]["expense_cents"] == 1
    assert [t["concept"] for t in other.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"]] == ["suyo"]
    assert other.call("GET", "/api/finance/recurring", expect=200)[1]["recurring"] == []
    assert other.call("GET", "/api/finance/installments", expect=200)[1]["installments"] == []
    assert [g["name"] for g in other.call("GET", "/api/finance/budget", expect=200)[1]["groups"]] == ["Suyo"]
    assert other.call("GET", "/api/finance/budget", expect=200)[1]["items"] == []
    assert other.call("GET", f"/api/finance/transactions?account_id={mine['id']}", expect=200)[1]["transactions"] == []
    # Lo mío, intacto
    assert sorted(x["concept"] for x in api.call("GET", "/api/finance/transactions", expect=200)[1]["transactions"]) == ["Laptop", "Tacos"]

def test_saved_reports(seeded):
    api, other = seeded["api"], seeded["other"]
    monday = date.today() - timedelta(days=date.today().weekday())
    _, rep = api.call("POST", "/api/reports", {"kind": "week", "period_start": monday.isoformat(),
                                               "today": date.today().isoformat()}, expect=200)
    assert other.call("GET", f"/api/reports/{rep['id']}")[0] == 404
    assert all(r["id"] != rep["id"] for r in other.call("GET", "/api/reports", expect=200)[1]["reports"])
    assert other.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 404
