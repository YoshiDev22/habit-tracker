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
