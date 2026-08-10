import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from backend.database import create_db_and_tables
from backend.routers import auth, habits, projects, tasks

# Rutas de los archivos frontend (directorio raíz del proyecto)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cargar variables de entorno. Ruta explícita: bajo `uvicorn --reload` en Windows,
# el subproceso relanzado (multiprocessing spawn) rompe la detección automática
# de load_dotenv() basada en el stack frame, y nunca encuentra backend/.env.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Leer versión desde el archivo VERSION en la raíz del repo
with open(os.path.join(BASE_DIR, "VERSION"), encoding="utf-8") as f:
    APP_VERSION = f.read().strip()

# Crear las tablas en la base de datos
create_db_and_tables()

# Inicializar FastAPI
app = FastAPI(
    title="Habits Tracker API",
    description="API para gestionar hábitos con autenticación",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(habits.router, prefix="/api/habits")
app.include_router(projects.router, prefix="/api/projects")
app.include_router(tasks.router, prefix="/api/tasks")


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


# API info endpoint
@app.get("/api")
def api_info():
    """API info"""
    return {
        "message": "Habits Tracker API",
        "version": APP_VERSION,
        "docs": "/api/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
