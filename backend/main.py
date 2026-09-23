import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from backend.database import create_db_and_tables, check_pending_migrations
from backend.routers import auth, habits, projects, tasks, pomodoro, boards, tags

# Rutas de los archivos frontend (directorio raíz del proyecto)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cargar variables de entorno. Ruta explícita: bajo `uvicorn --reload` en Windows,
# el subproceso relanzado (multiprocessing spawn) rompe la detección automática
# de load_dotenv() basada en el stack frame, y nunca encuentra backend/.env.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Leer versión desde el archivo VERSION en la raíz del repo
with open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8") as f:
    APP_VERSION = f.read().strip()

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


def get_frontend_path(filename: str = "index.html") -> str:
    """Obtiene la ruta completa del archivo frontend"""
    return os.path.join(BASE_DIR, filename)


# Rutas del frontend
@app.get("/")
def root():
    """Serve frontend - raíz"""
    return FileResponse(get_frontend_path("index.html"))


@app.get("/index.html")
def index_html():
    """Serve index.html"""
    return FileResponse(get_frontend_path("index.html"))


@app.get("/styles.css")
def styles_css():
    """Serve styles.css"""
    return FileResponse(get_frontend_path("styles.css"))


@app.get("/script.js")
def script_js():
    """Serve script.js"""
    return FileResponse(get_frontend_path("script.js"))


@app.get("/projects.js")
def projects_js():
    """Serve projects.js"""
    return FileResponse(get_frontend_path("projects.js"))


@app.get("/board.js")
def board_js():
    """Serve board.js"""
    return FileResponse(get_frontend_path("board.js"))


@app.get("/pomodoro.js")
def pomodoro_js():
    """Serve pomodoro.js"""
    return FileResponse(get_frontend_path("pomodoro.js"))


@app.get("/reports.js")
def reports_js():
    """Serve reports.js"""
    return FileResponse(get_frontend_path("reports.js"))


# Instalable como app: manifest, iconos y favicon. Los iconos van por una lista
# cerrada, no por el nombre que pida la URL, para no servir otros archivos.
APP_ICONS = {
    "icon-192.png", "icon-512.png", "icon-maskable-192.png", "icon-maskable-512.png",
    "apple-touch-icon.png", "favicon-48.png",
}


@app.get("/manifest.webmanifest")
def web_manifest():
    """Serve the web app manifest"""
    return FileResponse(get_frontend_path("manifest.webmanifest"), media_type="application/manifest+json")


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


# Under /api for the same reason as /api/version: a bare /health never gets
# past the reverse proxy, so an uptime monitor would see a permanent 404.
@app.get("/api/health")
def health_check():
    """Health check endpoint for uptime monitors"""
    return {"status": "healthy"}
