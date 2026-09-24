"""
Fixtures de las pruebas de API.

La app se importa una sola vez contra una base SQLite temporal (nunca la de
desarrollo ni su .env): DATABASE_URL y SECRET_KEY se fijan ANTES de importar
backend.main, y load_dotenv() no pisa variables que ya existen.

Cada prueba empieza con la base vacía (fixture `fresh_db`, automática). Las que
simulan un deploy piden `old_db`: la base de la 1.9 migrada con el migrate.py real.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TMP = Path(tempfile.mkdtemp(prefix="habit-tests-"))
DB_PATH = TMP / "test.db"

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from backend.database import create_db_and_tables, engine  # noqa: E402
from backend.main import app  # noqa: E402
import bcrypt  # noqa: E402

# Solo en las pruebas: bcrypt con costo 4 en vez de 12. Cada registro costaba
# ~0.3 s y las pruebas registran usuarios todo el tiempo. checkpw acepta
# cualquier costo, así que los hashes de la base de la 1.9 siguen valiendo.
_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _gensalt(rounds=4, prefix=prefix)

from sqlalchemy import event  # noqa: E402


@event.listens_for(engine, "connect")
def _fast_sqlite(dbapi_connection, _record):
    # Base temporal de pruebas: no hace falta esperar a que cada escritura
    # llegue al disco (en Windows es lo que más tarda)
    dbapi_connection.execute("PRAGMA synchronous=OFF")
    dbapi_connection.execute("PRAGMA journal_mode=MEMORY")

PASSWORD = "secret123"
H = 3600


def load_sql_fixture(path: Path, name: str):
    """Crea en `path` la base descrita por fixtures/<name>.sql."""
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / f"{name}.sql").read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def run_migrate(db_path: Path) -> subprocess.CompletedProcess:
    """Corre scripts/migrate.py de verdad, como en un deploy."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "migrate.py")],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


class Api:
    """Cliente con el mismo estilo que las baterías originales:
    call(método, ruta, body) -> (status, json), y expect= para exigir un código."""

    def __init__(self, client: TestClient):
        self.client = client
        self.token = None

    def call(self, method, path, body=None, form=None, expect=None):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        kwargs = {"headers": headers}
        if form is not None:
            kwargs["data"] = form
        elif body is not None:
            kwargs["json"] = body
        response = self.client.request(method, path, **kwargs)
        payload = response.json() if response.content else None
        if expect is not None:
            assert response.status_code == expect, f"{method} {path} -> {response.status_code} (expected {expect}): {payload}"
        return response.status_code, payload

    def login(self, email, password=PASSWORD):
        """Registra (si hace falta) e inicia sesión; deja el token puesto."""
        self.token = None
        self.call("POST", "/api/auth/register", {"email": email, "password": password})
        _, tok = self.call("POST", "/api/auth/login", form={"username": email, "password": password}, expect=200)
        self.token = tok["access_token"]
        return self

    def as_user(self, email):
        """Otro cliente, ya con sesión de `email` (para pruebas de aislamiento)."""
        return Api(self.client).login(email)


@pytest.fixture(autouse=True)
def fresh_db():
    """Base vacía para cada prueba."""
    engine.dispose()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client):
    return Api(client)


@pytest.fixture
def old_db():
    """La base de una cuenta de la 1.9 (tests/fixtures/db_v1_9.sql), migrada con el
    migrate.py real y con las tablas nuevas creadas: lo mismo que ve la app tras un
    deploy (migrar y reiniciar)."""
    engine.dispose()
    load_sql_fixture(DB_PATH, "db_v1_9")
    result = run_migrate(DB_PATH)
    assert result.returncode == 0, result.stderr
    create_db_and_tables()
    yield result


def utc_now():
    """UTC naive, como guarda la app started_at / ended_at."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def log_time(api, project_id, task_id, seconds, day=None, source="manual", mode="focus", note=None, start=None):
    """Registra una sesión de `seconds` que termina ahora (o empieza en `start`)."""
    day = day or date.today()
    start = start or (utc_now() - timedelta(seconds=seconds))
    _, s = api.call("POST", "/api/pomodoro", {
        "project_id": project_id, "task_id": task_id, "session_date": day.isoformat(),
        "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=seconds)).isoformat(),
        "duration_seconds": seconds, "planned_seconds": seconds, "mode": mode,
        "was_completed": True, "source": source, "note": note,
    }, expect=201)
    return s


@pytest.fixture
def seeded(api):
    """Los datos típicos de las baterías: 'Habit Tracker' con 5 tareas (4 hechas,
    417 min en total), un proyecto archivado, y otro usuario con su propia tarea.
    Devuelve el cliente de yoshi@test.com y los ids útiles."""
    other = api.as_user("otro@test.com")
    _, ajeno = other.call("POST", "/api/projects", {"name": "Ajeno"}, expect=201)
    _, ajena = other.call("POST", "/api/tasks", {"project_id": ajeno["id"], "title": "Tarea ajena"}, expect=201)

    api.login("yoshi@test.com")
    api.call("PATCH", "/api/auth/me", {"display_name": "Yoshio"}, expect=200)
    _, p = api.call("POST", "/api/projects", {"name": "Habit Tracker", "color": "#3498db"}, expect=201)
    _, arch = api.call("POST", "/api/projects", {"name": "Archivado"}, expect=201)
    api.call("PATCH", f"/api/projects/{arch['id']}", {"is_active": False}, expect=200)
    tasks = {}
    for title, done, secs in [
        ("Corrección de Pomodoros", True, 4 * H),
        ("Confirmación de cambios datos y cancelación pomodoro", True, 25 * 60),
        ("Confirmación de guardado de datos en hábitos", True, 35 * 60),
        ("modificación de tiempo de pomodoros", True, 117 * 60),
        ("Revisión de idea para cambiar a kanban", False, 0),
    ]:
        _, t = api.call("POST", "/api/tasks", {"project_id": p["id"], "title": title}, expect=201)
        if done:
            api.call("PATCH", f"/api/tasks/{t['id']}?today={date.today()}", {"is_done": True}, expect=200)
        if secs:
            log_time(api, p["id"], t["id"], secs)
        tasks[title] = t
    return {"api": api, "other": other, "project": p, "archived": arch, "tasks": tasks,
            "other_task": ajena, "other_project": ajeno}
