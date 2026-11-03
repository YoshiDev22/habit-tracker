"""
Grupos de proyectos (1.34, docs/specs/grupos-de-proyectos.md): un grupo es un
proyecto con hijos (projects.parent_id). Un solo nivel, un solo grupo por
proyecto, de la misma cuenta, y "Sin asignar" fuera.
"""


def project(api, name, **extra):
    return api.call("POST", "/api/projects", {"name": name, **extra}, expect=201)[1]


def unassigned(api):
    _, listing = api.call("GET", "/api/projects", expect=200)
    return next(p for p in listing["projects"] if p["is_system"])


def test_a_project_goes_into_a_group_and_back_out(api):
    api.login("grupos@test.com")
    group = project(api, "Emprendimiento")
    assert group["parent_id"] is None
    # Al crearlo, o después con PATCH
    campaign = project(api, "Campaña", parent_id=group["id"])
    assert campaign["parent_id"] == group["id"]
    app = project(api, "App")
    _, moved = api.call("PATCH", f"/api/projects/{app['id']}", {"parent_id": group["id"]}, expect=200)
    assert moved["parent_id"] == group["id"]
    _, listing = api.call("GET", "/api/projects", expect=200)
    assert {p["name"]: p["parent_id"] for p in listing["projects"]}["Campaña"] == group["id"]
    # Cambiar otra cosa no lo saca del grupo; null sí
    _, renamed = api.call("PATCH", f"/api/projects/{app['id']}", {"name": "App 2"}, expect=200)
    assert renamed["parent_id"] == group["id"]
    _, out = api.call("PATCH", f"/api/projects/{app['id']}", {"parent_id": None}, expect=200)
    assert out["parent_id"] is None


def test_one_level_only(api):
    api.login("niveles@test.com")
    group = project(api, "Grupo")
    child = project(api, "Hijo", parent_id=group["id"])
    other = project(api, "Otro")
    # Nada dentro de un proyecto que ya está en un grupo
    status, body = api.call("POST", "/api/projects", {"name": "Nieto", "parent_id": child["id"]})
    assert status == 409 and "un grupo no va dentro de otro" in body["detail"]
    # Un grupo no entra en otro
    status, body = api.call("PATCH", f"/api/projects/{group['id']}", {"parent_id": other["id"]})
    assert status == 409 and "es un grupo (1 proyecto)" in body["detail"]
    # Ni en sí mismo
    assert api.call("PATCH", f"/api/projects/{other['id']}", {"parent_id": other["id"]})[0] == 422


def test_sin_asignar_is_neither_in_a_group_nor_one(api):
    api.login("sistema@test.com")
    group = project(api, "Grupo")
    system = unassigned(api)
    assert api.call("PATCH", f"/api/projects/{system['id']}", {"parent_id": group["id"]})[0] == 409
    status, body = api.call("POST", "/api/projects", {"name": "X", "parent_id": system["id"]})
    assert status == 409 and "Sin asignar" in body["detail"]


def test_an_archived_project_takes_no_members(api):
    api.login("archivado@test.com")
    group = project(api, "Viejo")
    api.call("PATCH", f"/api/projects/{group['id']}", {"is_active": False}, expect=200)
    status, body = api.call("POST", "/api/projects", {"name": "Nuevo", "parent_id": group["id"]})
    assert status == 409 and "archivado" in body["detail"]


def test_archiving_a_group_keeps_its_projects(api):
    api.login("archivar@test.com")
    group = project(api, "Grupo")
    child = project(api, "Hijo", parent_id=group["id"])
    api.call("PATCH", f"/api/projects/{group['id']}", {"is_active": False}, expect=200)
    _, kept = api.call("GET", f"/api/projects/{child['id']}", expect=200)
    assert kept["is_active"] and kept["parent_id"] == group["id"]


def test_deleting_a_group_leaves_its_projects_ungrouped(api):
    api.login("borrar@test.com")
    group = project(api, "Grupo")
    child = project(api, "Hijo", parent_id=group["id"])
    _, task = api.call("POST", "/api/tasks", {"project_id": child["id"], "title": "sigue"}, expect=201)
    api.call("DELETE", f"/api/projects/{group['id']}", expect=204)
    _, kept = api.call("GET", f"/api/projects/{child['id']}", expect=200)
    assert kept["parent_id"] is None
    # Sus tareas no se tocan: siguen en su proyecto
    _, tasks = api.call("GET", "/api/tasks", expect=200)
    assert next(t for t in tasks["tasks"] if t["id"] == task["id"])["project_id"] == child["id"]


def test_metrics_and_the_saved_report_add_up_each_group(api):
    """Fase 3: cada proyecto dice su grupo y by_group da el subtotal (lo propio
    del grupo más sus proyectos); el reporte guardado y lo que recibe la IA, igual."""
    from datetime import date, timedelta

    from backend.report_ai import ai_payload
    from test_metrics import post

    api.login("reporte-grupos@test.com")
    group = project(api, "Emprendimiento")
    campaign = project(api, "Campaña", parent_id=group["id"])
    app = project(api, "App", parent_id=group["id"])
    loose = project(api, "Tesis")
    project(api, "Vacío", parent_id=group["id"])   # sin tiempo: no sale
    monday = date.today() - timedelta(days=date.today().weekday() + 7)
    post(api, group, None, monday, 9, 30)
    post(api, campaign, None, monday, 10, 60)
    post(api, app, None, monday + timedelta(days=1), 9, 90)
    post(api, loose, None, monday + timedelta(days=2), 9, 120)

    sunday = monday + timedelta(days=6)
    _, m = api.call("GET", f"/api/metrics?date_from={monday}&date_to={sunday}&today={date.today()}", expect=200)
    rows = {p["name"]: (p["group"], p["is_group"]) for p in m["by_project"]}
    assert rows == {"Tesis": (None, False), "App": ("Emprendimiento", False),
                    "Campaña": ("Emprendimiento", False), "Emprendimiento": ("Emprendimiento", True)}
    assert len(m["by_group"]) == 1
    g = m["by_group"][0]
    assert (g["name"], g["seconds"], g["own_seconds"], g["pct"]) == ("Emprendimiento", 180 * 60, 30 * 60, 60)
    assert g["projects"] == ["App", "Campaña"]
    assert g["seconds"] == sum(p["seconds"] for p in m["by_project"] if p["group"] == "Emprendimiento")

    _, rep = api.call("POST", "/api/reports", {"kind": "week", "period_start": monday.isoformat(),
                                               "today": date.today().isoformat()}, expect=200)
    assert rep["metrics"]["by_group"][0]["seconds"] == 180 * 60
    observations = " ".join(rep["text"]["observations"])
    assert "El grupo Emprendimiento sumó 3.0 h (60 % del tiempo) entre App, Campaña y lo general del grupo." \
        in observations, observations
    sent = ai_payload("week", rep["metrics"], rep["text"])["metrics"]
    assert sent["by_group"][0] == {"name": "Emprendimiento", "minutes": 180, "own_minutes": 30,
                                   "projects": ["App", "Campaña"], "pct": 60}
    assert {"name": "Campaña", "minutes": 60, "pct": 20, "group": "Emprendimiento", "is_group": False} \
        in sent["by_project"]
