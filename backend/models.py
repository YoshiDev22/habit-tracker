from sqlmodel import SQLModel, Field
from typing import Optional, Dict
from datetime import date as date_type, datetime
from sqlalchemy import JSON, UniqueConstraint


class User(SQLModel, table=True):
    """Modelo de Usuario"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)

    # Perfil, todo opcional y solo cosmético: el login sigue siendo por email.
    # Nullable a propósito, para que las cuentas que ya existen sigan valiendo.
    display_name: Optional[str] = Field(default=None)
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)


class HabitEntry(SQLModel, table=True):
    """Modelo de Entrada de Hábito (día específico) — se mantiene sin cambios"""
    __tablename__ = "habit_entries"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    entry_date: date_type = Field(index=True)
    
    # Almacena los hábitos como JSON
    habits_data: Dict = Field(default={}, sa_type=JSON)


class Habit(SQLModel, table=True):
    """
    Definición de un hábito por usuario.
    Persiste la configuración de hábitos en la base de datos,
    evitando depender solo del localStorage del navegador.
    """
    __tablename__ = "habits"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # Identificador corto usado como clave en habits_data (ej: "lectura")
    key: str = Field(index=True)

    # Nombre visible en la UI (ej: "Lectura")
    label: str

    # Emoji o texto corto para el ícono (ej: "📚")
    icon: Optional[str] = Field(default=None)

    # Color hexadecimal (ej: "#3498db")
    color: Optional[str] = Field(default=None)

    # Orden de aparición en la UI (menor = primero)
    order: int = Field(default=0)

    # Si es False, el hábito está "archivado" pero sus datos históricos se conservan
    is_active: bool = Field(default=True)

    # Fecha de creación
    created_at: date_type = Field(default_factory=date_type.today)


class Project(SQLModel, table=True):
    """
    Proyecto u objetivo del usuario. Tabla NUEVA: create_all() la crea sola
    al arrancar, sin migración.
    NOTA: agregar una columna aquí en el futuro NO se aplica automáticamente
    sobre una base existente (create_all no hace ALTER TABLE) — requeriría
    una migración manual.
    """
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str
    description: Optional[str] = Field(default=None)

    # Color hexadecimal (ej: "#3498db")
    color: Optional[str] = Field(default=None)

    # Emoji o texto corto para el ícono
    icon: Optional[str] = Field(default=None)

    # Orden de aparición en la UI (menor = primero)
    order: int = Field(default=0)

    # Si es False, el proyecto está "archivado" pero sus tareas se conservan
    is_active: bool = Field(default=True)

    created_at: date_type = Field(default_factory=date_type.today)


class Task(SQLModel, table=True):
    """Tarea dentro de un proyecto (tasklist)."""
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)  # denormalizado, igual que Habit
    project_id: int = Field(foreign_key="projects.id", index=True)

    title: str
    notes: Optional[str] = Field(default=None)
    is_done: bool = Field(default=False)

    # Orden de aparición en la UI (menor = primero)
    order: int = Field(default=0)

    completed_at: Optional[date_type] = Field(default=None)
    created_at: date_type = Field(default_factory=date_type.today)


class PomodoroSession(SQLModel, table=True):
    """
    Registro de una sesión de pomodoro. Append-only (no se edita, solo se
    crea o se borra). Tabla NUEVA, aditiva — ver nota en Project.
    """
    __tablename__ = "pomodoro_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id", index=True)
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id", index=True)

    # Fecha LOCAL del usuario, calculada en el cliente (getDateKey()) y no
    # derivada de started_at en el servidor: agrupar por date(started_at)
    # archivaría sesiones nocturnas bajo el día equivocado según el huso
    # horario del usuario. Toda la agregación por día/mes usa esta columna.
    session_date: date_type = Field(index=True)

    # UTC naive, igual que backend/auth.py (datetime.utcnow()). El cliente
    # nunca parsea estos valores para la lógica del timer (solo Date.now()
    # + localStorage), evitando el problema de que un datetime naive se
    # interprete como hora local al hacer new Date(...) en el navegador.
    started_at: datetime = Field()
    ended_at: datetime = Field()

    duration_seconds: int = Field()  # medido, no planeado
    planned_seconds: int = Field(default=1500)
    mode: str = Field(default="focus", index=True)  # focus | short_break | long_break
    was_completed: bool = Field(default=True)
    note: Optional[str] = Field(default=None)

    created_at: date_type = Field(default_factory=date_type.today)
