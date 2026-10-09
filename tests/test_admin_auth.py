"""El panel de administración (1.27): solo entra un JWT de Cloudflare Access válido de
un correo de ADMIN_EMAILS, y la app pública no tiene ninguna de sus rutas."""
import base64
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt

ROOT = Path(__file__).resolve().parents[1]
TEAM = "equipo-prueba"
AUD = "aud-de-la-app-de-prueba"
ISSUER = f"https://{TEAM}.cloudflareaccess.com"
ADMIN = "yoshi@test.com"


def rsa_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


SIGNING = rsa_pem()
OTHER = rsa_pem()     # otra llave: su firma no vale aunque use el mismo kid


def public_jwk(pem, kid):
    key = jwk.construct(pem, "RS256").public_key().to_dict()
    return {**key, "kid": kid, "alg": "RS256", "use": "sig"}


JWKS = {"keys": [public_jwk(SIGNING, "k1")]}


def token(email=ADMIN, kid="k1", pem=SIGNING, aud=AUD, iss=ISSUER, exp_in=300, **extra):
    claims = {"email": email, "aud": aud, "iss": iss, "iat": int(time.time()), **extra}
    if exp_in is not None:
        claims["exp"] = int(time.time()) + exp_in
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", f"{ADMIN.upper()}, otra-admin@test.com")
    monkeypatch.setenv("ADMIN_ACCESS_TEAM", TEAM)
    monkeypatch.setenv("ADMIN_ACCESS_AUD", AUD)
    from backend import admin_main
    admin_main = importlib.reload(admin_main)
    fetched = []

    def fetch(url):
        fetched.append(url)
        return JWKS

    monkeypatch.setattr(admin_main.ACCESS_KEYS, "fetch", fetch)
    client = TestClient(admin_main.app)

    def get(path="/api/me", jwt_token=None, **headers):
        if jwt_token is not None:
            headers["Cf-Access-Jwt-Assertion"] = jwt_token
        return client.get(path, headers=headers)

    get.fetched = fetched
    return get


def test_a_valid_access_token_gets_in(admin):
    r = admin(jwt_token=token())
    assert r.status_code == 200 and r.json() == {"email": ADMIN}
    assert admin.fetched == [f"{ISSUER}/cdn-cgi/access/certs"]
    # Mayúsculas en el correo: el mismo administrador
    assert admin(jwt_token=token(email="Yoshi@Test.com")).status_code == 200
    assert len(admin.fetched) == 1          # las llaves quedan en caché


@pytest.mark.parametrize("case", [
    "no header", "garbage", "other key", "expired", "no exp", "other app (aud)", "other team (iss)",
    "not an admin", "no email", "unknown kid", "alg none", "alg HS256 with the public key",
])
def test_everything_else_is_403(admin, case):
    if case == "no header":
        r = admin()
    elif case == "garbage":
        r = admin(jwt_token="no.es.un.jwt")
    elif case == "other key":
        r = admin(jwt_token=token(pem=OTHER))
    elif case == "expired":
        r = admin(jwt_token=token(exp_in=-10))
    elif case == "no exp":
        r = admin(jwt_token=token(exp_in=None))
    elif case == "other app (aud)":
        r = admin(jwt_token=token(aud="aud-de-otra-app"))
    elif case == "other team (iss)":
        r = admin(jwt_token=token(iss="https://otro-equipo.cloudflareaccess.com"))
    elif case == "not an admin":
        r = admin(jwt_token=token(email="usuario@test.com"))
    elif case == "no email":
        r = admin(jwt_token=token(email=""))
    elif case == "unknown kid":
        r = admin(jwt_token=token(kid="k-desconocida"))
    elif case == "alg none":
        def b64(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        r = admin(jwt_token=f"{b64({'alg': 'none', 'kid': 'k1'})}.{b64({'email': ADMIN, 'aud': AUD, 'iss': ISSUER, 'exp': int(time.time()) + 300})}.")
    else:
        # El clásico: firmar con HS256 usando la llave pública como secreto (a mano: jose
        # se niega a firmarlo, pero un atacante no usa jose)
        import hashlib
        import hmac

        def b64(raw):
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        public_pem = jwk.construct(SIGNING, "RS256").public_key().to_pem()
        head = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode())
        body = b64(json.dumps({"email": ADMIN, "aud": AUD, "iss": ISSUER, "exp": int(time.time()) + 300}).encode())
        sig = b64(hmac.new(public_pem, f"{head}.{body}".encode(), hashlib.sha256).digest())
        r = admin(jwt_token=f"{head}.{body}.{sig}")
    assert r.status_code == 403 and r.json() == {"detail": "Acceso denegado"}, (case, r.status_code, r.text)


def test_an_unknown_kid_refetches_at_most_once_a_minute(admin):
    for _ in range(5):
        assert admin(jwt_token=token(kid="k-desconocida")).status_code == 403
    assert len(admin.fetched) == 1


def test_security_headers(admin):
    r = admin(jwt_token=token())
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "'unsafe-inline'" not in csp
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Content-Type-Options"] == "nosniff"
    # También en una respuesta de error
    assert admin().headers["Content-Security-Policy"] == csp
    # Sin documentación de la API
    assert admin("/docs").status_code == 404 and admin("/openapi.json").status_code == 404


def test_the_public_app_has_no_admin_route(api):
    from backend import admin_main, main
    public = {(m, r.path) for r in main.app.routes for m in getattr(r, "methods", ())}
    admin_routes = {(m, r.path) for r in admin_main.app.routes for m in getattr(r, "methods", ())
                    if r.path.startswith("/api")}
    assert admin_routes and not (admin_routes & public)
    assert api.call("GET", "/api/me")[0] == 404
    # Y la app pública, en un proceso limpio, no carga nada del panel
    loaded = subprocess.run([sys.executable, "-c", "import sys, backend.main; "
                             "print(sorted(m for m in sys.modules if m.startswith('backend.admin')))"],
                            cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                            capture_output=True, text=True, encoding="utf-8")
    assert loaded.returncode == 0 and loaded.stdout.strip() == "[]", (loaded.stdout, loaded.stderr)


@pytest.mark.parametrize("missing", ["ADMIN_EMAILS", "ADMIN_ACCESS_TEAM", "ADMIN_ACCESS_AUD"])
def test_it_refuses_to_start_without_its_config(missing):
    env = {**os.environ, "ADMIN_EMAILS": ADMIN, "ADMIN_ACCESS_TEAM": TEAM, "ADMIN_ACCESS_AUD": AUD,
           "PYTHONIOENCODING": "utf-8"}
    env[missing] = ""
    started = subprocess.run([sys.executable, "-c", "import backend.admin_main"], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
    assert started.returncode != 0 and missing in started.stderr
