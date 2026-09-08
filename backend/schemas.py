from sqlmodel import Field, SQLModel
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


class UserUpdate(SQLModel):
    """Esquema para actualizar el perfil (todo opcional, PATCH parcial)"""
    display_name: Optional[str] = Field(default=None, max_length=40)
    first_name: Optional[str] = Field(default=None, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)


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


# ==================== Project Schemas ====================

class ProjectCreate(SQLModel):
    """Esquema para crear un proyecto"""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = 0


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


class ProjectResponse(SQLModel):
    """Esquema de respuesta para un proyecto"""
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: int
    is_active: bool
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
    project_id: int
    title: str
    notes: Optional[str] = None
    order: Optional[int] = 0


class TaskUpdate(SQLModel):
    """
    Esquema para actualizar una tarea existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    title: Optional[str] = None
    notes: Optional[str] = None
    is_done: Optional[bool] = None
    order: Optional[int] = None
    project_id: Optional[int] = None  # mover la tarea a otro proyecto


class TaskResponse(SQLModel):
    """Esquema de respuesta para una tarea"""
    id: int
    project_id: int
    title: str
    notes: Optional[str] = None
    is_done: bool
    order: int
    completed_at: Optional[date_type] = None
    created_at: date_type

    class Config:
        from_attributes = True


class TaskListResponse(SQLModel):
    """Lista de tareas"""
    tasks: List[TaskResponse]
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
