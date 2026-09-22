import importlib.util
import os
from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from dotenv import load_dotenv

# Cargar variables de entorno desde .env. Ruta explícita: bajo `uvicorn --reload`
# en Windows, load_dotenv() sin ruta no encuentra backend/.env en el subproceso spawneado.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Obtener DATABASE_URL del .env (valor por defecto para desarrollo)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./habits.db")

# Crear engine
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables():
    """Crea las tablas en la base de datos"""
    SQLModel.metadata.create_all(bind=engine)


MIGRATE_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "migrate.py")


def check_pending_migrations():
    """
    Se niega a arrancar si a una tabla existente le falta una columna que
    scripts/migrate.py sabe añadir. create_all() no hace ALTER TABLE, así que
    sin esto la app arrancaba "bien" y cada request fallaba con un 500 de
    "no such column" (pasó con users.rest_days en la 1.7.0, y con
    projects.is_system en una base local). Mejor un error claro en el log
    del servicio que una app rota a medias.

    La lista sale del propio migrate.py, para que no haya dos copias que
    mantener. Cargarlo no ejecuta nada: su main() va tras un __main__.
    """
    spec = importlib.util.spec_from_file_location("migrate", MIGRATE_SCRIPT)
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = []
    for entry in migrate.MIGRATIONS:
        if entry["table"] not in tables:
            continue  # tabla nueva: create_all() ya la creó completa
        columns = {c["name"] for c in inspector.get_columns(entry["table"])}
        if entry["column"] not in columns:
            missing.append(f"{entry['table']}.{entry['column']}")

    if missing:
        raise RuntimeError(
            "La base de datos no está migrada (faltan: " + ", ".join(missing) + "). "
            "Corre `python3 scripts/migrate.py` desde la raíz del repo y vuelve a arrancar."
        )


def get_session() -> Generator[Session, None, None]:
    """Obtiene una sesión de base de datos"""
    with Session(engine) as session:
        yield session
