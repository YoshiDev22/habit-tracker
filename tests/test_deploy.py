"""
El deploy de verdad: una base de la 1.9 (antes de los tableros), scripts/migrate.py
y el arranque de la versión actual. Nada de los datos viejos se pierde ni cambia.
"""
import os
import sqlite3
import subprocess
import sys

# Todo lo de conftest se importa aquí arriba, al recolectar: dentro de una prueba,
# `conftest` ya puede ser el de tests/ui (el nombre es el mismo).
from conftest import DB_PATH, ROOT, TMP, Api, app, create_db_and_tables, engine, load_sql_fixture, run_migrate

H = 3600


def test_the_app_refuses_to_start_without_migrating():
    db = TMP / "unmigrated.db"
    load_sql_fixture(db, "db_v1_9")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    started = subprocess.run([sys.executable, "-c", "import backend.main"], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert started.returncode != 0
    assert "scripts/migrate.py" in started.stderr and "tasks.column_id" in started.stderr

    first = run_migrate(db)
    assert first.returncode == 0, first.stderr
    assert "tasks.column_id" in first.stdout and "users.pomodoro_focus_seconds" in first.stdout
    assert "pomodoro_sessions.idempotency_key" in first.stdout and "tasks.estimate_minutes" in first.stdout
    assert "pomodoro_sessions.needs_review" in first.stdout
    assert "index uq_pomodoro_sessions_user_key" in first.stdout
    again = run_migrate(db)
    assert again.returncode == 0 and "nothing, already up to date" in again.stdout

    started = subprocess.run([sys.executable, "-c", "import backend.main"], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert started.returncode == 0, started.stderr

    # Un índice único que falta también la frena: sin él, una sesión de tiempo
    # reenviada a la vez se guardaría dos veces
    conn = sqlite3.connect(db)
    conn.execute("DROP INDEX uq_pomodoro_sessions_user_key")
    conn.commit()
    conn.close()
    started = subprocess.run([sys.executable, "-c", "import backend.main"], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert started.returncode != 0 and "uq_pomodoro_sessions_user_key" in started.stderr
    assert run_migrate(db).returncode == 0


def test_old_auto_closed_sessions_are_marked_for_review_once():
    """Las sesiones de antes que se cerraron solas a las 8 h y nadie corrigió quedan
    por confirmar al añadir needs_review. Solo esa vez: confirmar una y volver a
    migrar no la marca de nuevo."""
    db = TMP / "review.db"
    load_sql_fixture(db, "db_v1_9")
    conn = sqlite3.connect(db)
    note = "Cerrado automáticamente a las 8 h"
    rows = [(901, 28800, note), (902, 7200, note), (903, 28800, None)]   # solo la 901
    for sid, seconds, n in rows:
        conn.execute("INSERT INTO pomodoro_sessions VALUES(?,1,1,1,'2026-09-20','2026-09-20 08:00:00',"
                     "'2026-09-20 16:00:00',?,0,'focus',1,?,'timer','2026-09-20')", (sid, seconds, n))
    conn.commit()
    conn.close()

    first = run_migrate(db)
    assert first.returncode == 0, first.stderr
    assert "pomodoro_sessions.needs_review" in first.stdout and "Sessions to review" in first.stdout
    conn = sqlite3.connect(db)
    marked = {r[0] for r in conn.execute("SELECT id FROM pomodoro_sessions WHERE needs_review = 1")}
    assert marked == {901}
    assert conn.execute("SELECT COUNT(*) FROM pomodoro_sessions WHERE needs_review IS NULL").fetchone()[0] == 0
    conn.execute("UPDATE pomodoro_sessions SET needs_review = 0 WHERE id = 901")   # el usuario la confirma
    conn.commit()
    conn.close()

    assert run_migrate(db).returncode == 0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT needs_review FROM pomodoro_sessions WHERE id = 901").fetchone()[0] == 0
    conn.close()


def test_old_data_survives_and_is_placed_on_a_board(old_db, api):
    api.login("yoshi@test.com")
    # Lo que ya leía la app antes de los tableros no cambia
    _, summ = api.call("GET", "/api/projects/summary", expect=200)
    ht = next(x for x in summ["summaries"] if x["name"] == "Habit Tracker")
    assert (ht["task_done"], ht["task_total"], ht["total_seconds"]) == (4, 5, 417 * 60)

    # El primer acceso crea "Mi tablero" y coloca cada tarea según esté hecha o no
    _, bl = api.call("GET", "/api/boards", expect=200)
    assert bl["total"] == 1 and bl["boards"][0]["name"] == "Mi tablero"
    board = bl["boards"][0]
    assert [c["name"] for c in board["columns"]] == ["Por hacer", "Haciendo", "Hecho"]
    assert [c["category"] for c in board["columns"]] == ["todo", "doing", "done"]
    col = {c["name"]: c["id"] for c in board["columns"]}
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert len(tl["tasks"]) == 5
    for t in tl["tasks"]:
        assert t["column_id"] == (col["Hecho"] if t["is_done"] else col["Por hacer"]), t
        assert t["board_id"] == board["id"]
        assert t["estimate_minutes"] is None, "no old task gets an invented estimate"

    # El archivado sigue archivado, y aparece "Sin asignar" vacío
    _, allp = api.call("GET", "/api/projects?include_inactive=true", expect=200)
    assert next(p for p in allp["projects"] if p["name"] == "Archivado")["is_active"] is False
    system = [p for p in allp["projects"] if p["is_system"]]
    assert len(system) == 1 and system[0]["name"] == "Sin asignar"

    # Idempotente: volver a pedir no crea más tableros
    assert api.call("GET", "/api/boards", expect=200)[1]["total"] == 1

    # Las columnas nuevas de users valen NULL = valores por defecto
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["pomodoro_focus_seconds"] is None
    # Y sin filas en user_modules (tabla nueva), cada módulo como viene por defecto
    assert me["modules"] == {"habits": {"enabled": True, "allowed": True},
                             "maker": {"enabled": False, "allowed": False}, "ai": {"enabled": False, "allowed": False}}


def test_a_preexisting_sin_asignar_project_is_adopted():
    # Con el código viejo alguien pudo crear (y archivar) un proyecto llamado así
    engine.dispose()
    load_sql_fixture(DB_PATH, "db_v1_9")
    conn = sqlite3.connect(DB_PATH)
    uid = conn.execute("select id from users where email='otro@test.com'").fetchone()[0]
    conn.execute("insert into projects(user_id,name,\"order\",is_active,created_at) values(?,?,0,0,'2026-09-01')",
                 (uid, "Sin asignar"))
    conn.commit()
    conn.close()
    assert run_migrate(DB_PATH).returncode == 0
    create_db_and_tables()

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        other = Api(c).login("otro@test.com")
        _, pl = other.call("GET", "/api/projects?include_inactive=true", expect=200)
        named = [p for p in pl["projects"] if p["name"] == "Sin asignar"]
        assert len(named) == 1 and named[0]["is_system"] and named[0]["is_active"], named
