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
    # Última actividad (UTC naive), para el panel de administración (1.27). La pone
    # get_current_user como mucho una vez por hora (LAST_SEEN_EVERY en auth.py),
    # no en cada petición. NULL = sin actividad desde la 1.27. Columna AÑADIDA.
    last_seen_at: Optional[datetime] = Field(default=None)
    # Cuándo se registró (UTC naive), para el panel (1.27). Las cuentas de antes de
    # la 1.27 no lo tienen (NULL): no hay de dónde sacarlo. Columna AÑADIDA.
    created_at: Optional[datetime] = Field(default_factory=lambda: utc_now_naive())


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


class Announcement(SQLModel, table=True):
    """
    Un aviso para todas las cuentas (1.26): mantenimiento, una caída, algo que
    todos deben saber. Lo publica scripts/announce.py en el servidor (y, más
    adelante, el panel de administración). Cada cuenta lo recibe como aviso
    informativo de la campanita mientras esté vigente (hasta `ends_at`; sin
    fecha, hasta terminarlo). No es de un usuario: no tiene user_id.
    Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "announcements"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str                                   # hasta 80
    body: str = Field(default="")                # hasta 500
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())
    ends_at: Optional[datetime] = Field(default=None)   # UTC naive; después ya no se enseña


class AccountMessage(SQLModel, table=True):
    """
    Un aviso del panel de administración para una sola cuenta (1.27, Fase 2,
    paso 6): uno escrito a mano, o los automáticos al darle textos de IA extra o
    acceso a un módulo. Sale en su campanita como `message`. Se va con la cuenta
    (user_id). Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "account_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())
    title: str                                   # hasta 80
    body: str = Field(default="")                # hasta 500


class Notice(SQLModel, table=True):
    """
    Un aviso de la campanita (1.26), guardado por cuenta. Los pendientes
    (review, missed_day) calculan su estado de los datos; los informativos
    (report_ready, novedades) se leen. Uno por usuario, tipo y referencia (id
    de la sesión o del reporte, fecha, versión). Ver backend/notices.py.
    Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_notices_user_kind_ref"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str                                  # review | missed_day | report_ready | novedades | announcement
    ref: str
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())
    read_at: Optional[datetime] = Field(default=None)
    dismissed_at: Optional[datetime] = Field(default=None)


class Feedback(SQLModel, table=True):
    """
    Un problema que reporta un usuario desde Mi perfil (1.27, épica 32): su
    texto y, si quiso, detalles técnicos (versión, pestaña, pantalla, navegador
    y los últimos errores de la consola; nunca tokens). Se lee en el
    panel de administración, que cambia `status` y deja `admin_note`. Se borra
    con la cuenta (purge_user). Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive(), index=True)
    text: str                                              # 10 a 2000
    details: Optional[Dict] = Field(default=None, sa_type=JSON)
    status: str = Field(default="open")                    # open | reviewed | closed
    admin_note: Optional[str] = Field(default=None)        # nota interna: no sale en avisos; sí en su export
    # Lo que lee quien lo reportó en su aviso al cerrarlo (1.27, Fase 2). Columna de una
    # tabla de esta misma versión: en migrate.py con new_table (las bases de desarrollo)
    user_note: Optional[str] = Field(default=None)


class AiGrant(SQLModel, table=True):
    """
    Textos de IA extra para una cuenta, solo por un día (1.27, Fase 2 del panel):
    se suman al límite del día (UTC) de su contador (`pool`: report | costs) y
    al día siguiente vuelve el normal. Los da el panel de administración; dar
    más el mismo día suma a la misma fila. Se borra con la cuenta (user_id).
    Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "ai_grants"
    __table_args__ = (UniqueConstraint("user_id", "pool", "day", name="uq_ai_grants_user_pool_day"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    pool: str
    day: date_type
    extra: int


class SecurityEvent(SQLModel, table=True):
    """
    Eventos de seguridad, agrupados: una fila por hora, tipo, IP y cuenta, con su
    contador (backend/security_log.py). Solo lo que falla o delata un abuso, nunca
    lo que hace cada persona. IP completa, 30 días; con user_id se va con la
    cuenta. Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "security_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    hour: datetime = Field(index=True)             # UTC naive, al inicio de la hora
    kind: str
    ip: str = Field(default="")                    # vacía si el evento no viene de una petición
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    count: int = Field(default=0)
    last_at: Optional[datetime] = Field(default=None)


