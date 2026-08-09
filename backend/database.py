import os
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


def get_session() -> Generator[Session, None, None]:
    """Obtiene una sesión de base de datos"""
    with Session(engine) as session:
        yield session
