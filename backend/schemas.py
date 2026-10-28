from sqlmodel import Field, SQLModel
from pydantic import ConfigDict, field_validator, model_validator
import re
from typing import Optional, Dict, List
from datetime import date as date_type, datetime
from sqlalchemy import JSON


# ==================== Auth Schemas ====================

class UserCreate(SQLModel):
    """Esquema para crear usuario"""
    # 254 es el largo máximo de un email; la contraseña, el mínimo del formulario
    # y un tope holgado (bcrypt solo usa los primeros 72 bytes)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=40)
    first_name: Optional[str] = Field(default=None, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Lo mismo que pide el input type="email", sin librerías: algo@algo
        local, at, domain = v.partition("@")
        if not local or not at or not domain or any(c.isspace() for c in v):
            raise ValueError("El email no es válido")
        return v


class ModuleState(SQLModel):
    """Un módulo para esta cuenta: si se ve (enabled) y si puede encenderlo (allowed)"""
    enabled: bool
    allowed: bool


class ModuleUpdate(SQLModel):
    """Encender o apagar un módulo desde Mi perfil"""
    enabled: bool


class UserResponse(SQLModel):
    """Esquema para respuesta de usuario"""
    id: int
    email: str
    is_active: bool
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    rest_days: Optional[List[int]] = None
    pomodoro_focus_seconds: Optional[int] = None
    pomodoro_short_break_seconds: Optional[int] = None
    pomodoro_long_break_seconds: Optional[int] = None
    # Todos los de backend/modules.py, por nombre ("habits", "maker")
    modules: Dict[str, ModuleState] = {}
    # Borrado programado ("irme unos días"): la app ofrece conservar la cuenta
    delete_after: Optional[datetime] = None


POMODORO_FIELDS = ("pomodoro_focus_seconds", "pomodoro_short_break_seconds", "pomodoro_long_break_seconds")


class UserUpdate(SQLModel):
    """Esquema para actualizar el perfil (todo opcional, PATCH parcial)"""
    display_name: Optional[str] = Field(default=None, max_length=40)
    first_name: Optional[str] = Field(default=None, max_length=60)
    last_name: Optional[str] = Field(default=None, max_length=60)
    rest_days: Optional[List[int]] = None
    # null = volver al valor por defecto
    pomodoro_focus_seconds: Optional[int] = None
    pomodoro_short_break_seconds: Optional[int] = None
    pomodoro_long_break_seconds: Optional[int] = None

    @field_validator(*POMODORO_FIELDS)
    @classmethod
    def validate_pomodoro_seconds(cls, v: Optional[int]) -> Optional[int]:
        # Entre 1 minuto y 4 horas: un cero dejaría el timer inservible
        if v is not None and not (60 <= v <= 4 * 3600):
            raise ValueError("La duración debe estar entre 1 minuto y 4 horas")
        return v

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


class PasswordChange(SQLModel):
    """Cambiar la contraseña estando dentro: la actual y la nueva"""
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
    logout_others: bool = True      # cerrar la sesión en los otros dispositivos


DELETE_MODES = ("later", "now")
DELETE_CONFIRMATION = "BORRAR"


class AccountDelete(SQLModel):
    """Irse: 'later' programa el borrado (30 días); 'now' borra todo ya"""
    password: str = Field(max_length=128)
    mode: str
    confirm: Optional[str] = Field(default=None, max_length=20)   # "BORRAR", para 'now'
    logout_others: bool = True

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in DELETE_MODES:
            raise ValueError(f"mode debe ser uno de: {', '.join(DELETE_MODES)}")
        return v


class DeletionScheduled(SQLModel):
    delete_after: datetime
    access_token: Optional[str] = None   # el de esta sesión si se cerraron las otras


class TokenData(SQLModel):
    """Datos dentro del token"""
    email: Optional[str] = None


# ==================== Habit Schemas ====================

class HabitData(SQLModel):
    """Datos de hábitos para un día específico - campos dinámicos"""
    # Usaremos un dict para cualquier hábito
    pass


MAX_HABITS_PER_DAY = 100


class HabitEntryCreate(SQLModel):
    """Esquema para crear/actualizar entrada de hábitos"""
    date: date_type
    habits: Dict[str, bool] = Field(default={})

    @field_validator("habits")
    @classmethod
    def validate_habits(cls, v: Dict[str, bool]) -> Dict[str, bool]:
        # Las claves son las de los hábitos (máx. 40, como en HabitCreate). El
        # tope de claves es holgado: un día guarda también hábitos ya archivados.
        if len(v) > MAX_HABITS_PER_DAY:
            raise ValueError(f"Un día admite como máximo {MAX_HABITS_PER_DAY} hábitos")
        if any(not 1 <= len(k) <= 40 for k in v):
            raise ValueError("La clave de un hábito debe tener entre 1 y 40 caracteres")
        return v


class HabitMark(SQLModel):
    """Marcar o desmarcar UN hábito en un día (PATCH /api/habits/day/{fecha})."""
    habit_key: str = Field(min_length=1, max_length=40)
    done: bool


class HabitEntryResponse(SQLModel):
    """Esquema para respuesta de entrada de hábitos"""
    id: int
    date: date_type = Field(alias="entry_date")
    habits_data: Dict = Field(default={}, sa_type=JSON)

    model_config = ConfigDict(populate_by_name=True)


class HabitStats(SQLModel):
    """Estadísticas de hábitos - dinámicas"""
    pass


class MissedDay(SQLModel):
    """Ayer quedó sin hábitos (sin ser de descanso) y había racha."""
    date: date_type
    streak: int                       # la racha que había antes de ayer
    shielded: bool                    # True: la cubrió un protector; False: se cortó


class StreakResponse(SQLModel):
    """La racha general con sus protectores (ver _walk_streak en routers/habits.py)."""
    streak: int
    best_streak: int = 0              # la racha más larga del historial, misma regla
    streak_shields: int = 0           # protectores guardados (0..2)
    shield_next_in: Optional[int] = None   # días hechos que faltan para el próximo; None si ya hay 2
    protected_days: List[str] = []    # días que cubrió un protector (AAAA-MM-DD)
    missed_yesterday: Optional[MissedDay] = None
    habit_streaks: Dict[str, int] = {}   # racha actual de cada hábito, solo las > 0
    paused_days: List[str] = []       # días en pausa por vacaciones (AAAA-MM-DD), futuros incluidos


class UserHabitsResponse(StreakResponse):
    """Respuesta completa de hábitos del usuario"""
    entries: list
    stats: Dict = Field(default={})  # Dict[str, int]


# ==================== Habit Definition Schemas ====================

class HabitCreate(SQLModel):
    """
    Esquema para crear un nuevo hábito.
    El frontend envía estos datos al registrar un hábito nuevo.
    """
    # Los topes siguen al campo del formulario (maxlength="40"); el del emoji
    # deja sitio a las secuencias compuestas (👨‍👩‍👧 son varios code points).
    key: str = Field(min_length=1, max_length=40)    # Clave única por usuario (ej: "lectura")
    label: str = Field(min_length=1, max_length=40)  # Nombre visible (ej: "Lectura")
    icon: Optional[str] = Field(default=None, max_length=16)  # Emoji (ej: "📚")
    color: Optional[str] = None       # Hex color (ej: "#3498db")
    order: Optional[int] = None       # Posición en la UI; sin ella, va al final

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class HabitUpdate(SQLModel):
    """
    Esquema para actualizar un hábito existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    icon: Optional[str] = Field(default=None, max_length=16)
    color: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None  # False = archivar (no borra datos históricos)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


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

    model_config = ConfigDict(from_attributes=True)


class HabitReportItem(SQLModel):
    """Un hábito en el reporte de un rango"""
    key: str
    label: str
    icon: Optional[str] = None
    color: Optional[str] = None
    days_done: int                    # días del rango en que se marcó
    current_streak: int               # racha de este hábito hasta hoy
    best_streak: int                  # la más larga de su historial


class HabitReportResponse(SQLModel):
    """
    Hábitos en un rango de fechas locales. Las rachas siguen la regla de
    _walk_streak (hoy no corta, los días de descanso congelan, los protectores
    cubren días perdidos; cada hábito gana los suyos).
    """
    days_elapsed: int                 # días del rango hasta hoy, incluido
    rest_days_elapsed: int            # de esos, cuántos son de descanso
    paused_days_elapsed: int = 0      # y cuántos en pausa (sin contar los de descanso)
    active_days: int                  # días del rango con algún hábito hecho
    streak: int                       # racha general (la del calendario)
    best_streak: int
    streak_shields: int = 0           # protectores de la racha general
    habits: List[HabitReportItem]




# Rango máximo de un export de hábitos: un año (cada día × cada hábito es una fila)
MAX_HABIT_EXPORT_DAYS = 366


class HabitExportRow(SQLModel):
    """Un hábito en un día del export. `day_kind` dice por qué un día sin nada no
    rompe la racha: descanso, vacaciones, festivo (que se descansa), escudo
    (protector), hoy (en curso), o vacío si es un día normal."""
    date: date_type
    habit_key: str
    label: str
    icon: Optional[str] = None
    done: bool
    day_kind: str = ""
    note: str = ""            # la nota de ese hábito ese día (1.25)


# Una nota de un hábito en un día: corta, para control propio
MAX_HABIT_NOTE = 200
MAX_HABIT_NOTES_RANGE_DAYS = 366


class HabitNoteUpdate(SQLModel):
    """La nota de un hábito en un día. Vacía (o solo espacios): se borra."""
    text: str = Field(default="", max_length=MAX_HABIT_NOTE)


class HabitNoteResponse(SQLModel):
    habit_key: str
    date: date_type
    text: str


class HabitNoteListResponse(SQLModel):
    notes: List[HabitNoteResponse]


class HabitExportResponse(SQLModel):
    """Una fila por día y hábito del rango (fechas LOCALES, hasta hoy). Los
    hábitos: los activos y los ocultos con algún registro en el rango, en orden
    (order, id), como el calendario."""
    date_from: date_type
    date_to: date_type
    rows: List[HabitExportRow]


# Una pausa por vacaciones dura como mucho esto (Apple permite 90; aquí se decidió 30)
MAX_PAUSE_DAYS = 30


class PauseCreate(SQLModel):
    """Programar una pausa por vacaciones: fechas LOCALES, las dos incluidas."""
    start_date: date_type
    end_date: date_type

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("La pausa no puede terminar antes de empezar")
        if (self.end_date - self.start_date).days + 1 > MAX_PAUSE_DAYS:
            raise ValueError(f"Una pausa dura como mucho {MAX_PAUSE_DAYS} días")
        return self


class PauseResponse(SQLModel):
    id: int
    start_date: date_type
    end_date: date_type

    model_config = ConfigDict(from_attributes=True)


class PauseListResponse(SQLModel):
    pauses: List[PauseResponse]


class DeleteImpact(SQLModel):
    """Qué cambiaría al borrar un hábito: sus registros se van y, con ellos, los
    días en que fue lo único hecho."""
    records: int                      # días en que estaba marcado
    streak_before: int
    streak_after: int
    best_before: int
    best_after: int


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

    model_config = ConfigDict(from_attributes=True)


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


# ==================== Project Schemas ====================

class ProjectCreate(SQLModel):
    """Esquema para crear un proyecto"""
    # Los topes siguen a los formularios (maxlength); el del icono, como el de
    # los hábitos, deja sitio a los emojis compuestos
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=200)
    color: Optional[str] = None
    icon: Optional[str] = Field(default=None, max_length=16)
    order: Optional[int] = 0

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ProjectUpdate(SQLModel):
    """
    Esquema para actualizar un proyecto existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=200)
    color: Optional[str] = None
    icon: Optional[str] = Field(default=None, max_length=16)
    order: Optional[int] = None
    is_active: Optional[bool] = None  # False = archivar (conserva las tareas)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class ProjectResponse(SQLModel):
    """Esquema de respuesta para un proyecto"""
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    order: int
    is_active: bool
    is_system: bool = False           # "Sin asignar": no se renombra, archiva ni borra
    created_at: date_type

    model_config = ConfigDict(from_attributes=True)


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