class AdminAction(SQLModel, table=True):
    """
    La bitácora del panel de administración (1.27, Fase 2): cada acción que
    cambia algo, con quién la hizo (el correo de Access), qué, sobre qué cuenta
    y cómo estaba antes y después. No se edita ni se borra desde el panel.
    `account_id` y no `user_id` a propósito: purge_user() borra toda tabla con
    user_id, y la bitácora debe sobrevivir al borrado de la cuenta (sin datos de
    la persona: solo su id y el cambio). Tabla NUEVA: create_all(), sin migración.
    """
    __tablename__ = "admin_actions"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive(), index=True)
    admin_email: str
    action: str                                   # module | ai_grant | account | feedback | announcement …
    account_id: Optional[int] = Field(default=None, index=True)   # la cuenta afectada (o ninguna)
    before: Optional[Dict] = Field(default=None, sa_type=JSON)
    after: Optional[Dict] = Field(default=None, sa_type=JSON)


class HabitNote(SQLModel, table=True):
    """
    Una nota corta de un hábito en un día (1.25): "cuerda 20 min", "bici a la
    escuela". Solo para control propio: no cambia la racha ni el cumplimiento
    (el hábito sigue siendo sí/no, en habit_entries). Una por hábito y día; sin
    texto, se borra. Va por habit_key, como habits_data. Tabla NUEVA:
    create_all(), sin migración.
    """
    __tablename__ = "habit_notes"
    __table_args__ = (UniqueConstraint("user_id", "habit_key", "entry_date", name="uq_habit_notes_user_habit_day"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    habit_key: str
    entry_date: date_type = Field(index=True)
    text: str
    updated_at: datetime = Field(default_factory=lambda: utc_now_naive())


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


# ==================== Finanzas personales (épica 37) ====================
# Tablas NUEVAS: create_all() las crea solas, sin migración. No comparten nada
# con Costos (aquello es el costo de un proyecto; esto, el dinero del día a día).
# Todo en centavos enteros, y una moneda por cuenta que nunca se convierte.

class FinAccount(SQLModel, table=True):
    """
    De dónde sale el dinero: efectivo, débito o crédito. La compra con crédito
    es el gasto; el pago de la tarjeta, una transferencia (débito → crédito).
    Cada cuenta recibe "Efectivo" la primera vez (backend/finance.py). Con
    movimientos no se borra: se archiva (is_active).
    """
    __tablename__ = "fin_accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_fin_accounts_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    kind: str = Field(default="cash")            # cash | debit | credit | investment
    currency: str = Field(default="MXN")
    last4: Optional[str] = Field(default=None)   # nunca el número completo
    is_default: bool = Field(default=False)      # la de la alta rápida: solo una
    is_active: bool = Field(default=True)
    order: int = Field(default=0)
    icon: Optional[str] = Field(default=None)    # FIN_ICONS; NULL = el de su tipo
    color: Optional[str] = Field(default=None)
    # El saldo es este más sus movimientos (no se guarda). En una de crédito,
    # negativo es lo que ya se debía al empezar a usar la app.
    opening_balance_cents: int = Field(default=0)
    # El día de ese saldo (al empezar el día): cuentan los movimientos de ese día
    # en adelante; los de antes (meses viejos cargados después) son historial.
    # NULL = cuentan todos.
    opening_date: Optional[date_type] = Field(default=None)
    # Solo crédito: el límite, el día de corte y el día de pago (1 a 31; el que
    # el mes no tiene cae en el último)
    credit_limit_cents: Optional[int] = Field(default=None)
    statement_day: Optional[int] = Field(default=None)
    due_day: Optional[int] = Field(default=None)
    # Solo crédito: la tasa de interés anual que cobra, de referencia (no se calcula nada con ella)
    interest_rate_bp: Optional[int] = Field(default=None)
    # Un apartado (ahorro dentro de la cuenta) cuelga de su cuenta madre: un solo
    # nivel, de efectivo o débito, misma moneda y tipo. Mover dinero entre ellas
    # es una transferencia. NULL = cuenta suelta.
    parent_id: Optional[int] = Field(default=None, foreign_key="fin_accounts.id")
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinYieldRate(SQLModel, table=True):
    """
    La tasa anual que paga una cuenta (o un apartado) día a día, sin plazo,
    desde `from_date` hasta la fila siguiente: un cambio de tasa del banco no
    reescribe lo de antes. rate_bp = 0 es "desde aquí ya no gana". Con tope,
    solo esa parte del saldo gana. El rendimiento no se guarda: se estima
    (backend/finance_yield.py) y se anota con un movimiento source = "yield".
    """
    __tablename__ = "fin_yield_rates"
    __table_args__ = (UniqueConstraint("account_id", "from_date", name="uq_fin_yield_rates_account_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    from_date: date_type
    rate_bp: int                                  # 1500 = 15 % anual
    cap_cents: Optional[int] = Field(default=None)
    day_basis: int = Field(default=365)           # 365 o 360
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinTerm(SQLModel, table=True):
    """
    Una inversión a plazo fijo (CETES, un pagaré) que vive en una cuenta o
    apartado: el dinero llega con una transferencia del usuario y no está
    disponible hasta el vencimiento (start_date + days). Al vencer, el
    rendimiento (capital × tasa × días ÷ base) se anota como ingreso con
    source = "yield", y según on_maturity el total se queda, regresa a otra
    cuenta o se reinvierte en un plazo nuevo. Lo anota backend/finance_yield.py
    una sola vez: external_id "term-<id>" en el índice único de los movimientos.
    Por eso un id nunca se reutiliza (AUTOINCREMENT): uno borrado deja sus
    movimientos, y otro plazo con su id chocaría con ellos.
    """
    __tablename__ = "fin_terms"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    concept: str
    principal_cents: int
    start_date: date_type
    days: int
    rate_bp: int
    day_basis: int = Field(default=360)           # CETES y pagarés cuentan años de 360 días
    on_maturity: str = Field(default="stay")      # stay | return | renew
    return_account_id: Optional[int] = Field(default=None, foreign_key="fin_accounts.id")
    matured: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinNote(SQLModel, table=True):
    """Una nota libre de Finanzas (p. ej. el prompt con el que una IA lee los
    estados de cuenta). Texto del usuario: el panel de administración no la lee."""
    __tablename__ = "fin_notes"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    body: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())
    updated_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinCategory(SQLModel, table=True):
    """Categoría de gasto o de ingreso. Las de inicio las crea backend/finance.py
    la primera vez; después son del usuario. Con movimientos no se borra."""
    __tablename__ = "fin_categories"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_fin_categories_user_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    color: Optional[str] = Field(default=None)
    kind: str = Field(default="expense")         # expense | income
    icon: Optional[str] = Field(default=None)    # FIN_ICONS
    order: int = Field(default=0)


class FinRecurring(SQLModel, table=True):
    """
    Un fijo: renta, teléfono, suscripciones, o el sueldo. Misma regla de serie
    que los recurrentes de Costos (backend/series.py), más la quincenal (el 15 y
    el último día, u otros dos días). generate_due() en backend/finance.py convierte los cobros
    que ya llegaron en movimientos con recurring_id; `generated` cuenta los
    hechos, así que uno borrado no vuelve.
    """
    __tablename__ = "fin_recurring"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    category_id: int = Field(foreign_key="fin_categories.id")
    kind: str = Field(default="expense")         # expense | income (no transferencias)
    concept: str
    amount_cents: int
    note: Optional[str] = Field(default=None)
    frequency: str = Field(default="monthly")    # monthly | yearly | semimonthly
    # Los dos días de pago de una quincenal (del 1 al 31; el que el mes no tiene
    # cae en el último). NULL = el 15 y el último día. Solo con semimonthly.
    first_day: Optional[int] = Field(default=None)
    second_day: Optional[int] = Field(default=None)
    start_date: date_type                        # el primer cobro
    end_date: Optional[date_type] = Field(default=None)
    paused: bool = Field(default=False)
    generated: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinTransaction(SQLModel, table=True):
    """
    Un movimiento: gasto, ingreso o transferencia entre cuentas propias. El
    monto siempre es positivo; el signo lo da el tipo. Una transferencia no
    lleva categoría ni cuenta como gasto. Las columnas de las fases 3 y 4
    (source email/cfdi/telegram, external_id, linked_id, needs_review) van desde
    la fase 1: agregarlas después a una tabla ya en producción costaría una
    migración.
    """
    __tablename__ = "fin_transactions"
    __table_args__ = (
        Index("ix_fin_transactions_user_date", "user_id", "tx_date"),
        # Lo que llega solo (un correo, un mensaje) entra una vez
        Index("uq_fin_transactions_external", "user_id", "source", "external_id", unique=True),
        # Un cobro de un fijo se genera una vez por fecha
        Index("uq_fin_transactions_recurring", "recurring_id", "tx_date", unique=True),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    kind: str                                    # expense | income | transfer
    amount_cents: int
    tx_date: date_type                           # fecha LOCAL del usuario, como session_date
    category_id: Optional[int] = Field(default=None, foreign_key="fin_categories.id")
    to_account_id: Optional[int] = Field(default=None, foreign_key="fin_accounts.id")   # transferencias
    concept: str
    note: Optional[str] = Field(default=None)
    source: str = Field(default="manual")        # manual | import | recurring | email | cfdi | telegram
    external_id: Optional[str] = Field(default=None)
    linked_id: Optional[int] = Field(default=None)   # la factura (CFDI) ↔ la compra del banco
    recurring_id: Optional[int] = Field(default=None, foreign_key="fin_recurring.id")
    needs_review: bool = Field(default=False)    # llegó solo y quedó dudoso: cuenta igual
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())



class FinSplit(SQLModel, table=True):
    """
    Una parte de un movimiento dividido en categorías (un cargo de la tarjeta
    con súper y farmacia). Las partes suman exacto el monto del movimiento, y
    ese movimiento queda sin category_id: el resumen cuenta cada parte en su
    categoría. Se borran con su movimiento.
    """
    __tablename__ = "fin_splits"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    transaction_id: int = Field(foreign_key="fin_transactions.id", index=True)
    category_id: int = Field(foreign_key="fin_categories.id")
    amount_cents: int
    order: int = Field(default=0)


class FinStatement(SQLModel, table=True):
    """
    Lo que pide el estado de cuenta del banco para no generar intereses en un
    corte de una tarjeta, cuando el usuario lo corrige: manda sobre el cálculo
    de la app para ese corte (`card_statement()`). Uno por tarjeta y corte; el
    siguiente corte vuelve al cálculo.
    """
    __tablename__ = "fin_statements"
    __table_args__ = (UniqueConstraint("account_id", "cut_date", name="uq_fin_statements_cut"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    cut_date: date_type
    pay_no_interest_cents: int
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinBudgetGroup(SQLModel, table=True):
    """
    Un grupo del presupuesto mensual (Necesidades, Fondo de emergencia, Dar…) con
    su parte del ingreso en puntos base (4500 = 45 %). Los nombres y porcentajes
    son del usuario; una referencia (50/30/20) solo los crea para empezar.
    """
    __tablename__ = "fin_budget_groups"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    percent_bp: int = Field(default=0)
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinBudgetItem(SQLModel, table=True):
    """
    Un renglón del presupuesto mensual: un ingreso planeado (sin grupo) o un gasto
    planeado dentro de un grupo. Es solo el plan: nunca crea movimientos. Con
    `recurring_id` es un fijo (ese sí se anota solo); sin él, una estimación. La
    categoría, opcional, es para comparar después con lo gastado.
    """
    __tablename__ = "fin_budget_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str = Field(default="expense")         # expense | income
    group_id: Optional[int] = Field(default=None, foreign_key="fin_budget_groups.id")
    name: str
    amount_cents: int = Field(default=0)         # al mes
    note: Optional[str] = Field(default=None)
    category_id: Optional[int] = Field(default=None, foreign_key="fin_categories.id")
    recurring_id: Optional[int] = Field(default=None, foreign_key="fin_recurring.id")
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())


class FinInstallment(SQLModel, table=True):
    """
    Una compra a meses sin intereses en una tarjeta de crédito. La compra cuenta
    como gasto completa el día que se hace (es un movimiento normal); esto solo
    dice cuánto pide cada corte: el total en `months` partes, la primera en el
    corte `first_statement`. Se borra con su movimiento.
    """
    __tablename__ = "fin_installments"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_fin_installments_transaction"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="fin_accounts.id")
    transaction_id: Optional[int] = Field(default=None, foreign_key="fin_transactions.id")
    concept: str
    total_cents: int
    months: int
    purchase_date: date_type
    first_statement: date_type                   # el corte que factura la primera mensualidad
    created_at: datetime = Field(default_factory=lambda: utc_now_naive())

class FinSettings(SQLModel, table=True):
    """
    Cómo mide sus finanzas cada cuenta. `period` es la respuesta a "¿Cada cuándo
    cobras?": NULL mientras no conteste (la pantalla pregunta y usa el mes). Las
    demás columnas son de la fase 2 (ingreso esperado y hora del aviso del día)
    y llegan vacías desde ahora para no migrar después.
    """
    __tablename__ = "fin_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_fin_settings_user"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    period: Optional[str] = Field(default=None)  # month | biweekly
    expected_income_cents: Optional[int] = Field(default=None)
    currency: Optional[str] = Field(default=None)
    day_notice_hour: Optional[int] = Field(default=None)
    # Cuándo aceptó cómo se tratan sus datos financieros (UTC naive). Sin él, la
    # API de Finanzas no guarda ni enseña nada (finance_user)
    consent_at: Optional[datetime] = Field(default=None)
    # El aviso del pago de una tarjeta (Finanzas 0.8): con cuántos días antes (3 o 5) y si
    # también sale en la campana. NULL = por defecto (5 días, sí)
    due_notice_days: Optional[int] = Field(default=None)
    due_notice_bell: Optional[bool] = Field(default=None)
