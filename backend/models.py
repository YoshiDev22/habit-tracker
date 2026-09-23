from sqlmodel import SQLModel, Field
from typing import Optional, Dict, List
from datetime import date as date_type, datetime, timezone
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

    # Días de descanso semanal (0=lunes ... 6=domingo). Congelan la racha.
    rest_days: List[int] = Field(default=[], sa_type=JSON)

    # Duraciones del pomodoro, en segundos. NULL = el valor por defecto
    # (25 / 5 / 15 min), así las cuentas que ya existen no necesitan relleno.
    # Columnas añadidas en la 1.14: van en scripts/migrate.py.
    pomodoro_focus_seconds: Optional[int] = Field(default=None)
    pomodoro_short_break_seconds: Optional[int] = Field(default=None)
    pomodoro_long_break_seconds: Optional[int] = Field(default=None)


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


class Board(SQLModel, table=True):
    """
    Tablero kanban: "Escuela", "Área de ventas"... Cada uno tiene sus propias
    columnas (BoardColumn) y sus tareas viven en ellas. Los proyectos no son
    contenedores sino etiquetas de la tarea, usables en cualquier tablero.
    Tabla NUEVA: create_all() la crea sola.

    user_id es el dueño. Compartir un tablero con otros usuarios no existe
    todavía; cuando exista será una tabla de miembros aparte.
    """
    __tablename__ = "boards"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_boards_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str

    # Orden de aparición en el selector de tableros (menor = primero)
    order: int = Field(default=0)

    # Si es False, el tablero está "archivado": se oculta y conserva todo
    is_active: bool = Field(default=True)

    created_at: date_type = Field(default_factory=date_type.today)


class BoardColumn(SQLModel, table=True):
    """
    Columna de un tablero. El usuario elige nombre, color, orden y cuántas
    hay; `category` (todo | doing | done) es fija y es lo único que lee el
    código: una columna "Esperando cliente" sigue siendo "doing", y una tarea
    está hecha si su columna es "done". Ver backend/boards.py. Tabla NUEVA.
    """
    __tablename__ = "board_columns"
    __table_args__ = (UniqueConstraint("board_id", "name", name="uq_board_columns_board_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    board_id: int = Field(foreign_key="boards.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)  # denormalizado, igual que Task

    category: str
    name: str

    # Color hexadecimal (ej: "#3498db")
    color: Optional[str] = Field(default=None)

    # Orden de la columna en el tablero (menor = primero)
    order: int = Field(default=0)

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

    # True solo en "Sin asignar", el proyecto que cada usuario recibe para las
    # tareas sin proyecto. Existe porque tasks.project_id es NOT NULL y quitar
    # eso en SQLite obliga a reconstruir la tabla en producción. No se
    # renombra, ni se archiva, ni se borra. Columna AÑADIDA: migrate.py.
    is_system: bool = Field(default=False)

    created_at: date_type = Field(default_factory=date_type.today)


class Task(SQLModel, table=True):
    """
    Tarea: la tarjeta del tablero. Vive en una columna de un tablero
    (column_id, y por ella en el tablero) y lleva un proyecto como etiqueta
    (project_id), que es donde se suma su tiempo.
    """
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)  # denormalizado, igual que Habit
    project_id: int = Field(foreign_key="projects.id", index=True)

    title: str
    notes: Optional[str] = Field(default=None)

    # Se mantiene sincronizado con la categoría de column_id ("done" <=> True),
    # para que el progreso de /api/projects/summary siga saliendo de aquí.
    is_done: bool = Field(default=False)

    # Columna del tablero. Columna AÑADIDA a una tabla existente: la agrega
    # scripts/migrate.py como NULL, y ensure_user_setup() rellena los NULL al
    # primer request del usuario. Sin index=True a propósito: migrate.py no
    # crea índices y una base nueva quedaría distinta a la de prod.
    column_id: Optional[int] = Field(default=None, foreign_key="board_columns.id")

    # Orden de aparición en la UI (menor = primero)
    order: int = Field(default=0)

    completed_at: Optional[date_type] = Field(default=None)
    created_at: date_type = Field(default_factory=date_type.today)


class Tag(SQLModel, table=True):
    """
    Etiqueta libre de una tarea ("documentación", "administrativa"...), para
    filtrar y para saber en qué tipo de actividad se va el tiempo. Distinta
    del proyecto: una tarea tiene UN proyecto y VARIAS etiquetas. Tabla NUEVA.
    """
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    name: str

    # Color hexadecimal (ej: "#3498db")
    color: Optional[str] = Field(default=None)

    created_at: date_type = Field(default_factory=date_type.today)


class TaskTag(SQLModel, table=True):
    """Qué etiquetas tiene cada tarea (muchos a muchos). Tabla NUEVA."""
    __tablename__ = "task_tags"
    __table_args__ = (UniqueConstraint("task_id", "tag_id", name="uq_task_tags_task_tag"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)  # denormalizado, igual que Task
    task_id: int = Field(foreign_key="tasks.id", index=True)
    tag_id: int = Field(foreign_key="tags.id", index=True)


def utc_now_naive() -> datetime:
    """UTC naive, el mismo formato que started_at/ended_at del pomodoro, sin
    el datetime.utcnow() deprecado."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskChecklistItem(SQLModel, table=True):
    """Subtarea de una tarea: una línea que se marca, sin tiempos. Tabla NUEVA."""
    __tablename__ = "task_checklist_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)  # denormalizado, igual que Task
    task_id: int = Field(foreign_key="tasks.id", index=True)

    text: str
    is_done: bool = Field(default=False)

    # Orden de aparición en la UI (menor = primero)
    order: int = Field(default=0)

    created_at: date_type = Field(default_factory=date_type.today)


class TaskComment(SQLModel, table=True):
    """
    Comentario de seguimiento en una tarea. Tabla NUEVA.

    user_id es el DUEÑO de la tarea, y es lo que filtran las queries, igual
    que en el resto de tablas. author_id es quien lo escribió. Hoy son
    siempre la misma persona; están separados para que un tablero compartido
    el día de mañana no obligue a migrar los comentarios.
    """
    __tablename__ = "task_comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    author_id: int = Field(foreign_key="users.id")

    body: str

    # UTC naive. El cliente lo convierte a su hora local solo para mostrarlo.
    created_at: datetime = Field(default_factory=utc_now_naive)
    edited_at: Optional[datetime] = Field(default=None)


class PomodoroSession(SQLModel, table=True):
    """
    Registro de una sesión de pomodoro. La crea el timer al terminar, o el
    usuario a mano; en ambos casos se puede corregir o borrar después.
    Tabla NUEVA, aditiva — ver nota en Project.
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

    # UTC naive (utc_now_naive() o el datetime.utcnow() de antes). El cliente
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

    # "timer": la midió el cronómetro. "manual": la escribió el usuario a
    # posteriori. Columna AÑADIDA a una tabla existente, así que necesita
    # scripts/migrate.py; las filas previas se rellenan con "timer", que es
    # la verdad para todo lo registrado hasta ahora.
    source: str = Field(default="timer", index=True)

    created_at: date_type = Field(default_factory=date_type.today)
