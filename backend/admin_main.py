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

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from backend.admin_auth import AccessKeys, admin_dependency, load_config  # noqa: E402
from backend.database import check_pending_migrations, create_db_and_tables  # noqa: E402

ADMIN_CONFIG = load_config()
ACCESS_KEYS = AccessKeys(ADMIN_CONFIG.certs_url)
require_admin = admin_dependency(ADMIN_CONFIG, ACCESS_KEYS)

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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


api = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


@api.get("/me")
def whoami(admin: str = Depends(require_admin)) -> dict:
    """Quién entró (el correo de Access)."""
    return {"email": admin}


app.include_router(api)
