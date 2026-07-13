import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from backend.database import create_db_and_tables
from backend.routers import auth, habits

# Rutas de los archivos frontend (directorio raíz del proyecto)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cargar variables de entorno
load_dotenv()

# Crear las tablas en la base de datos
create_db_and_tables()

# Inicializar FastAPI
app = FastAPI(
    title="Habits Tracker API",
    description="API para gestionar hábitos con autenticación",
    version="1.0.0",
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


# API info endpoint
@app.get("/api")
def api_info():
    """API info"""
    return {
        "message": "Habits Tracker API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