# Monedas que acepta el costeo de un proyecto (ISO 4217). Lista cerrada: el
# frontend formatea con Intl.NumberFormat, que necesita un código válido.
CURRENCIES = ("MXN", "USD", "EUR", "CAD", "GBP", "COP", "ARS", "CLP", "PEN")
MAX_MONEY_CENTS = 100_000_000_000      # mil millones en la unidad de la moneda
MAX_BUDGET_MINUTES = 1_000_000         # ~16,600 horas


# Un proyecto personal no se cobra: sin cliente ni precio (los guarda, no los pide)
PROJECT_KINDS = ("personal", "product", "service")


class ProjectFinanceUpdate(SQLModel):
    """Costeo de un proyecto (PUT parcial): solo cambia lo que se manda, y null
    borra ese dato."""
    client_name: Optional[str] = Field(default=None, max_length=120)
    hourly_rate_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    currency: Optional[str] = None
    budget_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    budget_minutes: Optional[int] = Field(default=None, ge=0, le=MAX_BUDGET_MINUTES)
    kind: Optional[str] = None
    price_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CURRENCIES:
            raise ValueError(f"Moneda no válida. Usa una de: {', '.join(CURRENCIES)}")
        return v

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PROJECT_KINDS:
            raise ValueError(f"Tipo no válido. Usa uno de: {', '.join(PROJECT_KINDS)}")
        return v


MAX_COST_QUANTITY = 1_000_000
MAX_IMPORT_ROWS = 500


