"""Cliente urllib contra el servidor de la prueba (BASE lo fija tests/ui/conftest.py)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ["HABIT_UI_BASE"]   # tests/ui/conftest.py picks a free port
TOKEN = None
PASSWORD = "secret123"


def call(method, path, body=None, form=None, expect=None):
    headers = {}
    data = None
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    payload = json.loads(raw) if raw else None
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} -> {status} (expected {expect}): {payload}")
    return status, payload


def login(email, password=PASSWORD):
    global TOKEN
    TOKEN = None
    call("POST", "/api/auth/register", {"email": email, "password": password})
    _, tok = call("POST", "/api/auth/login", form={"username": email, "password": password}, expect=200)
    TOKEN = tok["access_token"]
