"""
Pruebas de navegador: `pytest -m ui` (necesitan Edge o Chrome).

Cada prueba levanta su propio servidor (uvicorn) sobre la base de la 1.9 de
tests/fixtures, migrada con el scripts/migrate.py real: la misma situación que un
deploy, con datos conocidos. Las fechas de esos datos se corren a "ayer", así las
pruebas no dependen del día en que se corran (las que miran "esta semana" calculan lo
esperado con la API: un lunes, "ayer" es de la semana anterior).
"""
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SQL = ROOT / "tests" / "fixtures" / "db_v1_9.sql"
FIXTURE_ORIGINAL_DAY = date(2026, 9, 22)   # el día de los datos de db_v1_9.sql
TMP = Path(tempfile.mkdtemp(prefix="habit-ui-"))   # bases, logs y perfiles del navegador
os.environ["HABIT_UI_TMP"] = str(TMP)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
os.environ["HABIT_UI_BASE"] = f"http://127.0.0.1:{PORT}"
TODAY = date.today()
FIXTURE_DAY = TODAY - timedelta(days=1)
os.environ["HABIT_UI_FIXTURE_DAY"] = FIXTURE_DAY.isoformat()


def pytest_collection_modifyitems(config, items):
    here = Path(__file__).resolve().parent
    for item in items:
        if here in Path(item.fspath).resolve().parents:
            item.add_marker(pytest.mark.ui)


def _prepare_db(db: Path):
    """La base de la 1.9, con sus fechas corridas a FIXTURE_DAY, y migrada."""
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    conn.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    shift = f"'{(FIXTURE_DAY - FIXTURE_ORIGINAL_DAY).days:+d} days'"
    ts = f"strftime('%Y-%m-%d %H:%M:%f', {{c}}, {shift})"
    for table, dates, stamps in [
        ("pomodoro_sessions", ["session_date", "created_at"], ["started_at", "ended_at"]),
        ("tasks", ["completed_at", "created_at"], []),
        ("projects", ["created_at"], []),
        ("habit_entries", ["entry_date"], []),
    ]:
        for c in dates:
            conn.execute(f"update {table} set {c} = date({c}, {shift}) where {c} is not null")
        for c in stamps:
            conn.execute(f"update {table} set {c} = {ts.format(c=c)} where {c} is not null")
    conn.commit()
    conn.close()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    migrated = subprocess.run([sys.executable, str(ROOT / "scripts" / "migrate.py")], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8")
    assert migrated.returncode == 0, migrated.stderr


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def ui_server(request):
    """Un servidor nuevo para cada prueba de navegador."""
    from cdp import find_browser
    if not find_browser():
        pytest.skip("No hay Edge ni Chrome (o define HABIT_UI_BROWSER con su ruta)")

    db = TMP / f"{request.node.name}.db"
    _prepare_db(db)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SECRET_KEY": "test-secret-key-not-for-production", "PYTHONIOENCODING": "utf-8"}
    log = open(TMP / f"{request.node.name}.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = os.environ["HABIT_UI_BASE"]
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError((TMP / f"{request.node.name}.log").read_text(encoding="utf-8"))
            time.sleep(0.2)
    import api
    api.TOKEN = None
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    server_log = (TMP / f"{request.node.name}.log").read_text(encoding="utf-8")
    assert "Traceback" not in server_log, f"server error during the test:\n{server_log[-3000:]}"
