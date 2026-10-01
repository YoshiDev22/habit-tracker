"""Cliente urllib contra el servidor de la prueba (BASE lo fija tests/ui/conftest.py)."""
import asyncio
import json
import os
import time
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


async def wait_api(path, ok, timeout=8.0):
    """GET `path` hasta que ok(body) se cumpla (o se acabe el tiempo) y devuelve
    el último body. Para lo que un clic guarda en el backend: con la máquina
    ocupada, una espera fija a veces no alcanzaba."""
    deadline = time.monotonic() + timeout
    while True:
        _, body = call("GET", path, expect=200)
        if ok(body) or time.monotonic() > deadline:
            return body
        await asyncio.sleep(0.2)


def login(email, password=PASSWORD):
    global TOKEN
    TOKEN = None
    call("POST", "/api/auth/register", {"email": email, "password": password})
    _, tok = call("POST", "/api/auth/login", form={"username": email, "password": password}, expect=200)
    TOKEN = tok["access_token"]
