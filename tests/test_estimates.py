"""Estimado contra real (épica 24, Fase 4): el estimado de cada tarea y cuánto
se desvía el usuario de lo que estima, en la ficha y en Costos."""
from datetime import date

from conftest import log_time
from test_finance import maker_on

M = 60
TODAY = date.today().isoformat()


def task(api, project_id, title, estimate=None, minutes=0, done=False, tag_ids=None):
    _, t = api.call("POST", "/api/tasks", {"project_id": project_id, "title": title}, expect=201)
    body = {}
    if estimate is not None:
        body["estimate_minutes"] = estimate
    if tag_ids:
        body["tag_ids"] = tag_ids
    if done:
        body["is_done"] = True
    if body:
        api.call("PATCH", f"/api/tasks/{t['id']}?today={TODAY}", body, expect=200)
    if minutes:
        log_time(api, project_id, t["id"], minutes * M)
    return t


def test_set_change_and_clear_without_the_maker_plan(api):
    # El estimado es de todos: sin el plan maker se guarda igual
    api.login("plan@test.com")
    _, t = api.call("POST", "/api/tasks", {"title": "Cotizar"}, expect=201)
    assert t["estimate_minutes"] is None
    url = f"/api/tasks/{t['id']}"
    assert api.call("PATCH", url, {"estimate_minutes": 90}, expect=200)[1]["estimate_minutes"] == 90
    assert api.call("PATCH", url, {"estimate_minutes": 120}, expect=200)[1]["estimate_minutes"] == 120
    # Un PATCH sin el campo no lo toca
    assert api.call("PATCH", url, {"title": "Cotizar lámpara"}, expect=200)[1]["estimate_minutes"] == 120
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(x for x in tl["tasks"] if x["id"] == t["id"])["estimate_minutes"] == 120
    # null lo borra
    assert api.call("PATCH", url, {"estimate_minutes": None}, expect=200)[1]["estimate_minutes"] is None


def test_the_deviation_needs_the_maker_plan(api):
    api.login("sinplan@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    t = task(api, p["id"], "T", estimate=60, minutes=90, done=True)
    assert api.call("GET", "/api/costs/estimates")[0] == 403
    _, ov = api.call("GET", f"/api/projects/{p['id']}/overview", expect=200)
    assert ov["estimates"] is None
    # La ficha sí lleva el estimado de cada tarea: eso es de todos
    assert ov["tasks"][0]["estimate_minutes"] == 60 and ov["tasks"][0]["id"] == t["id"]


def test_the_rule(api):
    api.login("regla@test.com")
    maker_on(api, "regla@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "Tienda"}, expect=201)
    _, back = api.call("POST", "/api/tags", {"name": "backend"}, expect=201)
    _, design = api.call("POST", "/api/tags", {"name": "diseño"}, expect=201)
    pid = p["id"]
    task(api, pid, "A", estimate=60, minutes=90, done=True, tag_ids=[back["id"]])
    task(api, pid, "B", estimate=60, minutes=60, done=True, tag_ids=[back["id"], design["id"]])
    task(api, pid, "C abierta, por debajo", estimate=60, minutes=30, tag_ids=[back["id"]])     # no cuenta
    task(api, pid, "D abierta, ya pasada", estimate=30, minutes=45, tag_ids=[back["id"]])      # cuenta
    task(api, pid, "E sin tiempo", estimate=60, done=True)                                     # no cuenta
    task(api, pid, "F sin estimado", minutes=60, done=True)                                    # no cuenta
    task(api, pid, "G sin etiqueta", estimate=120, minutes=100, done=True)

    _, ov = api.call("GET", f"/api/projects/{pid}/overview", expect=200)
    est = ov["estimates"]
    assert est["min_tasks"] == 3
    # Cada tarea una vez: A, B, D y G; cociente de sumas, 295 ÷ 270 = 109 %
    assert est["overall"] == {"tasks": 4, "estimate_seconds": 270 * M, "actual_seconds": 295 * M, "ratio_pct": 109}
    rows = {r["name"]: r for r in est["tags"]}
    # backend: A, B y D (195 ÷ 150); B también cuenta en diseño, pero sola no da cifra
    assert (rows["backend"]["tasks"], rows["backend"]["ratio_pct"]) == (3, 130)
    assert (rows["diseño"]["tasks"], rows["diseño"]["ratio_pct"]) == (1, None)
    assert [r["name"] for r in est["tags"]] == ["backend", "diseño"], "most tasks first"
    assert est["untagged"] == {"tasks": 1, "estimate_seconds": 120 * M, "actual_seconds": 100 * M, "ratio_pct": None}

    # Cuadre: con un solo proyecto, Costos dice lo mismo que la ficha
    assert api.call("GET", "/api/costs/estimates", expect=200)[1] == est

    # Costos junta todos los proyectos, archivados incluidos; la ficha, solo el suyo
    _, other = api.call("POST", "/api/projects", {"name": "Viejo"}, expect=201)
    task(api, other["id"], "H", estimate=60, minutes=60, done=True)
    api.call("PATCH", f"/api/projects/{other['id']}", {"is_active": False}, expect=200)
    _, all_est = api.call("GET", "/api/costs/estimates", expect=200)
    assert all_est["overall"]["tasks"] == 5 and all_est["untagged"]["tasks"] == 2
    assert api.call("GET", f"/api/projects/{pid}/overview", expect=200)[1]["estimates"] == est


def test_an_open_task_that_finishes_under_its_estimate_starts_counting(api):
    api.login("abierta@test.com")
    maker_on(api, "abierta@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    t = task(api, p["id"], "Va por debajo", estimate=60, minutes=30)
    assert api.call("GET", "/api/costs/estimates", expect=200)[1]["overall"]["tasks"] == 0
    api.call("PATCH", f"/api/tasks/{t['id']}?today={TODAY}", {"is_done": True}, expect=200)
    assert api.call("GET", "/api/costs/estimates", expect=200)[1]["overall"]["tasks"] == 1


def test_ratio_rounds_half_up(api):
    # 201 min de 200 estimados = 100.5 %: sube a 101 (round() daría 100, al par)
    api.login("redondeo@test.com")
    maker_on(api, "redondeo@test.com")
    _, p = api.call("POST", "/api/projects", {"name": "P"}, expect=201)
    for estimate, minutes in [(60, 60), (60, 60), (80, 81)]:
        task(api, p["id"], f"{estimate}", estimate=estimate, minutes=minutes, done=True)
    _, est = api.call("GET", "/api/costs/estimates", expect=200)
    assert (est["overall"]["estimate_seconds"], est["overall"]["actual_seconds"]) == (200 * M, 201 * M)
    assert est["overall"]["ratio_pct"] == 101
