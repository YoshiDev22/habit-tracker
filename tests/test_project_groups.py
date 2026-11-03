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


def test_costs_add_up_each_group_by_currency(api):
    """Fase 4: el resumen de Costos da el subtotal de cada grupo por moneda (nunca
    se suman monedas) y el reporte de costos del mes, igual."""
    from datetime import date

    from conftest import log_time
    from test_costs import add
    from test_finance import maker_on

    api.login("costos-grupos@test.com")
    maker_on(api, "costos-grupos@test.com")
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = cats["categories"][0]["id"]
    group = project(api, "Taller")
    lamp = project(api, "Lámpara", parent_id=group["id"])
    abroad = project(api, "Encargo", parent_id=group["id"])
    loose = project(api, "Suelto")
    api.call("PUT", f"/api/projects/{abroad['id']}/finance", {"currency": "USD"}, expect=200)
    api.call("PUT", f"/api/projects/{lamp['id']}/finance", {"hourly_rate_cents": 20000, "budget_cents": 100000},
             expect=200)
    add(api, group["id"], cat, "Filamento", 30000)       # lo general del grupo
    add(api, lamp["id"], cat, "Foco", 5000)
    add(api, abroad["id"], cat, "Envío", 2000)
    add(api, loose["id"], cat, "Otro", 1000)
    log_time(api, lamp["id"], None, 3600)                # 1 h × $200 = mano de obra

    _, summary = api.call("GET", "/api/costs/summary", expect=200)
    rows = {p["name"]: (p["group_id"], p["is_group"]) for p in summary["projects"]}
    assert rows["Taller"] == (group["id"], True) and rows["Lámpara"] == (group["id"], False)
    assert rows["Suelto"] == (None, False)
    by_currency = {g["currency"]: g for g in summary["groups"]}
    assert set(by_currency) == {"MXN", "USD"}
    mxn = by_currency["MXN"]
    assert (mxn["name"], mxn["labor_cents"], mxn["costs_cents"], mxn["total_cost_cents"], mxn["budget_cents"]) \
        == ("Taller", 20000, 35000, 55000, 100000)
    assert sorted(mxn["project_ids"]) == sorted([group["id"], lamp["id"]])
    assert by_currency["USD"]["total_cost_cents"] == 2000 and by_currency["USD"]["project_ids"] == [abroad["id"]]

    _, rep = api.call("POST", "/api/reports", {"kind": "costs-month", "period_start": date.today().replace(day=1)
                                               .isoformat(), "today": date.today().isoformat()}, expect=200)
    groups = {(g["name"], g["currency"]): g for g in rep["metrics"]["groups"]}
    assert groups[("Taller", "MXN")]["total_cost_cents"] == 55000
    assert groups[("Taller", "MXN")]["own_cost_cents"] == 30000 and groups[("Taller", "MXN")]["projects"] == ["Lámpara"]
    assert groups[("Taller", "USD")]["projects"] == ["Encargo"]
    assert any(line.startswith("El grupo Taller costó $550.00 MXN entre Lámpara y lo general del grupo")
               for line in rep["text"]["patterns"]), rep["text"]["patterns"]
