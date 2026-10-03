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
    rompe la racha: descanso, vacaciones, escudo (protector), hoy (en curso), o
    vacío si es un día normal."""
    date: date_type
    habit_key: str
    label: str
    icon: Optional[str] = None
    done: bool
    day_kind: str = ""


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


class ProjectFinanceUpdate(SQLModel):
    """Costeo de un proyecto (PUT parcial): solo cambia lo que se manda, y null
    borra ese dato."""
    client_name: Optional[str] = Field(default=None, max_length=120)
    hourly_rate_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    currency: Optional[str] = None
    budget_cents: Optional[int] = Field(default=None, ge=0, le=MAX_MONEY_CENTS)
    budget_minutes: Optional[int] = Field(default=None, ge=0, le=MAX_BUDGET_MINUTES)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CURRENCIES:
            raise ValueError(f"Moneda no válida. Usa una de: {', '.join(CURRENCIES)}")
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
    total_cents: int          # cantidad × costo unitario, redondeado al centavo
    note: Optional[str] = None


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
    margin_cents: Optional[int] = None    # presupuesto − costo, con presupuesto en dinero
    is_quote: bool = False


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
    margin_cents: Optional[int] = None        # presupuesto − costo, con presupuesto en dinero


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
