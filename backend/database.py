import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

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
