"""Módulos por cuenta: Hábitos (activo por defecto) y el plan maker (con acceso)."""
import os
import subprocess
import sys
from datetime import date

from conftest import DB_PATH, ROOT


def grant(*args):
    """Corre scripts/grant_module.py de verdad, contra la base de las pruebas."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "grant_module.py"), *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")


def test_defaults_come_with_the_user(api):
    _, created = api.call("POST", "/api/auth/register", {"email": "nuevo@test.com", "password": "secret123"}, expect=200)
    expected = {"habits": {"enabled": True, "allowed": True}, "maker": {"enabled": False, "allowed": False}, "ai": {"enabled": False, "allowed": False}}
    assert created["modules"] == expected, "register already returns them: the app uses it as currentUser"
    api.login("nuevo@test.com")
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"] == expected
    _, me = api.call("PATCH", "/api/auth/me", {"display_name": "Yo"}, expect=200)
    assert me["modules"] == expected, "a profile edit returns them too"


def test_turn_habits_off_and_on(api):
    api.login("habitos@test.com")
    today = date.today().isoformat()
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "gym", "done": True}, expect=200)

    _, me = api.call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)
    assert me["modules"]["habits"] == {"enabled": False, "allowed": True}
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"]["habits"]["enabled"] is False
    # Apagado no es borrado: el hábito y su día siguen ahí
    _, defs = api.call("GET", "/api/habits/definitions", expect=200)
    assert "gym" in str(defs)
    _, days = api.call("GET", f"/api/habits?today={today}", expect=200)
    assert "gym" in str(days)
    _, me = api.call("PUT", "/api/auth/me/modules/habits", {"enabled": True}, expect=200)
    assert me["modules"]["habits"] == {"enabled": True, "allowed": True}
    # Repetir no crea otra fila (restricción única por usuario y módulo)
    api.call("PUT", "/api/auth/me/modules/habits", {"enabled": True}, expect=200)


def test_maker_needs_access(api):
    api.login("maker@test.com")
    s, body = api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True})
    assert s == 403 and "acceso" in body["detail"]
    # Apagar lo que no se tiene no hace daño
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": False}, expect=200)

    result = grant("--email", "maker@test.com", "--module", "maker")
    assert result.returncode == 0, result.stderr
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"]["maker"] == {"enabled": False, "allowed": True}, "access alone does not turn it on"
    _, me = api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    assert me["modules"]["maker"] == {"enabled": True, "allowed": True}

    # Quitar el acceso lo apaga; devolverlo lo deja como el usuario lo tenía
    assert grant("--email", "maker@test.com", "--module", "maker", "--revoke").returncode == 0
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"]["maker"] == {"enabled": False, "allowed": False}
    assert api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True})[0] == 403
    assert grant("--email", "maker@test.com", "--module", "maker").returncode == 0
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"]["maker"] == {"enabled": True, "allowed": True}

    listed = grant("--list")
    assert listed.returncode == 0 and "maker@test.com" in listed.stdout


def test_access_is_per_account(api):
    api.login("con@test.com")
    other = api.as_user("sin@test.com")
    assert grant("--email", "con@test.com", "--module", "maker").returncode == 0
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": True}, expect=200)
    other.call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)
    _, mine = api.call("GET", "/api/auth/me", expect=200)
    _, theirs = other.call("GET", "/api/auth/me", expect=200)
    assert mine["modules"] == {"habits": {"enabled": True, "allowed": True}, "maker": {"enabled": True, "allowed": True}, "ai": {"enabled": False, "allowed": False}}
    assert theirs["modules"] == {"habits": {"enabled": False, "allowed": True}, "maker": {"enabled": False, "allowed": False}, "ai": {"enabled": False, "allowed": False}}


def test_grant_script_errors(api):
    api.login("existe@test.com")
    result = grant("--email", "nadie@test.com", "--module", "maker")
    assert result.returncode != 0 and "No account" in result.stderr
    result = grant("--email", "existe@test.com", "--module", "inventado")
    assert result.returncode != 0, "only the modules of backend/modules.py"


def test_unknown_module_and_bad_body(api):
    api.login("raro@test.com")
    assert api.call("PUT", "/api/auth/me/modules/inventado", {"enabled": True})[0] == 404
    assert api.call("PUT", "/api/auth/me/modules/habits", {})[0] == 422
    assert api.call("PUT", "/api/auth/me/modules/habits", {"enabled": "tal vez"})[0] == 422
    api.token = None
    assert api.call("PUT", "/api/auth/me/modules/habits", {"enabled": False})[0] == 401
