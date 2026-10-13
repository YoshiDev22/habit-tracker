"""
El panel de administración (1.27, épica 32): un proceso aparte de la app pública.

    uvicorn backend.admin_main:app --host 127.0.0.1 --port 8100

Usa la misma base y los mismos modelos, pero la app pública (backend/main.py)
nunca monta estas rutas: en el dominio público no existen. Solo escucha en
127.0.0.1, y se llega a él por un Cloudflare Tunnel con Cloudflare Access
(Fase 3, docs/specs/panel-admin.md). Cada petición a /api pide un JWT de Access
válido de un correo de ADMIN_EMAILS (backend/admin_auth.py). Sin esa
configuración el proceso no arranca.

Gestión, no vigilancia: el panel cuenta filas, nunca enseña lo que escribe cada
persona (tareas, hábitos, gastos, textos de reportes).
"""
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from backend import admin_api, security_log  # noqa: E402
from backend.admin_auth import access_keys, admin_dependency, client_ip as admin_client_ip, load_config  # noqa: E402
from backend.database import check_pending_migrations, create_db_and_tables  # noqa: E402

ADMIN_CONFIG = load_config()
ACCESS_KEYS = access_keys(ADMIN_CONFIG)
require_admin = admin_dependency(ADMIN_CONFIG, ACCESS_KEYS)
if ADMIN_CONFIG.dev_keys_file:
    print(f"*** PANEL EN MODO DE DESARROLLO: confía en las llaves de {ADMIN_CONFIG.dev_keys_file}, "
          "no en Cloudflare Access. Nunca en producción. ***", file=sys.stderr, flush=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Las únicas páginas del panel: no hay StaticFiles, como en la app pública
PAGE_FILES = {"/": ("admin.html", "text/html"), "/admin.js": ("admin.js", "text/javascript"),
              "/admin-charts.js": ("admin-charts.js", "text/javascript"),
              "/admin.css": ("admin.css", "text/css")}

create_db_and_tables()
check_pending_migrations()

app = FastAPI(title="Habit Tracker · Admin", docs_url=None, redoc_url=None, openapi_url=None)

# Lo que el navegador puede hacer con estas páginas: solo scripts y estilos del
# propio panel (un texto escrito por un usuario nunca se ejecuta), sin marcos, sin
# enviar la URL a otros sitios y sin guardar copias
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _same_origin(request: Request) -> bool:
    """El Origin del navegador es el mismo host que el panel. Detrás de cloudflared
    el esquema que ve uvicorn es http, así que se compara el host, no la URL entera."""
    origin = request.headers.get("origin") or ""
    return bool(origin) and urlparse(origin).netloc == request.headers.get("host")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # CSRF: Access manda su JWT también en las peticiones que otro sitio haga con la
    # cookie de Access. Lo que cambia algo pide JSON y el Origin del propio panel
    if request.method not in SAFE_METHODS:
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type != "application/json" or not _same_origin(request):
            security_log.record("admin_csrf", admin_client_ip(request))
            response = JSONResponse({"detail": "Acceso denegado"}, status_code=403)
            for name, value in SECURITY_HEADERS.items():
                response.headers[name] = value
            return response
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


api = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


@api.get("/me")
def whoami(admin: str = Depends(require_admin)) -> dict:
    """Quién entró (el correo de Access)."""
    return {"email": admin}


api.include_router(admin_api.router)
app.include_router(api)


def _page(name: str, media_type: str):
    def serve():
        return FileResponse(os.path.join(BASE_DIR, name), media_type=media_type)
    return serve


# Las páginas no traen datos: todo lo que enseñan llega de /api, que pide administrador
for path, (name, media_type) in PAGE_FILES.items():
    app.add_api_route(path, _page(name, media_type), methods=["GET"], include_in_schema=False)
