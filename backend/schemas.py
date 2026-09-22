from sqlmodel import Field, SQLModel
from pydantic import field_validator
import re
from typing import Optional, Dict, List
from datetime import date as date_type, datetime
from sqlalchemy import JSON


# ==================== Auth Schemas ====================

class UserCreate(SQLModel):
    """Esquema para crear usuario"""
    email: str
    password: str
    display_name: Optional[str] = Field(default=None, max_length=40)
    first_name: Optional[str] = Field(default=None, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)


class UserResponse(SQLModel):
    """Esquema para respuesta de usuario"""
    id: int
    email: str
    is_active: bool
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    rest_days: Optional[List[int]] = None


class UserUpdate(SQLModel):
    """Esquema para actualizar el perfil (todo opcional, PATCH parcial)"""
    display_name: Optional[str] = Field(default=None, max_length=40)
    first_name: Optional[str] = Field(default=None, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)
    rest_days: Optional[List[int]] = None

    @field_validator("rest_days")
    @classmethod
    def validate_rest_days(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return None
        for day in v:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError("Los días de descanso deben ser números entre 0 (lunes) y 6 (domingo)")
        return sorted(list(set(v)))


class Token(SQLModel):
    """Esquema para token de acceso"""
    access_token: str
    token_type: str


class TokenData(SQLModel):
    """Datos dentro del token"""
    email: Optional[str] = None


# ==================== Habit Schemas ====================

class HabitData(SQLModel):
    """Datos de hábitos para un día específico - campos dinámicos"""
    # Usaremos un dict para cualquier hábito
    pass


class HabitEntryCreate(SQLModel):
    """Esquema para crear/actualizar entrada de hábitos"""
    date: date_type
    habits: Dict = Field(default={})  # Dict[str, bool]


class HabitEntryResponse(SQLModel):
    """Esquema para respuesta de entrada de hábitos"""
    id: int
    date: date_type = Field(alias="entry_date")
    habits_data: Dict = Field(default={}, sa_type=JSON)

    class Config:
        populate_by_name = True


class HabitStats(SQLModel):
    """Estadísticas de hábitos - dinámicas"""
    pass


class UserHabitsResponse(SQLModel):
    """Respuesta completa de hábitos del usuario"""
    entries: list
    stats: Dict = Field(default={})  # Dict[str, int]
    streak: int


# ==================== Habit Definition Schemas ====================

class HabitCreate(SQLModel):
    """
    Esquema para crear un nuevo hábito.
    El frontend envía estos datos al registrar un hábito nuevo.
    """
    key: str                          # Clave única por usuario (ej: "lectura")
    label: str                        # Nombre visible (ej: "Lectura")
    icon: Optional[str] = None        # Emoji (ej: "📚")
    color: Optional[str] = None       # Hex color (ej: "#3498db")
    order: Optional[int] = 0         # Posición en la UI


class HabitUpdate(SQLModel):
    """
    Esquema para actualizar un hábito existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    label: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None  # False = archivar (no borra datos históricos)


class HabitResponse(SQLModel):
    """
    Esquema de respuesta para un hábito.
    Incluye todos los campos que el frontend necesita para renderizar.
    """
    id: int
    key: str
    label: str
    icon: Optional[str] = None
    color: Optional[str] = None
    order: int
    is_active: bool
    created_at: date_type

    class Config:
        from_attributes = True


class HabitListResponse(SQLModel):
    """Lista de hábitos del usuario (activos e inactivos)"""
    habits: List[HabitResponse]
    total: int


# ==================== Board Schemas ====================

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_hex_color(v: Optional[str]) -> Optional[str]:
    # A mano y no con Field(regex=...): sqlmodel 0.0.14 no lo aplica con
    # Pydantic v2 y el valor pasaba sin validar.
    if v is not None and not HEX_COLOR.match(v):
        raise ValueError("El color debe ser hexadecimal, por ejemplo #3498db")
    return v


class ColumnCreate(SQLModel):
    """Esquema para agregar una columna a un tablero"""
    category: str                     # todo | doing | done
    name: str = Field(min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = None       # sin él, va al final

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ColumnUpdate(SQLModel):
    """
    Esquema para actualizar una columna (PATCH parcial). La categoría no se
    cambia: sus tareas tendrían que recalcular is_done. Para eso, crear una
    columna nueva, mover las tareas y borrar la vieja.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ColumnResponse(SQLModel):
    """Esquema de respuesta para una columna"""
    id: int
    board_id: int
    category: str
    name: str
    color: Optional[str] = None
    order: int

    class Config:
        from_attributes = True


class BoardCreate(SQLModel):
    """Esquema para crear un tablero. Nace con las columnas por defecto."""
    name: str = Field(min_length=1, max_length=60)
    order: Optional[int] = 0


class BoardUpdate(SQLModel):
    """Esquema para actualizar un tablero (PATCH parcial)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    order: Optional[int] = None
    is_active: Optional[bool] = None  # False = archivar (conserva todo)


class BoardResponse(SQLModel):
    """Un tablero con sus columnas, en orden"""
    id: int
    name: str
    order: int
    is_active: bool
    created_at: date_type
    columns: List[ColumnResponse] = []


class BoardListResponse(SQLModel):
    """Lista de tableros del usuario"""
    boards: List[BoardResponse]
    total: int


# ==================== Project Status Schemas ====================

class ProjectStatusCreate(SQLModel):
    """Esquema para crear un estado de proyecto"""
    category: str                     # idea | active | paused | done
    name: str = Field(min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = None       # sin él, va al final

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ProjectStatusUpdate(SQLModel):
    """Esquema para actualizar un estado de proyecto. La categoría es fija."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ProjectStatusResponse(SQLModel):
    """Esquema de respuesta para un estado de proyecto"""
    id: int
    category: str
    name: str
    color: Optional[str] = None
    order: int

    class Config:
        from_attributes = True


class ProjectStatusListResponse(SQLModel):
    """Estados de proyecto del usuario"""
    statuses: List[ProjectStatusResponse]
    total: int


# ==================== Project Schemas ====================

class ProjectCreate(SQLModel):
    """Esquema para crear un proyecto"""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = 0
    status_id: Optional[int] = None   # sin él, el primer estado "active"


class ProjectUpdate(SQLModel):
    """
    Esquema para actualizar un proyecto existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None  # False = archivar (conserva las tareas)
    status_id: Optional[int] = None


class ProjectResponse(SQLModel):
    """Esquema de respuesta para un proyecto"""
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: int
    is_active: bool
    status_id: Optional[int] = None
    is_system: bool = False           # "Sin asignar": no se renombra, archiva ni borra
    created_at: date_type

    class Config:
        from_attributes = True


class ProjectListResponse(SQLModel):
    """Lista de proyectos del usuario (activos e inactivos)"""
    projects: List[ProjectResponse]
    total: int


class ProjectSummary(SQLModel):
    """
    Resumen de un proyecto: progreso de tareas y tiempo dedicado.
    total_seconds/session_count quedan en 0 hasta que exista Pomodoro.
    """
    project_id: int
    name: str
    color: Optional[str] = None
    task_total: int
    task_done: int

    # Desglose de total_seconds por tarea. Clave: task_id como string (JSON no
    # admite claves numéricas). El tiempo registrado sin tarea no aparece aquí,
    # va en seconds_no_task, de forma que la suma de ambos da total_seconds.
    seconds_by_task: Dict[str, int] = {}
    seconds_no_task: int = 0
    total_seconds: int
    session_count: int


class ProjectSummaryListResponse(SQLModel):
    """Lista de resúmenes de proyectos"""
    summaries: List[ProjectSummary]
    total: int


# ==================== Task Schemas ====================

class TaskCreate(SQLModel):
    """Esquema para crear una tarea"""
    project_id: Optional[int] = None  # sin él, "Sin asignar"
    title: str
    notes: Optional[str] = None
    order: Optional[int] = 0
    column_id: Optional[int] = None   # columna exacta; manda sobre board_id
    board_id: Optional[int] = None    # sin column_id: la primera "todo" de este tablero
    tag_ids: Optional[List[int]] = None


class TaskUpdate(SQLModel):
    """
    Esquema para actualizar una tarea existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    title: Optional[str] = None
    notes: Optional[str] = None
    is_done: Optional[bool] = None
    order: Optional[int] = None
    project_id: Optional[int] = None  # cambiar el proyecto; null = "Sin asignar"
    column_id: Optional[int] = None   # mover la tarea de columna (o de tablero); manda sobre is_done
    tag_ids: Optional[List[int]] = None  # reemplaza TODAS las etiquetas; [] las quita


class TaskResponse(SQLModel):
    """Esquema de respuesta para una tarea"""
    id: int
    project_id: int
    title: str
    notes: Optional[str] = None
    is_done: bool
    column_id: Optional[int] = None
    board_id: Optional[int] = None    # el de su columna
    order: int
    completed_at: Optional[date_type] = None
    created_at: date_type

    # Para pintar la tarjeta sin pedir el detalle de cada tarea
    checklist_total: int = 0
    checklist_done: int = 0
    comment_count: int = 0
    tag_ids: List[int] = []

    class Config:
        from_attributes = True


class TaskListResponse(SQLModel):
    """Lista de tareas"""
    tasks: List[TaskResponse]
    total: int


# ==================== Tag Schemas ====================

class TagCreate(SQLModel):
    """Esquema para crear una etiqueta"""
    name: str = Field(min_length=1, max_length=30)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class TagUpdate(SQLModel):
    """Esquema para renombrar o recolorear una etiqueta (PATCH parcial)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=30)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class TagResponse(SQLModel):
    """Esquema de respuesta para una etiqueta"""
    id: int
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class TagListResponse(SQLModel):
    """Etiquetas del usuario, por nombre"""
    tags: List[TagResponse]
    total: int


class TagSummary(SQLModel):
    """
    Tiempo de enfoque en tareas con esta etiqueta. Una tarea con dos
    etiquetas suma su tiempo en las dos: los totales por etiqueta pueden
    superar el tiempo real. El total exacto es el de los proyectos.
    """
    tag_id: int
    name: str
    color: Optional[str] = None
    task_count: int
    total_seconds: int
    session_count: int


class TagSummaryListResponse(SQLModel):
    """
    Resumen de tiempo por etiqueta.

    summaries es el desglose: cada etiqueta con su total, y una sesión
    aparece en todas las etiquetas de su tarea. Por eso NO se suman entre sí.

    combined_* es el total real de las etiquetas pedidas (?tag_ids=, o todas
    si no se pide ninguna): cada sesión cuenta UNA vez aunque tenga varias.
    untagged_* es el tiempo de enfoque sin ninguna etiqueta, incluido el que
    se registró sin tarea: lo que falta clasificar.
    """
    summaries: List[TagSummary]
    total: int
    combined_seconds: int = 0
    combined_session_count: int = 0
    untagged_seconds: int = 0
    untagged_session_count: int = 0


# ==================== Checklist Schemas ====================

class ChecklistItemCreate(SQLModel):
    """Esquema para agregar una línea al checklist de una tarea"""
    text: str = Field(min_length=1, max_length=200)
    order: Optional[int] = None  # sin él, va al final


class ChecklistItemUpdate(SQLModel):
    """Esquema para actualizar una línea del checklist (PATCH parcial)"""
    text: Optional[str] = Field(default=None, min_length=1, max_length=200)
    is_done: Optional[bool] = None
    order: Optional[int] = None


class ChecklistItemResponse(SQLModel):
    """Esquema de respuesta para una línea del checklist"""
    id: int
    task_id: int
    text: str
    is_done: bool
    order: int

    class Config:
        from_attributes = True


class ChecklistListResponse(SQLModel):
    """Checklist de una tarea"""
    items: List[ChecklistItemResponse]
    total: int


# ==================== Comment Schemas ====================

class CommentCreate(SQLModel):
    """Esquema para comentar una tarea"""
    body: str = Field(min_length=1, max_length=2000)


class CommentUpdate(SQLModel):
    """Esquema para editar un comentario propio"""
    body: str = Field(min_length=1, max_length=2000)


class CommentResponse(SQLModel):
    """
    Esquema de respuesta para un comentario. author_name es el display_name
    del autor o, si no tiene, su email.
    """
    id: int
    task_id: int
    author_id: int
    author_name: str
    body: str
    created_at: datetime
    edited_at: Optional[datetime] = None


class CommentListResponse(SQLModel):
    """Comentarios de una tarea, del más viejo al más nuevo"""
    comments: List[CommentResponse]
    total: int


# ==================== Pomodoro Schemas ====================

class PomodoroSessionCreate(SQLModel):
    """Esquema para registrar una sesión de pomodoro ya finalizada"""
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    session_date: date_type
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    planned_seconds: Optional[int] = 1500
    mode: Optional[str] = "focus"
    was_completed: Optional[bool] = True
    note: Optional[str] = None
    source: Optional[str] = "timer"


class PomodoroSessionUpdate(SQLModel):
    """
    Esquema para corregir una sesión ya registrada (PATCH parcial).
    No se puede mover de proyecto ni cambiar el origen: para eso, borrar y
    volver a crear.
    """
    task_id: Optional[int] = None
    session_date: Optional[date_type] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    note: Optional[str] = None


class PomodoroSessionResponse(SQLModel):
    """Esquema de respuesta para una sesión de pomodoro"""
    id: int
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    session_date: date_type
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    planned_seconds: int
    mode: str
    was_completed: bool
    note: Optional[str] = None
    source: str = "timer"
    created_at: date_type

    class Config:
        from_attributes = True


class PomodoroSessionListResponse(SQLModel):
    """Lista de sesiones de pomodoro"""
    sessions: List[PomodoroSessionResponse]
    total: int


class PomodoroStatsResponse(SQLModel):
    """Estadísticas agregadas de pomodoros"""
    total_seconds: int
    session_count: int
    today_seconds: int
    by_project: Dict[str, int]
    by_date: Dict[str, int]