class CostCategoryCreate(SQLModel):
    """Categoría de gasto nueva (plan maker)"""
    name: str = Field(min_length=1, max_length=40)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class CostCategoryUpdate(SQLModel):
    """Renombrar, recolorear u ordenar una categoría de gasto (PATCH parcial)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = Field(default=None, ge=0, le=10_000)

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class CostCategoryResponse(SQLModel):
    id: int
    name: str
    color: Optional[str] = None
    order: int
    cost_count: int = 0      # cuántos gastos la usan: con alguno, no se borra

    model_config = ConfigDict(from_attributes=True)


class CostCategoryListResponse(SQLModel):
    categories: List[CostCategoryResponse]


class ProjectCostFields(SQLModel):
    """Lo que el usuario escribe de un gasto. El total no se manda: se calcula."""
    category_id: int
    cost_date: date_type
    concept: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0, le=MAX_COST_QUANTITY)
    unit_cost_cents: int = Field(default=0, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)


class ProjectCostCreate(ProjectCostFields):
    project_id: int


class ProjectCostUpdate(SQLModel):
    """Editar un gasto celda por celda (PATCH parcial)"""
    category_id: Optional[int] = None
    cost_date: Optional[date_type] = None
    concept: Optional[str] = Field(default=None, min_length=1, max_length=200)
    quantity: Optional[float] = Field(default=None, gt=0, le=MAX_COST_QUANTITY)
    unit_cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)


class ProjectCostImport(SQLModel):
    """Varios gastos de una vez (pegados de una hoja o de un CSV, ya revisados
    en la vista previa). O entran todos o ninguno."""
    project_id: int
    rows: List[ProjectCostFields] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)


class ProjectCostResponse(SQLModel):
    id: int
    project_id: int
    category_id: int
    cost_date: date_type
    concept: str
    quantity: float
    unit_cost_cents: int
    total_cents: int          # lo de este proyecto: su parte si está repartido
    note: Optional[str] = None
    # Repartido (1.24): su porcentaje en puntos base, el total del gasto entero y
    # con qué proyectos se reparte ([{project_id, name, bp}], este incluido)
    split_id: Optional[int] = None
    split_bp: Optional[int] = None
    group_total_cents: Optional[int] = None
    split_with: List[Dict] = []
    recurring_id: Optional[int] = None    # 🔁 lo generó un gasto recurrente


# Un gasto se reparte entre hasta 10 proyectos de la misma moneda
MAX_SPLIT_PROJECTS = 10
RECURRING_FREQUENCIES = ("monthly", "yearly")
RECURRING_APPLY_TO = ("future", "current", "all")


class CostAllocation(SQLModel):
    """La parte de un proyecto en un gasto, en puntos base (6500 = 65 %)"""
    project_id: int
    bp: int = Field(ge=1, le=10000)


def _validate_allocations(v: Optional[List[CostAllocation]]) -> Optional[List[CostAllocation]]:
    if v is None:
        return v
    if not 1 <= len(v) <= MAX_SPLIT_PROJECTS:
        raise ValueError(f"Reparte entre 1 y {MAX_SPLIT_PROJECTS} proyectos")
    if len({a.project_id for a in v}) != len(v):
        raise ValueError("Un proyecto aparece dos veces en el reparto")
    if sum(a.bp for a in v) != 10000:
        raise ValueError("Los porcentajes del reparto tienen que sumar 100 %")
    return v


class CostSplitUpdate(SQLModel):
    """Repartir un gasto (o cambiar su reparto). Con un solo proyecto al 100 %,
    deja de estar repartido."""
    allocations: List[CostAllocation]

    @field_validator("allocations")
    @classmethod
    def validate_allocations(cls, v):
        return _validate_allocations(v)


class RecurringCostFields(SQLModel):
    category_id: int
    concept: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0, le=MAX_COST_QUANTITY)
    unit_cost_cents: int = Field(default=0, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)
    frequency: str = "monthly"
    start_date: date_type
    end_date: Optional[date_type] = None
    allocations: List[CostAllocation]
    # "Hacer recurrente" desde un gasto de la hoja: ese gasto queda con el 🔁, y
    # si el primer cobro es su misma fecha, cuenta como ese cobro (no se duplica)
    from_cost_id: Optional[int] = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in RECURRING_FREQUENCIES:
            raise ValueError(f"frequency debe ser uno de: {', '.join(RECURRING_FREQUENCIES)}")
        return v

    @field_validator("allocations")
    @classmethod
    def validate_allocations(cls, v):
        return _validate_allocations(v)


class RecurringCostUpdate(SQLModel):
    """Cambiar un recurrente: solo afecta a los cobros siguientes"""
    category_id: Optional[int] = None
    concept: Optional[str] = Field(default=None, min_length=1, max_length=200)
    quantity: Optional[float] = Field(default=None, gt=0, le=MAX_COST_QUANTITY)
    unit_cost_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)
    frequency: Optional[str] = None
    first_day: Optional[int] = Field(default=None, ge=1, le=31)
    second_day: Optional[int] = Field(default=None, ge=1, le=31)
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    paused: Optional[bool] = None
    allocations: Optional[List[CostAllocation]] = None
    # A qué cobros ya anotados se aplican los cambios: ninguno ("future", los
    # siguientes), los del periodo actual en adelante ("current") o todos ("all")
    apply_to: str = "future"
    # Con una fecha de fin anterior a cobros ya anotados: borrarlos (la pantalla
    # lo pregunta). Sin esto, se quedan como estaban
    drop_after_end: bool = False

    @field_validator("apply_to")
    @classmethod
    def validate_apply_to(cls, v: str) -> str:
        if v not in RECURRING_APPLY_TO:
            raise ValueError(f"apply_to debe ser uno de: {', '.join(RECURRING_APPLY_TO)}")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RECURRING_FREQUENCIES:
            raise ValueError(f"frequency debe ser uno de: {', '.join(RECURRING_FREQUENCIES)}")
        return v

    @field_validator("allocations")
    @classmethod
    def validate_allocations(cls, v):
        return _validate_allocations(v)


class RecurringCostResponse(SQLModel):
    id: int
    category_id: int
    concept: str
    quantity: float
    unit_cost_cents: int
    total_cents: int
    note: Optional[str] = None
    frequency: str
    start_date: date_type
    end_date: Optional[date_type] = None
    paused: bool
    next_date: Optional[date_type] = None   # el siguiente cobro (None: ya terminó)
    generated: int                          # cobros ya generados
    last_charge: Optional[date_type] = None # el último gasto anotado: el siguiente va después
    currency: str
    allocations: List[Dict]                 # [{project_id, name, bp}]


class RecurringCostListResponse(SQLModel):
    recurring: List[RecurringCostResponse]


class ProjectCostListResponse(SQLModel):
    costs: List[ProjectCostResponse]   # del más reciente al más antiguo
    total_cents: int
    currency: str


class CostsProjectSummary(SQLModel):
    """Una fila del resumen de la pestaña Costos"""
    project_id: int
    name: str
    color: Optional[str] = None
    is_active: bool
    currency: str
    total_seconds: int
    hourly_rate_cents: Optional[int] = None
    labor_cents: Optional[int] = None
    costs_cents: int
    total_cost_cents: int                 # mano de obra (si hay tarifa) + gastos
    budget_cents: Optional[int] = None
    budget_left_cents: Optional[int] = None   # presupuesto disponible: presupuesto − costo
    kind: Optional[str] = None
    price_cents: Optional[int] = None
    margin_cents: Optional[int] = None        # precio − costo, solo con precio
    is_quote: bool = False
    # Gasto por categoría de este proyecto, para filtrar la gráfica "Costos"
    categories: List[Dict[str, int]] = []


class CostsCategorySummary(SQLModel):
    category_id: int
    name: str
    color: Optional[str] = None
    currency: str
    cents: int


class CostsCurrencyTotal(SQLModel):
    """Totales de una moneda: no se convierte entre monedas, nunca se suman"""
    currency: str
    labor_cents: int
    costs_cents: int
    total_cost_cents: int
    budget_cents: int


class CostsSummaryResponse(SQLModel):
    projects: List[CostsProjectSummary]
    categories: List[CostsCategorySummary]   # por moneda, de mayor a menor
    totals: List[CostsCurrencyTotal]


class ProjectFinanceResponse(SQLModel):
    """
    Costeo de un proyecto y lo que sale de cruzarlo con su tiempo de enfoque
    (el mismo total que /summary). Los porcentajes son null sin presupuesto.
    """
    project_id: int
    client_name: Optional[str] = None
    hourly_rate_cents: Optional[int] = None
    currency: str = "MXN"
    budget_cents: Optional[int] = None
    budget_minutes: Optional[int] = None
    total_seconds: int
    labor_cents: Optional[int] = None         # horas × tarifa, redondeado al centavo
    budget_money_pct: Optional[int] = None    # mano de obra ÷ presupuesto en dinero
    budget_time_pct: Optional[int] = None     # tiempo ÷ presupuesto en tiempo
    is_quote: bool = False                    # con presupuesto y sin tiempo todavía
    # Fase 3: los gastos del proyecto y lo que suman con la mano de obra
    costs_cents: int = 0
    total_cost_cents: int = 0                 # mano de obra (si hay tarifa) + gastos
    budget_left_cents: Optional[int] = None   # presupuesto disponible: presupuesto − costo
    # Fase 6 (épica 30): tipo y precio; el margen es precio − costo, solo con precio
    kind: Optional[str] = None
    price_cents: Optional[int] = None
    margin_cents: Optional[int] = None


# ==================== Estimado contra real (épica 24, Fase 4) ====================

ESTIMATE_MAX_MINUTES = 6000   # 100 h: más que eso suele ser un proyecto, no una tarea


class EstimateRow(SQLModel):
    """Real contra estimado de un grupo de tareas. ratio_pct = real × 100 ÷
    estimado (enteros, .5 hacia arriba); None con menos de min_tasks tareas:
    con tan poco historial la cifra no diría nada."""
    tasks: int
    estimate_seconds: int
    actual_seconds: int
    ratio_pct: Optional[int] = None


class EstimateTagRow(EstimateRow):
    """Una etiqueta: una tarea con dos etiquetas cuenta en las dos, así que
    estas filas NO se suman entre sí"""
    tag_id: int
    name: str
    color: Optional[str] = None


class EstimateDeviation(SQLModel):
    """Cuánto se desvía el usuario de lo que estima. Cuentan las tareas con
    estimado y tiempo: las terminadas y las abiertas que ya lo pasaron."""
    min_tasks: int
    overall: EstimateRow              # cada tarea una vez
    tags: List[EstimateTagRow]        # las de más tareas primero
    untagged: EstimateRow


class OverviewTask(SQLModel):
    """Una tarea en la ficha del proyecto, con su tiempo de enfoque"""
    id: int
    title: str
    is_done: bool
    seconds: int
    estimate_minutes: Optional[int] = None


class OverviewTag(SQLModel):
    """Tiempo del proyecto en tareas con esta etiqueta. Una sesión cuenta en
    cada etiqueta de su tarea: estos totales NO se suman entre sí."""
    tag_id: int
    name: str
    color: Optional[str] = None
    seconds: int


class OverviewMonth(SQLModel):
    """Tiempo del proyecto en un mes ("AAAA-MM", por session_date: la fecha local)"""
    month: str
    seconds: int


class ProjectOverview(SQLModel):
    """
    Ficha de un proyecto (épica 24, Fase 1): todo su tiempo de enfoque, con
    el mismo criterio que /api/projects/summary, para que las cifras cuadren
    con la Lista y Reportes. Vale también para proyectos archivados.
    """
    project: ProjectResponse
    total_seconds: int
    session_count: int
    task_total: int
    task_done: int
    tasks: List[OverviewTask]          # todas, las de más tiempo primero
    seconds_no_task: int               # tiempo registrado sin tarea
    tags: List[OverviewTag]            # las de más tiempo primero
    untagged_seconds: int              # sesiones sin etiqueta (o sin tarea)
    months: List[OverviewMonth]        # del más antiguo al más reciente
    first_date: Optional[date_type] = None   # primera y última sesión
    last_date: Optional[date_type] = None
    # Solo con el plan maker encendido (y nunca en "Sin asignar")
    finance: Optional[ProjectFinanceResponse] = None
    # Solo con el plan maker encendido: el estimado es de todos, el desvío no
    estimates: Optional[EstimateDeviation] = None


# ==================== Task Schemas ====================

TASK_NOTES_MAX = 5000


class TaskCreate(SQLModel):
    """Esquema para crear una tarea"""
    project_id: Optional[int] = None  # sin él, "Sin asignar"
    title: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=TASK_NOTES_MAX)
    order: Optional[int] = None       # sin él, al final de su columna
    column_id: Optional[int] = None   # columna exacta; manda sobre board_id
    board_id: Optional[int] = None    # sin column_id: la primera "todo" de este tablero
    tag_ids: Optional[List[int]] = None


class TaskUpdate(SQLModel):
    """
    Esquema para actualizar una tarea existente.
    Todos los campos son opcionales (PATCH parcial).
    """
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=TASK_NOTES_MAX)
    is_done: Optional[bool] = None
    order: Optional[int] = None
    project_id: Optional[int] = None  # cambiar el proyecto; null = "Sin asignar"
    column_id: Optional[int] = None   # mover la tarea de columna (o de tablero); manda sobre is_done
    tag_ids: Optional[List[int]] = None  # reemplaza TODAS las etiquetas; [] las quita
    # Minutos; null lo borra. Para todos, con o sin el plan maker
    estimate_minutes: Optional[int] = Field(default=None, ge=1, le=ESTIMATE_MAX_MINUTES)


class TaskReorder(SQLModel):
    """El orden completo de una columna, de arriba abajo, tras arrastrar una tarjeta."""
    column_id: int
    task_ids: List[int]


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
    estimate_minutes: Optional[int] = None

    # Para pintar la tarjeta sin pedir el detalle de cada tarea
    checklist_total: int = 0
    checklist_done: int = 0
    comment_count: int = 0
    tag_ids: List[int] = []
    seconds: int = 0                  # tiempo de foco registrado, sea cual sea su proyecto

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

POMODORO_MODES = ("focus", "short_break", "long_break")


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
    note: Optional[str] = Field(default=None, max_length=200)
    source: Optional[str] = "timer"
    # El sessionId del timer (pomodoro.js). Mismo usuario y misma clave = la
    # misma sesión: el segundo POST devuelve la primera en vez de duplicarla.
    idempotency_key: Optional[str] = Field(default=None, max_length=64)
    # Un cronómetro que llegó al tope de 8 h sin que nadie dijera cuánto se trabajó
    needs_review: Optional[bool] = False

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        # El cronómetro se guarda como "focus": solo existen estos tres
        if v is not None and v not in POMODORO_MODES:
            raise ValueError(f"mode debe ser uno de: {', '.join(POMODORO_MODES)}")
        return v

    @field_validator("idempotency_key")
    @classmethod
    def blank_key_is_none(cls, v: Optional[str]) -> Optional[str]:
        # Una clave vacía no identifica nada: sin ella no se deduplica
        if v is None:
            return None
        return v.strip() or None


class PomodoroSessionUpdate(SQLModel):
    """
    Esquema para corregir una sesión ya registrada (PATCH parcial).
    El origen no se cambia. El proyecto no se manda: sigue a la tarea.
    """
    # false = "Está bien": confirmar tal cual. Corregir horas o duración también
    # la confirma (routers/pomodoro.py), sin mandar este campo.
    needs_review: Optional[bool] = None
    task_id: Optional[int] = None
    session_date: Optional[date_type] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=200)


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
    needs_review: bool = False
    created_at: date_type

    model_config = ConfigDict(from_attributes=True)


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


# ==================== Calendario de trabajo (épica 30) ====================

DAY_KINDS = ("libre", "laboral")


class WorkSettingsResponse(SQLModel):
    timezone: str
    country: str
    configured: bool          # False: aún no se guardó; valen los de por defecto


class WorkSettingsUpdate(SQLModel):
    timezone: Optional[str] = Field(default=None, max_length=64)
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.upper()
        if not re.fullmatch(r"[A-Z]{2}", v):
            raise ValueError("El país es un código de dos letras, como MX")
        return v


class UserDayCreate(SQLModel):
    """Marcar un día a mano: libre (no se trabaja) o laboral (sí, aunque sea festivo)"""
    date: date_type
    kind: str = "libre"
    name: Optional[str] = Field(default=None, max_length=80)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in DAY_KINDS:
            raise ValueError(f"kind debe ser uno de: {', '.join(DAY_KINDS)}")
        return v


class UserDayResponse(SQLModel):
    id: int
    date: date_type
    kind: str
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OfficialDay(SQLModel):
    date: date_type
    name: str
    observed: bool = True     # False si el usuario lo marcó "laboral"


class YearDaysResponse(SQLModel):
    """Los festivos oficiales del año (de Nager.Date) y los días que marcó el usuario"""
    year: int
    country: str
    official: List[OfficialDay]
    own: List[UserDayResponse]


# ==================== Reportes guardados (épica 30, Fase 4) ====================

from backend.report_kinds import KINDS as REPORT_KINDS  # noqa: E402  (tiempo, hábitos y costos)


class ReportCreate(SQLModel):
    """Generar (o regenerar) el reporte de un periodo: semana desde su lunes, mes desde su día 1"""
    kind: str
    period_start: date_type
    today: Optional[date_type] = None   # fecha LOCAL del cliente (resolve_client_today)
    use_ai: bool = True                 # con la IA encendida, que ella escriba los pasos y el tip

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in REPORT_KINDS:
            raise ValueError(f"kind debe ser uno de: {', '.join(REPORT_KINDS)}")
        return v


class ReportSummary(SQLModel):
    """Una fila de la lista: sin cifras ni texto"""
    id: int
    kind: str
    subject: str = "time"       # time | habits | costs (backend/report_kinds.py)
    headline: str = ""          # la cifra de la fila: "12h 30m", "82 % de cumplimiento", "$1,250.00 MXN"
    period_start: date_type
    period_end: date_type
    through: date_type
    total_seconds: int
    trigger: str
    text_source: str
    text_model: Optional[str] = None
    text_note: Optional[str] = None
    created_at: datetime
    regenerate_in: int = 0      # segundos para poder volver a generarlo a mano


class ReportListResponse(SQLModel):
    reports: List[ReportSummary]


class ReportResponse(ReportSummary):
    metrics: Dict
    text: Dict


# ---------- Reportar un problema (1.27) ----------

FEEDBACK_MIN = 10
FEEDBACK_MAX = 2000
FEEDBACK_ERRORS_MAX = 10
# Lo único que pueden traer los detalles técnicos, con su tope. Lo arma feedback.js
# y el usuario lo ve antes de enviarlo; nada más entra (ni tokens ni datos suyos).
FEEDBACK_DETAIL_FIELDS = {"version": 20, "view": 20, "screen": 20, "user_agent": 300}
FEEDBACK_ERROR_MAX = 300


class FeedbackCreate(SQLModel):
    """Un problema reportado: qué pasó y, si el usuario quiso, detalles técnicos."""
    text: str = Field(max_length=FEEDBACK_MAX)
    details: Optional[Dict] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        v = v.strip()
        if len(v) < FEEDBACK_MIN:
            raise ValueError(f"Cuéntanos un poco más: al menos {FEEDBACK_MIN} caracteres.")
        return v

    @field_validator("details")
    @classmethod
    def validate_details(cls, v: Optional[Dict]) -> Optional[Dict]:
        if v is None:
            return None
        unknown = set(v) - set(FEEDBACK_DETAIL_FIELDS) - {"errors"}
        if unknown:
            raise ValueError(f"Detalles no admitidos: {', '.join(sorted(unknown))}")
        clean = {}
        for key, cap in FEEDBACK_DETAIL_FIELDS.items():
            if key in v and v[key] is not None:
                if not isinstance(v[key], str) or len(v[key]) > cap:
                    raise ValueError(f"{key}: texto de hasta {cap} caracteres")
                clean[key] = v[key]
        errors = v.get("errors") or []
        if (not isinstance(errors, list) or len(errors) > FEEDBACK_ERRORS_MAX
                or any(not isinstance(e, str) or len(e) > FEEDBACK_ERROR_MAX for e in errors)):
            raise ValueError(f"errors: hasta {FEEDBACK_ERRORS_MAX} textos de hasta {FEEDBACK_ERROR_MAX} caracteres")
        if errors:
            clean["errors"] = errors
        return clean or None


class FeedbackResponse(SQLModel):
    id: int
    created_at: datetime


# ==================== Finanzas personales (épica 37) ====================

# investment: una cuenta de inversión (CETES, una casa de bolsa, un exchange); se
# porta como débito, pero se lista en Cuentas › Inversiones
FIN_ACCOUNT_KINDS = ("cash", "debit", "credit", "investment")
FIN_CATEGORY_KINDS = ("expense", "income")
FIN_TX_KINDS = ("expense", "income", "transfer")
# La quincenal (el 15 y el último día) es solo de Finanzas: el sueldo
FIN_FREQUENCIES = ("monthly", "yearly", "semimonthly")
FIN_PERIODS = ("month", "biweekly")
# Los iconos de Finanzas (Lucide, en finance-icons.js): un icono nuevo va en los dos
FIN_ICONS = (
    "baby",
    "banknote",
    "beer",
    "bike",
    "book-open",
    "briefcase",
    "bus",
    "car",
    "coffee",
    "credit-card",
    "droplet",
    "dumbbell",
    "ellipsis",
    "film",
    "flame",
    "fuel",
    "gamepad-2",
    "gift",
    "graduation-cap",
    "hand-coins",
    "heart-handshake",
    "heart-pulse",
    "house",
    "landmark",
    "paw-print",
    "piggy-bank",
    "pill",
    "plane",
    "receipt",
    "scissors",
    "shirt",
    "shopping-bag",
    "shopping-basket",
    "smartphone",
    "sparkles",
    "ticket",
    "train-front",
    "trending-up",
    "tv",
    "utensils",
    "wallet",
    "wifi",
    "wrench",
    "zap",
)


def _one_of(value: Optional[str], allowed: tuple, field: str) -> Optional[str]:
    if value is not None and value not in allowed:
        raise ValueError(f"{field} debe ser uno de: {', '.join(allowed)}")
    return value


def _validate_last4(v: Optional[str]) -> Optional[str]:
    # Nunca el número completo: como mucho los últimos 4 dígitos
    if v is not None and not re.fullmatch(r"\d{4}", v):
        raise ValueError("Escribe solo los últimos 4 dígitos")
    return v


class FinAccountCreate(SQLModel):
    name: str = Field(min_length=1, max_length=40)
    kind: str = "cash"
    currency: str = "MXN"
    last4: Optional[str] = None
    is_default: bool = False
    icon: Optional[str] = None
    color: Optional[str] = None
    opening_balance_cents: int = Field(default=0, ge=-MAX_MONEY_CENTS, le=MAX_MONEY_CENTS)
    # El día de ese saldo; sin él, con saldo, hoy
    opening_date: Optional[date_type] = None
    # Solo crédito (en otra cuenta se ignoran)
    credit_limit_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    statement_day: Optional[int] = Field(default=None, ge=1, le=31)
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    # Tasa de interés anual de la tarjeta, de referencia (en puntos base: 4500 = 45 %)
    interest_rate_bp: Optional[int] = Field(default=None, ge=0, le=100_000)
    # Un apartado de esa cuenta: toma su moneda y su tipo
    parent_id: Optional[int] = None

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        return _one_of(v, FIN_ICONS, "icon")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        return _validate_hex_color(v)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_ACCOUNT_KINDS, "kind")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        return _one_of(v, CURRENCIES, "currency")

    @field_validator("last4")
    @classmethod
    def validate_last4(cls, v):
        return _validate_last4(v)


class FinAccountUpdate(SQLModel):
    """PATCH parcial. is_default solo acepta true: la de por defecto se cambia
    eligiendo otra. last4 en null lo borra."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    kind: Optional[str] = None
    currency: Optional[str] = None
    last4: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    order: Optional[int] = Field(default=None, ge=0, le=10_000)
    icon: Optional[str] = None
    color: Optional[str] = None
    opening_balance_cents: Optional[int] = Field(default=None, ge=-MAX_MONEY_CENTS, le=MAX_MONEY_CENTS)
    opening_date: Optional[date_type] = None   # null: cuentan todos los movimientos
    credit_limit_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    statement_day: Optional[int] = Field(default=None, ge=1, le=31)
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    interest_rate_bp: Optional[int] = Field(default=None, ge=0, le=100_000)
    parent_id: Optional[int] = None            # null: vuelve a ser cuenta suelta

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        return _one_of(v, FIN_ICONS, "icon")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        return _validate_hex_color(v)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_ACCOUNT_KINDS, "kind")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        return _one_of(v, CURRENCIES, "currency")

    @field_validator("last4")
    @classmethod
    def validate_last4(cls, v):
        return _validate_last4(v)


