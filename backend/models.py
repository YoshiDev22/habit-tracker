from sqlmodel import SQLModel, Field
from typing import Optional, Dict, List
from datetime import date as date_type, datetime, timezone
from sqlalchemy import JSON, Index, UniqueConstraint


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

    # Sube al cambiar la contraseña o al irse si el usuario pide cerrar sus otras
    # sesiones: un token con otra versión deja de valer (backend/auth.py). Los
    # tokens de antes no la traen y cuentan como 0. Columna AÑADIDA: migrate.py.
    token_version: int = Field(default=0)
    # "Irme unos días": cuándo se borra la cuenta (UTC naive). NULL = no se va.
    # La borra scripts/purge_accounts.py (backend/accounts.py). Columna AÑADIDA.
    delete_after: Optional[datetime] = Field(default=None)


class UserModule(SQLModel, table=True):
    """
    Los módulos de una cuenta (backend/modules.py) que se apartan del valor por
    defecto: sin fila, cada módulo está como lo define MODULES. `allowed` es el
    acceso, que se da con scripts/grant_module.py; `enabled`, lo que el usuario
    encendió o apagó. NULL en cualquiera de los dos = el valor por defecto.
    Tabla NUEVA: create_all() la crea sola, sin migración.
    """
    __tablename__ = "user_modules"
    __table_args__ = (UniqueConstraint("user_id", "module", name="uq_user_modules_user_module"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    module: str
    enabled: Optional[bool] = Field(default=None)
    allowed: Optional[bool] = Field(default=None)


class HabitEntry(SQLModel, table=True):
    """Modelo de Entrada de Hábito (día específico) — se mantiene sin cambios"""
    __tablename__ = "habit_entries"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    entry_date: date_type = Field(index=True)
    
    # Almacena los hábitos como JSON
    habits_data: Dict = Field(default={}, sa_type=JSON)


class UserSettings(SQLModel, table=True):
    """
    Calendario de trabajo del usuario (épica 30, Fase 3): huso horario para las
    horas locales de las métricas (sesiones nocturnas, horario habitual) y país
    para los festivos oficiales. Sin fila, los valores por defecto de
    backend/days.py. Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_settings_user"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    timezone: str                       # nombre IANA, p. ej. "America/Mexico_City"
    country: str = Field(default="MX")  # ISO 3166-1 alfa-2, para Nager.Date


class UserDay(SQLModel, table=True):
    """
    Un día que el usuario marca a mano: "libre" (no trabaja: un festivo local,
    un puente) o "laboral" (sí trabaja aunque sea festivo oficial). Las
    vacaciones no van aquí: son las pausas de la racha (StreakPause), y también
    cuentan como días no hábiles. Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "user_days"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_days_user_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: date_type
    kind: str            # libre | laboral
    name: Optional[str] = Field(default=None)


class HolidayCache(SQLModel, table=True):
    """
    Festivos oficiales de un país y año, tal como los dio Nager.Date
    (backend/holidays.py). Se piden una vez por país y año. No es de ningún
    usuario: los festivos de México son los mismos para todos. Tabla NUEVA.
    """
    __tablename__ = "holiday_cache"
    __table_args__ = (UniqueConstraint("country", "year", name="uq_holiday_cache_country_year"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    country: str
    year: int
    days: List[dict] = Field(default=[], sa_type=JSON)   # [{"date": "AAAA-MM-DD", "name": ...}]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class StreakPause(SQLModel, table=True):
    """
    Pausa por vacaciones: del start_date al end_date (fechas LOCALES, incluidas)
    los días sin hábitos congelan la racha, como un día de descanso. Se programa
    hoy o hacia adelante, nunca para días pasados (para eso están los escudos).
    Tabla NUEVA: create_all() la crea sola, sin migración.
    """
    __tablename__ = "streak_pauses"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    start_date: date_type
    end_date: date_type


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


class ProjectFinance(SQLModel, table=True):
    """
    Costeo de un proyecto (plan maker, épica 24 Fase 2): cliente, tarifa por
    hora, moneda y presupuesto. Aparte de `projects` para no tocar esa tabla, y
    porque solo existe para quien usa el plan maker. Uno por proyecto como
    mucho; sin fila, el proyecto no tiene costeo. Dinero en centavos enteros,
    nunca float. Tabla NUEVA: create_all() la crea sola, sin migración.
    """
    __tablename__ = "project_finance"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_finance_project"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    project_id: int = Field(foreign_key="projects.id")

    client_name: Optional[str] = Field(default=None)   # texto libre, no una tabla de clientes
    hourly_rate_cents: Optional[int] = Field(default=None)
    currency: str = Field(default="MXN")                # una por proyecto: no se convierte
    budget_cents: Optional[int] = Field(default=None)   # presupuesto en dinero...
    budget_minutes: Optional[int] = Field(default=None) # ...y/o en tiempo
    # Épica 30, Fase 6. Columnas AÑADIDAS (migrate.py). NULL = sin decir.
    kind: Optional[str] = Field(default=None)           # personal | product | service
    price_cents: Optional[int] = Field(default=None)    # lo que se cobra: margen = precio − costo


class CostCategory(SQLModel, table=True):
    """
    Categoría de gasto del usuario (plan maker, Fase 3): "Material", "IA"...
    Cada cuenta recibe cinco al entrar a Costos por primera vez
    (ensure_cost_categories en routers/costs.py) y las renombra, pinta, ordena
    o crea. Una con gastos no se borra. Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "cost_categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_cost_categories_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    color: Optional[str] = Field(default=None)
    order: int = Field(default=0)


class ProjectCost(SQLModel, table=True):
    """
    Un gasto de un proyecto (plan maker, Fase 3): licencias, materiales,
    servicios... Lo que no es mano de obra. En la moneda del proyecto
    (project_finance.currency). El total del renglón = cantidad × costo
    unitario, redondeado al centavo; no se guarda. Se borra con su proyecto.
    Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "project_costs"
    # Un cobro de un recurrente se genera una vez por fecha y proyecto (1.24)
    # Index con nombre (no UniqueConstraint): así lo crea y lo comprueba migrate.py
    __table_args__ = (Index("uq_project_costs_recurring", "recurring_id", "cost_date", "project_id", unique=True),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    category_id: int = Field(foreign_key="cost_categories.id")

    cost_date: date_type                      # fecha local del gasto
    concept: str
    quantity: float = Field(default=1)        # no es dinero: 2.5 m de tela, 3 licencias
    unit_cost_cents: int = Field(default=0)   # dinero: centavos enteros
    note: Optional[str] = Field(default=None)

    # 1.24. Columnas AÑADIDAS (migrate.py); NULL en los gastos de antes.
    # Un gasto repartido entre proyectos es una fila por proyecto, todas con los
    # mismos datos del gasto y el mismo split_id (el id de la primera). Cada una
    # guarda su parte: split_bp en puntos base (6500 = 65 %) y share_cents, que
    # se reparte al guardar para que las partes sumen exacto el total.
    split_id: Optional[int] = Field(default=None, index=True)
    split_bp: Optional[int] = Field(default=None)
    share_cents: Optional[int] = Field(default=None)
    # El gasto recurrente que lo generó (🔁); NULL si se escribió a mano
    recurring_id: Optional[int] = Field(default=None, foreign_key="recurring_costs.id")


class RecurringCost(SQLModel, table=True):
    """
    Un gasto que se repite (1.24): suscripciones, hosting, dominios. Cada mes o
    cada año, en el día de start_date (el 31 cae en el último día de un mes
    más corto), se convierte en un gasto real en project_costs, con
    recurring_id. Cambiarlo solo afecta a los cobros siguientes; los ya
    generados se editan o se borran como cualquier gasto, y uno borrado no
    vuelve. Puede ir repartido entre proyectos de la misma moneda
    (allocations). Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "recurring_costs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int = Field(foreign_key="cost_categories.id")
    concept: str
    quantity: float = Field(default=1)
    unit_cost_cents: int = Field(default=0)
    note: Optional[str] = Field(default=None)
    frequency: str = Field(default="monthly")      # monthly | yearly
    start_date: date_type                          # el primer cobro; su día marca los siguientes
    end_date: Optional[date_type] = Field(default=None)
    paused: bool = Field(default=False)
    # [{"project_id": 3, "bp": 6500}, ...]; los bp suman 10000
    allocations: List[Dict] = Field(default=[], sa_type=JSON)
    generated: int = Field(default=0)              # cobros ya generados (o saltados al pausar)
    # utc_now_naive se define más abajo: el lambda la busca al crear la fila
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


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

    # Estimado en minutos (épica 24, Fase 4); NULL = sin estimado. Columna
    # AÑADIDA a una tabla existente: la agrega scripts/migrate.py como NULL,
    # así que ninguna tarea vieja queda con un estimado inventado.
    estimate_minutes: Optional[int] = Field(default=None)


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
    # Una misma clave de idempotencia no se repite dentro de un usuario. En una
    # base nueva lo crea create_all(); en una existente, scripts/migrate.py
    # (INDEXES), con el mismo nombre para que las dos queden iguales. SQLite
    # no compara los NULL entre sí: las sesiones sin clave no chocan.
    __table_args__ = (
        Index("uq_pomodoro_sessions_user_key", "user_id", "idempotency_key", unique=True),
    )

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
    # Por confirmar: un cronómetro que llegó al tope de 8 h (o se cerró solo al
    # cerrar sesión) y nadie ha dicho cuánto se trabajó. La campanita lo avisa;
    # corregir las horas o "Está bien" lo quitan. Se cuenta igual en totales y
    # reportes, que dicen cuánto tiempo sin confirmar incluyen. Columna AÑADIDA:
    # scripts/migrate.py, que marca una sola vez las de antes por su nota.
    needs_review: bool = Field(default=False)
    # El sessionId que el cliente le puso al timer al arrancarlo. Si el mismo
    # POST llega dos veces (el navegador se cerró tras enviarlo y antes de
    # olvidarlo, o la respuesta se perdió y la cola lo reintentó), el segundo
    # devuelve la sesión ya guardada en vez de duplicar el tiempo. NULL en las
    # manuales y en todo lo anterior. Columna AÑADIDA: migrate.py.
    idempotency_key: Optional[str] = Field(default=None)

    created_at: date_type = Field(default_factory=date_type.today)


class Report(SQLModel, table=True):
    """
    Un reporte guardado de una semana (lunes a domingo) o un mes (épica 30,
    Fase 4). Congela las cifras de backend/metrics.py al generarlo, más un
    resumen del periodo anterior para comparar, y el texto (observaciones,
    recomendaciones, cierre). Uno por usuario, tipo y periodo: regenerar lo
    reemplaza, así que el timer puede correr dos veces sin duplicar.
    Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("user_id", "kind", "period_start", name="uq_reports_user_kind_start"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str                     # week | month
    period_start: date_type       # lunes, o día 1
    period_end: date_type         # domingo, o último del mes
    through: date_type            # último día con datos: antes de period_end si se generó a medio periodo
    metrics: Dict = Field(default={}, sa_type=JSON)
    text: Dict = Field(default={}, sa_type=JSON)
    text_source: str = Field(default="rules")   # rules | ai
    text_model: Optional[str] = Field(default=None)  # el modelo de IA que lo escribió
    text_note: Optional[str] = Field(default=None)   # por qué no lo escribió la IA, si debía
    trigger: str = Field(default="manual")      # manual (botón) | auto (scripts/generate_reports.py)
    created_at: datetime = Field(default_factory=utc_now_naive)  # UTC naive


class AiCall(SQLModel, table=True):
    """
    Cada llamada al proveedor de IA (backend/ai.py), salga bien o no: es lo que
    cuenta el límite diario por cuenta y lo que deja ver el consumo. No guarda
    lo que se envió ni lo que volvió. Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "ai_calls"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utc_now_naive, index=True)  # UTC naive
    purpose: str = Field(default="report")
    model: str
    ok: bool = Field(default=False)
    error: Optional[str] = Field(default=None)       # motivo corto, sin datos del usuario
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
