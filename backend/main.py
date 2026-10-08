import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv

from backend import novedades
from backend.database import create_db_and_tables, check_pending_migrations
from backend.routers import auth, habits, projects, tasks, pomodoro, boards, tags, costs, days, metrics, reports

# Rutas de los archivos frontend (directorio raíz del proyecto)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cargar variables de entorno. Ruta explícita: bajo `uvicorn --reload` en Windows,
# el subproceso relanzado (multiprocessing spawn) rompe la detección automática
# de load_dotenv() basada en el stack frame, y nunca encuentra backend/.env.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Leer versión desde el archivo VERSION en la raíz del repo
with open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8") as f:
    APP_VERSION = f.read().strip()
# Las Novedades de cada versión (NOVEDADES.md), leídas una vez, como VERSION.
# HABIT_NOVEDADES_FILE solo lo usan las pruebas de navegador (sin ventana)
NOVEDADES = novedades.load(os.getenv("HABIT_NOVEDADES_FILE") or os.path.join(BASE_DIR, "NOVEDADES.md"))

# Crear las tablas en la base de datos, y parar si a alguna existente le
# faltan columnas por migrar (ver check_pending_migrations)
create_db_and_tables()
check_pending_migrations()

# Inicializar FastAPI
app = FastAPI(
    title="Habits Tracker API",
    description="API para gestionar hábitos con autenticación",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# No CORS middleware on purpose: the frontend is served by this same app, so
# every browser request is same-origin. Allowing "*" with credentials made
# Starlette echo back any Origin, i.e. accept every site.

# Incluir routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(habits.router, prefix="/api/habits")
app.include_router(projects.router, prefix="/api/projects")
app.include_router(tasks.router, prefix="/api/tasks")
app.include_router(pomodoro.router, prefix="/api/pomodoro")
app.include_router(boards.router, prefix="/api/boards")
app.include_router(tags.router, prefix="/api/tags")
app.include_router(costs.router, prefix="/api/costs")
app.include_router(days.router, prefix="/api/days")
app.include_router(metrics.router, prefix="/api/metrics")
app.include_router(reports.router, prefix="/api/reports")


def get_frontend_path(filename: str = "index.html") -> str:
    """Obtiene la ruta completa del archivo frontend"""
    return os.path.join(BASE_DIR, filename)


# El frontend no tiene build ni nombres con hash: sin esta cabecera el navegador
# (y Cloudflare, si está delante) guardaba board.js de una versión y settings.js
# de otra, y la app se rompía tras un deploy. "no-cache" no impide guardarlos:
# obliga a preguntar antes de usarlos, y si no cambiaron la respuesta es un 304.
NO_CACHE = {"Cache-Control": "no-cache"}


def frontend_file(filename: str, **kwargs) -> FileResponse:
    return FileResponse(get_frontend_path(filename), headers=NO_CACHE, **kwargs)


@app.middleware("http")
async def not_modified(request: Request, call_next):
    """304 cuando el navegador ya tiene esa versión (mismo ETag). FileResponse pone
    el ETag, pero esta versión de Starlette no contesta If-None-Match: sin esto,
    "no-cache" bajaría todos los archivos en cada carga."""
    response = await call_next(request)
    etag = response.headers.get("etag")
    if request.method == "GET" and etag and request.headers.get("if-none-match") == etag:
        headers = {name: response.headers[name] for name in ("etag", "cache-control", "last-modified")
                   if name in response.headers}
        return Response(status_code=304, headers=headers)
    return response


# Rutas del frontend
@app.get("/")
def root():
    """Serve frontend - raíz"""
    return frontend_file("index.html")


@app.get("/index.html")
def index_html():
    """Serve index.html"""
    return frontend_file("index.html")


@app.get("/styles.css")
def styles_css():
    """Serve styles.css"""
    return frontend_file("styles.css")


@app.get("/script.js")
def script_js():
    """Serve script.js"""
    return frontend_file("script.js")


@app.get("/habits.js")
def habits_js():
    """Serve habits.js"""
    return frontend_file("habits.js")


@app.get("/projects.js")
def projects_js():
    """Serve projects.js"""
    return frontend_file("projects.js")


@app.get("/board.js")
def board_js():
    """Serve board.js"""
    return frontend_file("board.js")


@app.get("/pomodoro.js")
def pomodoro_js():
    """Serve pomodoro.js"""
    return frontend_file("pomodoro.js")


@app.get("/reports.js")
def reports_js():
    """Serve reports.js"""
    return frontend_file("reports.js")


@app.get("/project-overview.js")
def project_overview_js():
    """Serve project-overview.js"""
    return frontend_file("project-overview.js")


@app.get("/costs.js")
def costs_js():
    """Serve costs.js"""
    return frontend_file("costs.js")


@app.get("/notifications.js")
def notifications_js():
    """Serve notifications.js"""
    return frontend_file("notifications.js")


@app.get("/workdays.js")
def workdays_js():
    """Serve workdays.js"""
    return frontend_file("workdays.js")


@app.get("/settings.js")
def settings_js():
    """Serve settings.js"""
    return frontend_file("settings.js")


@app.get("/saved-reports.js")
def saved_reports_js():
    """Serve saved-reports.js"""
    return frontend_file("saved-reports.js")


@app.get("/costs-recurring.js")
def costs_recurring_js():
    """Serve costs-recurring.js"""
    return frontend_file("costs-recurring.js")


@app.get("/novedades.js")
def novedades_js():
    """Serve novedades.js"""
    return frontend_file("novedades.js")


@app.get("/account.js")
def account_js():
    """Serve account.js"""
    return frontend_file("account.js")


@app.get("/drilldown.js")
def drilldown_js():
    """Serve drilldown.js"""
    return frontend_file("drilldown.js")


# Instalable como app: manifest, iconos y favicon. Los iconos van por una lista
# cerrada, no por el nombre que pida la URL, para no servir otros archivos.
APP_ICONS = {
    "icon-192.png", "icon-512.png", "icon-maskable-192.png", "icon-maskable-512.png",
    "apple-touch-icon.png", "favicon-48.png",
}


@app.get("/manifest.webmanifest")
def web_manifest():
    """Serve the web app manifest"""
    return frontend_file("manifest.webmanifest", media_type="application/manifest+json")


@app.get("/icons/{name}")
def app_icon(name: str):
    """Serve one of the app icons"""
    if name not in APP_ICONS:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(get_frontend_path(os.path.join("icons", name)), media_type="image/png")


@app.get("/favicon.ico")
def favicon():
    """Serve the favicon (a PNG: every current browser accepts it)"""
    return FileResponse(get_frontend_path(os.path.join("icons", "favicon-48.png")), media_type="image/png")


def build_api_info() -> dict:
    """Payload shared by /api and /api/version"""
    return {
        "message": "Habits Tracker API",
        "version": APP_VERSION,
        "docs": "/api/docs"
    }


# API info endpoint
@app.get("/api")
def api_info():
    """API info"""
    return build_api_info()


# Same payload under /api/<segment>: the reverse proxy in production only
# forwards paths with a segment after /api, so /api itself never reaches the
# app. The frontend reads the version from here.
@app.get("/api/version")
def api_version():
    """API info, reachable behind the reverse proxy"""
    return build_api_info()


@app.get("/api/novedades")
def api_novedades():
    """What's new in each version, from NOVEDADES.md (never the CHANGELOG), the
    newest first. Public, like /api/version: it's the app's own text."""
    return {"current": APP_VERSION, "versions": NOVEDADES}


# Under /api for the same reason as /api/version: a bare /health never gets
# past the reverse proxy, so an uptime monitor would see a permanent 404.
@app.get("/api/health")
def health_check():
    """Health check endpoint for uptime monitors"""
    return {"status": "healthy"}
