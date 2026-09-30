"""Cuenta: registro, sesión, perfil y duraciones del pomodoro."""
import time
from datetime import timedelta

from jose import jwt

from backend.auth import create_access_token


def test_register_login_and_profile(api):
    api.login("nuevo@test.com")
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["email"] == "nuevo@test.com"
    assert api.call("POST", "/api/auth/login", form={"username": "nuevo@test.com", "password": "mala"})[0] == 401
    _, me = api.call("PATCH", "/api/auth/me", {"display_name": "  Yoshio  ", "first_name": ""}, expect=200)
    assert me["display_name"] == "Yoshio" and me["first_name"] is None
    assert api.call("PATCH", "/api/auth/me", {"rest_days": [7]})[0] == 422


def test_token_expiry_is_utc():
    token = create_access_token({"sub": "a"}, timedelta(minutes=60))
    assert abs(jwt.get_unverified_claims(token)["exp"] - time.time() - 3600) < 5


def test_pomodoro_durations(api):
    api.login("settings@test.com")
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["pomodoro_focus_seconds"] is None                      # NULL = 25 min
    _, me = api.call("PATCH", "/api/auth/me", {"pomodoro_focus_seconds": 3000, "pomodoro_long_break_seconds": 1800}, expect=200)
    assert (me["pomodoro_focus_seconds"], me["pomodoro_short_break_seconds"], me["pomodoro_long_break_seconds"]) == (3000, None, 1800)
    assert api.call("PATCH", "/api/auth/me", {"pomodoro_focus_seconds": 0})[0] == 422
    assert api.call("PATCH", "/api/auth/me", {"pomodoro_short_break_seconds": 5 * 3600})[0] == 422
    _, me = api.call("PATCH", "/api/auth/me", {"display_name": "Otro nombre"}, expect=200)
    assert me["pomodoro_focus_seconds"] == 3000, "a profile edit without them keeps them"
    _, me = api.call("PATCH", "/api/auth/me", {"pomodoro_focus_seconds": None}, expect=200)
    assert me["pomodoro_focus_seconds"] is None and me["pomodoro_long_break_seconds"] == 1800


def test_failed_logins_are_limited_per_ip(api):
    api.login("fuerza@test.com")
    bad = {"username": "fuerza@test.com", "password": "mala"}
    good = {"username": "fuerza@test.com", "password": "secret123"}
    # Los logins buenos no gastan intentos
    for _ in range(12):
        api.call("POST", "/api/auth/login", form=good, expect=200)
    for _ in range(10):
        api.call("POST", "/api/auth/login", form=bad, expect=401)
    # Agotados: el siguiente se frena antes de mirar la contraseña, aunque sea la buena
    response = api.client.post("/api/auth/login", data=good)
    assert response.status_code == 429
    assert "Demasiados intentos" in response.json()["detail"]
    assert 0 < int(response.headers["Retry-After"]) <= 15 * 60


def test_sliding_window_forgets_old_attempts(monkeypatch):
    from backend import ratelimit

    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    window = ratelimit.SlidingWindow(limit=2, window=60)
    window.hit("ip")
    now[0] += 30
    window.hit("ip")
    assert window.retry_after("ip") == 31          # el primero caduca en 30 s
    assert window.retry_after("otra-ip") is None
    now[0] += 31
    assert window.retry_after("ip") is None


def test_registrations_are_limited_per_ip(api):
    url = "/api/auth/register"
    for i in range(5):
        api.call("POST", url, {"email": f"cuenta{i}@test.com", "password": "secret123"}, expect=200)
    # La sexta cuenta desde la misma IP en menos de una hora se frena
    status, body = api.call("POST", url, {"email": "cuenta5@test.com", "password": "secret123"})
    assert status == 429 and "demasiadas cuentas" in body["detail"]
    # Las cuentas creadas siguen entrando
    api.call("POST", "/api/auth/login", form={"username": "cuenta0@test.com", "password": "secret123"}, expect=200)


def test_a_repeated_email_does_not_spend_a_registration(api):
    url = "/api/auth/register"
    api.call("POST", url, {"email": "repetida@test.com", "password": "secret123"}, expect=200)
    for _ in range(6):
        api.call("POST", url, {"email": "repetida@test.com", "password": "secret123"}, expect=400)
    for i in range(4):
        api.call("POST", url, {"email": f"otra{i}@test.com", "password": "secret123"}, expect=200)


def test_registration_can_be_closed(api, monkeypatch):
    api.login("antes@test.com")
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    status, body = api.call("POST", "/api/auth/register", {"email": "nueva@test.com", "password": "secret123"})
    assert status == 403 and "cerrado" in body["detail"]
    # Quien ya tiene cuenta sigue entrando
    api.call("POST", "/api/auth/login", form={"username": "antes@test.com", "password": "secret123"}, expect=200)
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    api.call("POST", "/api/auth/register", {"email": "nueva@test.com", "password": "secret123"}, expect=200)