class FinAccountResponse(SQLModel):
    id: int
    name: str
    kind: str
    currency: str
    last4: Optional[str] = None
    is_default: bool
    is_active: bool
    order: int
    tx_count: int = 0         # con alguno, no se borra: se archiva
    icon: Optional[str] = None
    color: Optional[str] = None
    opening_balance_cents: int = 0
    opening_date: Optional[date_type] = None
    credit_limit_cents: Optional[int] = None
    statement_day: Optional[int] = None
    due_day: Optional[int] = None
    # Los movimientos de antes de opening_date: historial que no mueve el saldo
    before_count: int = 0
    before_in_cents: int = 0      # ingresos, pagos y transferencias que llegaron
    before_out_cents: int = 0     # gastos, cargos y transferencias que salieron
    # El saldo a hoy (saldo inicial más movimientos hasta hoy); en crédito,
    # negativo es deuda. Disponible: límite + saldo, solo con límite.
    balance_cents: int = 0
    available_cents: Optional[int] = None
    parent_id: Optional[int] = None   # un apartado: la cuenta de la que cuelga
    interest_rate_bp: Optional[int] = None   # crédito: la tasa anual, de referencia
    cancelled_on: Optional[date_type] = None  # una tarjeta dada de baja: el día
    # Con tasa de rendimiento: la de hoy y lo ganado sin anotar (desde yield_since hasta ayer)
    yield_rate_bp: Optional[int] = None
    yield_since: Optional[date_type] = None
    yield_estimate_cents: Optional[int] = None
    # En plazos fijos abiertos: cuánto no está disponible y hasta cuándo (el primero que vence)
    term_locked_cents: int = 0
    term_until: Optional[date_type] = None


