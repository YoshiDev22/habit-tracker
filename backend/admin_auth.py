"""
Quién entra al panel de administración (1.27, épica 32). Solo lo usa
backend/admin_main.py: la app pública no importa este módulo.

Al panel se llega por un Cloudflare Tunnel protegido con Cloudflare Access, que
manda en cada petición su JWT en la cabecera Cf-Access-Jwt-Assertion. Aquí se
vuelve a comprobar todo, por si Access o el tunnel quedaran mal configurados:

- la firma (RS256) con las llaves públicas del equipo de Access, en caché;
- el emisor (https://<equipo>.cloudflareaccess.com) y la audiencia (el AUD de
  la aplicación de Access: sin él, un JWT de otra aplicación del mismo equipo
  también valdría);
- que no haya vencido, y que su correo esté en ADMIN_EMAILS.

Cualquier fallo es 403. Sin ADMIN_EMAILS, ADMIN_ACCESS_TEAM o ADMIN_ACCESS_AUD
el proceso de admin no arranca (como sin SECRET_KEY).
"""
import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Optional

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt

HEADER = "Cf-Access-Jwt-Assertion"
CERTS_TTL = 3600          # las llaves se vuelven a pedir cada hora
CERTS_RETRY = 60          # una llave desconocida fuerza otra petición, como mucho cada minuto
# Modo de desarrollo (scripts/admin_dev.py): el panel confía en las llaves de un archivo
# local en vez de las de Access. Solo con este equipo, que nunca es uno real, y este
# equipo solo con el archivo: sin él, se pedirían llaves a dev-local.cloudflareaccess.com
DEV_TEAM = "dev-local"


@dataclass(frozen=True)
class AdminConfig:
    emails: FrozenSet[str]
    team: str             # el subdominio de <equipo>.cloudflareaccess.com
    audience: str         # el AUD de la aplicación de Access
    dev_keys_file: Optional[str] = None   # solo en desarrollo (DEV_TEAM)

    @property
    def issuer(self) -> str:
        return f"https://{self.team}.cloudflareaccess.com"

    @property
    def certs_url(self) -> str:
        return f"{self.issuer}/cdn-cgi/access/certs"


def load_config() -> AdminConfig:
    """Lee la configuración del .env; sin ella, el panel no arranca."""
    emails = frozenset(e.strip().lower() for e in (os.getenv("ADMIN_EMAILS") or "").split(",") if e.strip())
    team = (os.getenv("ADMIN_ACCESS_TEAM") or "").strip().lower()
    team = team.removeprefix("https://").removesuffix("/").removesuffix(".cloudflareaccess.com")
    audience = (os.getenv("ADMIN_ACCESS_AUD") or "").strip()
    missing = [name for name, value in (("ADMIN_EMAILS", emails), ("ADMIN_ACCESS_TEAM", team),
                                        ("ADMIN_ACCESS_AUD", audience)) if not value]
    if missing:
        raise RuntimeError(f"El panel de administración necesita {', '.join(missing)} en backend/.env")
    if not team.replace("-", "").isalnum():
        raise RuntimeError("ADMIN_ACCESS_TEAM debe ser el nombre del equipo de Access (sin puntos ni barras)")
    dev_keys_file = (os.getenv("ADMIN_DEV_KEYS_FILE") or "").strip() or None
    if dev_keys_file and team != DEV_TEAM:
        raise RuntimeError(f"ADMIN_DEV_KEYS_FILE es solo para desarrollo, con ADMIN_ACCESS_TEAM={DEV_TEAM}")
    if team == DEV_TEAM and not dev_keys_file:
        raise RuntimeError(f"ADMIN_ACCESS_TEAM={DEV_TEAM} es solo para desarrollo (scripts/admin_dev.py)")
    return AdminConfig(emails=emails, team=team, audience=audience, dev_keys_file=dev_keys_file)


def fetch_certs(url: str) -> Dict:
    """Las llaves públicas del equipo de Access (un JWKS)."""
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def read_keys_file(path: str) -> Dict:
    """Las llaves del modo de desarrollo, de un archivo local."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def access_keys(config: AdminConfig) -> "AccessKeys":
    if config.dev_keys_file:
        return AccessKeys(config.dev_keys_file, fetch=read_keys_file)
    return AccessKeys(config.certs_url)


class AccessKeys:
    """Caché de las llaves por `kid`. Las pruebas reemplazan `fetch`."""

    def __init__(self, url: str, fetch: Callable[[str], Dict] = fetch_certs):
        self.url = url
        self.fetch = fetch
        self._keys: Dict[str, Dict] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        jwks = self.fetch(self.url)
        self._keys = {k["kid"]: k for k in jwks.get("keys", []) if k.get("kid")}
        self._fetched_at = time.monotonic()

    def get(self, kid: str) -> Optional[Dict]:
        with self._lock:
            age = time.monotonic() - self._fetched_at
            stale = not self._keys or age > CERTS_TTL
            unknown = kid not in self._keys and age > CERTS_RETRY
            if stale or unknown:
                try:
                    self._refresh()
                except Exception:
                    pass   # sin red: se usan las que hay (o ninguna: 403)
            return self._keys.get(kid)


def _deny() -> HTTPException:
    # Siempre el mismo motivo: no dice qué parte falló
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")


def verify(token: Optional[str], config: AdminConfig, keys: AccessKeys) -> str:
    """El correo del administrador, o 403."""
    if not token:
        raise _deny()
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise _deny()
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise _deny()
    key = keys.get(header["kid"])
    if key is None:
        raise _deny()
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=config.audience, issuer=config.issuer,
                            options={"require_exp": True, "require_aud": True, "require_iss": True})
    except JWTError:
        raise _deny()
    email = str(claims.get("email") or "").strip().lower()
    if not email or email not in config.emails:
        raise _deny()
    return email


def admin_dependency(config: AdminConfig, keys: AccessKeys):
    """La dependencia de FastAPI que pide un administrador válido."""
    def require_admin(request: Request) -> str:
        return verify(request.headers.get(HEADER), config, keys)
    return require_admin