class FinAccountListResponse(SQLModel):
    accounts: List[FinAccountResponse]


class FinYieldRateFields(SQLModel):
    """Una tasa anual desde un día (la misma fecha la reemplaza). 0 = ya no gana."""
    from_date: date_type
    rate_bp: int = Field(ge=0, le=10_000)
    cap_cents: Optional[int] = Field(default=None, ge=1, le=MAX_MONEY_CENTS)
    day_basis: int = 365

    @field_validator("day_basis")
    @classmethod
    def validate_day_basis(cls, v):
        if v not in (365, 360):
            raise ValueError("day_basis debe ser 365 o 360")
        return v


class FinYieldRateResponse(FinYieldRateFields):
    id: int


class FinYieldResponse(SQLModel):
    account_id: int
    rates: List[FinYieldRateResponse]
    rate_bp: Optional[int] = None         # la de hoy
    cap_cents: Optional[int] = None
    since: Optional[date_type] = None
    through: Optional[date_type] = None
    estimate_cents: Optional[int] = None


FIN_TERM_ON_MATURITY = ("stay", "return", "renew")


class FinTermFields(SQLModel):
    """Un plazo fijo. Al vencer: se queda en la cuenta (stay), regresa a otra
    (return, con return_account_id) o se reinvierte (renew)."""
    account_id: int
    concept: str = Field(default="Plazo fijo", min_length=1, max_length=80)
    principal_cents: int = Field(ge=1, le=MAX_MONEY_CENTS)
    start_date: date_type
    days: int = Field(ge=1, le=3650)
    rate_bp: int = Field(ge=0, le=10_000)
    day_basis: int = 360
    on_maturity: str = "stay"
    return_account_id: Optional[int] = None

    @field_validator("day_basis")
    @classmethod
    def validate_day_basis(cls, v):
        if v not in (365, 360):
            raise ValueError("day_basis debe ser 365 o 360")
        return v

    @field_validator("on_maturity")
    @classmethod
    def validate_on_maturity(cls, v):
        return _one_of(v, FIN_TERM_ON_MATURITY, "on_maturity")


class FinTermResponse(FinTermFields):
    id: int
    maturity_date: date_type
    interest_cents: int
    matured: bool


class FinTermListResponse(SQLModel):
    terms: List[FinTermResponse]


FIN_NOTE_BODY_MAX = 10_000


class FinNoteFields(SQLModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=FIN_NOTE_BODY_MAX)


class FinNoteUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=80)
    body: Optional[str] = Field(default=None, max_length=FIN_NOTE_BODY_MAX)


class FinNoteResponse(FinNoteFields):
    id: int
    updated_at: datetime


class FinNoteListResponse(SQLModel):
    notes: List[FinNoteResponse]


class FinYieldRecord(SQLModel):
    """Anotar el rendimiento: sin monto, el estimado; con monto, el del banco."""
    amount_cents: Optional[int] = Field(default=None, ge=1, le=MAX_MONEY_CENTS)
    tx_date: Optional[date_type] = None


class FinCategoryCreate(SQLModel):
    name: str = Field(min_length=1, max_length=40)
    color: Optional[str] = None
    kind: str = "expense"
    icon: Optional[str] = None

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        return _one_of(v, FIN_ICONS, "icon")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        return _validate_hex_color(v)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_CATEGORY_KINDS, "kind")


class FinCategoryUpdate(SQLModel):
    """Renombrar, recolorear u ordenar. El tipo no cambia: sus movimientos son de ese tipo."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    color: Optional[str] = None
    order: Optional[int] = Field(default=None, ge=0, le=10_000)
    icon: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        return _validate_hex_color(v)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        return _one_of(v, FIN_ICONS, "icon")


class FinCategoryResponse(SQLModel):
    id: int
    name: str
    color: Optional[str] = None
    kind: str
    order: int
    tx_count: int = 0
    icon: Optional[str] = None
    # La cuenta que la hoja del monto propone para ella (la más usada en sus últimos movimientos)
    usual_account_id: Optional[int] = None


class FinCategoryListResponse(SQLModel):
    categories: List[FinCategoryResponse]
    # La última cuenta de un gasto y de un ingreso: lo que se propone sin categoría con historial
    last_expense_account_id: Optional[int] = None
    last_income_account_id: Optional[int] = None


FIN_MAX_SPLITS = 20
FIN_MAX_INSTALLMENT_MONTHS = 48
# Un tope para la lista del orden de categorías (nadie tiene tantas)
FIN_MAX_CATEGORIES = 200


class FinSplitFields(SQLModel):
    """Una parte de un movimiento dividido: su categoría y su monto."""
    category_id: int
    amount_cents: int = Field(gt=0, le=MAX_MONEY_CENTS)


class FinTransactionFields(SQLModel):
    """Un movimiento escrito a mano o pegado. Un gasto o un ingreso lleva
    categoría de su tipo, o partes (splits) que suman su monto; una
    transferencia, la cuenta de destino y ninguna."""
    kind: str = "expense"
    account_id: int
    amount_cents: int = Field(gt=0, le=MAX_MONEY_CENTS)
    tx_date: date_type
    category_id: Optional[int] = None
    to_account_id: Optional[int] = None
    concept: str = Field(min_length=1, max_length=200)
    note: Optional[str] = Field(default=None, max_length=500)
    splits: Optional[List[FinSplitFields]] = Field(default=None, max_length=FIN_MAX_SPLITS)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_TX_KINDS, "kind")


class FinTransactionUpdate(SQLModel):
    """PATCH parcial; needs_review en false lo confirma."""
    kind: Optional[str] = None
    account_id: Optional[int] = None
    amount_cents: Optional[int] = Field(default=None, gt=0, le=MAX_MONEY_CENTS)
    tx_date: Optional[date_type] = None
    category_id: Optional[int] = None
    to_account_id: Optional[int] = None
    concept: Optional[str] = Field(default=None, min_length=1, max_length=200)
    note: Optional[str] = Field(default=None, max_length=500)
    needs_review: Optional[bool] = None
    # Una lista las reemplaza; null las quita (y entonces lleva categoría)
    splits: Optional[List[FinSplitFields]] = Field(default=None, max_length=FIN_MAX_SPLITS)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_TX_KINDS, "kind")


# Importar datos trae el historial de otra app de una vez (más que un estado de cuenta)
FIN_MAX_IMPORT_ROWS = 5000


class FinTransactionImport(SQLModel):
    """Varios de una vez (el estado de cuenta pegado, o el historial de Importar
    datos), ya revisados en la vista previa. O entran todos o ninguno."""
    rows: List[FinTransactionFields] = Field(min_length=1, max_length=FIN_MAX_IMPORT_ROWS)


class FinTransactionResponse(SQLModel):
    id: int
    kind: str
    account_id: int
    to_account_id: Optional[int] = None
    category_id: Optional[int] = None
    amount_cents: int
    currency: str             # la de su cuenta
    tx_date: date_type
    concept: str
    note: Optional[str] = None
    source: str
    recurring_id: Optional[int] = None
    needs_review: bool = False
    splits: List[FinSplitFields] = []
    installment_id: Optional[int] = None    # si es una compra a meses


class FinInstallmentCreate(SQLModel):
    """Una compra a meses en una tarjeta de crédito. Con transaction_id, la compra
    ya anotada (su cuenta, fecha y monto mandan); sin él, solo el plan de pagos."""
    account_id: Optional[int] = None
    transaction_id: Optional[int] = None
    concept: Optional[str] = Field(default=None, min_length=1, max_length=200)
    total_cents: Optional[int] = Field(default=None, gt=0, le=MAX_MONEY_CENTS)
    # Una compra va de 2 meses en adelante; un plan sin compra (los meses que le
    # faltan a una deuda de antes de usar la app) puede tener 1
    months: int = Field(ge=1, le=FIN_MAX_INSTALLMENT_MONTHS)
    purchase_date: Optional[date_type] = None
    first_statement: Optional[date_type] = None   # sin él, el primer corte desde la compra
    # Copiado del estado de cuenta del banco (sin compra): el corte de ese estado de
    # cuenta y el número de pago que factura ("11 de 12"); el plan se arma desde ahí.
    # El pago requerido y el saldo pendiente, si vienen, se comprueban contra el plan
    bank_cut: Optional[date_type] = None
    bank_part: Optional[int] = Field(default=None, ge=1, le=FIN_MAX_INSTALLMENT_MONTHS)
    bank_monthly_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    bank_pending_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)


FIN_BUDGET_MAX_GROUPS = 20
FIN_BUDGET_MAX_ITEMS = 300
# Las referencias para empezar: solo crean grupos, que luego son del usuario
FIN_BUDGET_TEMPLATES = {
    "50-30-20": [("Necesidades", 5000), ("Gustos", 3000), ("Ahorro y deudas", 2000)],
}


class FinBudgetGroupFields(SQLModel):
    name: str = Field(min_length=1, max_length=60)
    percent_bp: int = Field(default=0, ge=0, le=10000)


class FinBudgetGroupUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    percent_bp: Optional[int] = Field(default=None, ge=0, le=10000)
    order: Optional[int] = Field(default=None, ge=0, le=10_000)


class FinBudgetTemplate(SQLModel):
    template: str

    @field_validator("template")
    @classmethod
    def validate_template(cls, v):
        return _one_of(v, tuple(FIN_BUDGET_TEMPLATES), "template")


class FinBudgetItemFields(SQLModel):
    kind: str = "expense"
    group_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(default=0, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=200)
    category_id: Optional[int] = None
    recurring_id: Optional[int] = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_CATEGORY_KINDS, "kind")


class FinBudgetItemUpdate(SQLModel):
    """Lo que viene cambia; `null` en nota, categoría o fijo los quita."""
    group_id: Optional[int] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    amount_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=200)
    category_id: Optional[int] = None
    recurring_id: Optional[int] = None
    order: Optional[int] = Field(default=None, ge=0, le=10_000)


class FinBudgetGroupResponse(SQLModel):
    id: int
    name: str
    percent_bp: int
    order: int


class FinBudgetItemResponse(SQLModel):
    id: int
    kind: str
    group_id: Optional[int] = None
    name: str
    amount_cents: int
    note: Optional[str] = None
    category_id: Optional[int] = None
    recurring_id: Optional[int] = None
    order: int


class FinBudgetResponse(SQLModel):
    groups: List[FinBudgetGroupResponse]
    items: List[FinBudgetItemResponse]


class FinInstallmentBill(SQLModel):
    cut: date_type                # el corte que la pide
    part: int                     # 11 (de 12)
    amount_cents: int


class FinInstallmentResponse(SQLModel):
    id: int
    account_id: int
    transaction_id: Optional[int] = None
    concept: str
    total_cents: int
    currency: str
    months: int
    purchase_date: date_type
    first_statement: date_type
    monthly_cents: int            # la primera parte (las demás, igual o un centavo menos)
    billed: int                   # cuántas partes ya pidió algún corte hasta hoy
    remaining_cents: int          # lo que aún no se factura
    next_statement: Optional[date_type] = None
    bills: List[FinInstallmentBill] = []   # cada mensualidad, con su corte


class FinInstallmentListResponse(SQLModel):
    installments: List[FinInstallmentResponse]


class FinStatementInstallment(SQLModel):
    id: int
    concept: str
    part: int                     # 3 (de 12)
    months: int
    amount_cents: int


class FinStatementResponse(SQLModel):
    """El estado de cuenta de una tarjeta de crédito, calculado: el último corte,
    cuánto pagar antes del día de pago para no generar intereses y lo ya pagado."""
    account_id: int
    currency: str
    statement_day: int
    due_day: int
    last_cut: date_type
    prev_cut: date_type
    due_date: date_type
    next_cut: date_type
    debt_at_cut_cents: int        # lo que se debía al corte (MSI completos incluidos)
    msi_pending_cents: int        # mensualidades de MSI que aún no se facturan
    pay_no_interest_cents: int    # deuda al corte − MSI por facturar
    paid_since_cut_cents: int     # abonos y pagos después del corte
    remaining_cents: int          # lo que falta para no generar intereses
    cycle_charges_cents: int      # compras desde el corte (van al siguiente)
    installments: List[FinStatementInstallment] = []
    # True: el pago del último corte ya venció (o la cuenta se dio de alta
    # después de él) y esto es el PRÓXIMO corte: last_cut es ese corte futuro,
    # y la deuda, lo que lleva acumulado hasta hoy
    upcoming: bool = False
    # True: pay_no_interest_cents es el del estado de cuenta del banco (lo
    # escribió el usuario); estimated_cents, el que calculó la app
    from_bank: bool = False
    estimated_cents: int = 0
    # El aviso del pago (Finanzas 0.8): días que faltan para due_date y si ya toca avisar
    # (queda algo por pagar y faltan los días que eligió o menos)
    due_in_days: Optional[int] = None
    due_soon: bool = False


FIN_FIXED_ON_CANCEL = ("move", "pause")


class FinCardCancel(SQLModel):
    """Dar de baja una tarjeta: el día, y cómo queda en cero. Con deuda, desde qué cuenta
    se pagó (y cuándo); con saldo a favor, a cuál va. Sus fijos, a otra cuenta o en pausa."""
    cancelled_on: date_type
    settle_account_id: Optional[int] = None
    settle_date: Optional[date_type] = None
    fixed_action: Optional[str] = None
    fixed_account_id: Optional[int] = None

    @field_validator("fixed_action")
    @classmethod
    def validate_fixed_action(cls, v):
        return v if v is None else _one_of(v, FIN_FIXED_ON_CANCEL, "fixed_action")


class FinStatementOverride(SQLModel):
    """El pago para no generar intereses que dice el banco, para el corte en curso."""
    cut_date: date_type
    pay_no_interest_cents: int = Field(ge=0, le=MAX_MONEY_CENTS)


class FinCategoryOrder(SQLModel):
    """El orden de las categorías de un tipo: sus ids, todas, en el orden nuevo."""
    kind: str
    ids: List[int] = Field(min_length=1, max_length=FIN_MAX_CATEGORIES)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_CATEGORY_KINDS, "kind")


class FinTransactionListResponse(SQLModel):
    date_from: date_type
    date_to: date_type
    transactions: List[FinTransactionResponse]


class FinRecurringFields(SQLModel):
    kind: str = "expense"
    account_id: int
    category_id: int
    concept: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(gt=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)
    frequency: str = "monthly"
    # Una quincenal en otros días que el 15 y el último (los dos, o ninguno)
    first_day: Optional[int] = Field(default=None, ge=1, le=31)
    second_day: Optional[int] = Field(default=None, ge=1, le=31)
    start_date: date_type
    end_date: Optional[date_type] = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        return _one_of(v, FIN_CATEGORY_KINDS, "kind")

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        return _one_of(v, FIN_FREQUENCIES, "frequency")


class FinRecurringUpdate(SQLModel):
    """Cambiar un fijo: solo afecta a los cobros siguientes."""
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    concept: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount_cents: Optional[int] = Field(default=None, gt=0, le=MAX_MONEY_CENTS)
    note: Optional[str] = Field(default=None, max_length=500)
    frequency: Optional[str] = None
    first_day: Optional[int] = Field(default=None, ge=1, le=31)
    second_day: Optional[int] = Field(default=None, ge=1, le=31)
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    paused: Optional[bool] = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v):
        return _one_of(v, FIN_FREQUENCIES, "frequency")


class FinRecurringResponse(SQLModel):
    id: int
    kind: str
    account_id: int
    category_id: int
    concept: str
    amount_cents: int
    currency: str
    note: Optional[str] = None
    frequency: str
    first_day: Optional[int] = None
    second_day: Optional[int] = None
    start_date: date_type
    end_date: Optional[date_type] = None
    paused: bool
    generated: int
    next_date: Optional[date_type] = None
    last_charge: Optional[date_type] = None


class FinRecurringListResponse(SQLModel):
    recurring: List[FinRecurringResponse]


class FinSettingsResponse(SQLModel):
    # None mientras el usuario no conteste "¿Cada cuándo cobras?": se mide por mes
    period: Optional[str] = None


FIN_DUE_NOTICE_DAYS = (3, 5)


class FinNoticeSettings(SQLModel):
    """El aviso del pago de una tarjeta: con cuántos días antes y si sale en la campana."""
    due_days: int = 5
    due_bell: bool = True

    @field_validator("due_days")
    @classmethod
    def validate_due_days(cls, v):
        if v not in FIN_DUE_NOTICE_DAYS:
            raise ValueError("due_days es 3 o 5")
        return v


class FinConsentResponse(SQLModel):
    # None mientras no acepte cómo se tratan sus datos de Finanzas
    consent_at: Optional[datetime] = None


class FinSettingsUpdate(SQLModel):
    period: str

    @field_validator("period")
    @classmethod
    def validate_period(cls, v):
        return _one_of(v, FIN_PERIODS, "period")


class FinCategoryTotal(SQLModel):
    category_id: int
    name: str
    color: Optional[str] = None
    kind: str
    currency: str
    cents: int


class FinAccountTotal(SQLModel):
    """Lo que se movió en una cuenta en el periodo (no es su saldo)."""
    account_id: int
    name: str
    kind: str
    currency: str
    expense_cents: int = 0
    income_cents: int = 0
    transfer_in_cents: int = 0
    transfer_out_cents: int = 0
    net_cents: int = 0        # ingresos + lo que entra − gastos − lo que sale


class FinCurrencyTotal(SQLModel):
    currency: str
    expense_cents: int = 0    # las transferencias nunca cuentan como gasto
    income_cents: int = 0
    net_cents: int = 0


class FinSummaryResponse(SQLModel):
    period: str               # month | biweekly (month si no ha contestado)
    period_asked: bool        # si ya contestó "¿Cada cuándo cobras?"
    date_from: date_type
    date_to: date_type
    prev_day: date_type       # un día del periodo anterior, para pedirlo con ?day=
    next_day: date_type
    transactions: int
    needs_review: int
    categories: List[FinCategoryTotal]
    accounts: List[FinAccountTotal]
    totals: List[FinCurrencyTotal]
