from dataclasses import dataclass, field
from datetime import date as date_type, timedelta
from typing import Optional, Dict, List, Set
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, HabitEntry, Habit
from backend.schemas import (
    MAX_HABITS_PER_DAY,
    HabitEntryCreate,
    HabitEntryResponse,
    HabitMark,
    HabitStats,
    UserHabitsResponse,
    HabitData,
    HabitCreate,
    HabitUpdate,
    HabitResponse,
    HabitListResponse,
    HabitReportItem,
    HabitReportResponse,
    StreakResponse,
)
from backend.auth import get_current_user
from backend.dates import resolve_client_today

router = APIRouter(tags=["habits"])

HABIT_FIELDS = ["study", "capoeira", "reading", "diet", "others"]


@router.get("", response_model=UserHabitsResponse)
def get_habits(
    month: Optional[int] = None,
    year: Optional[int] = None,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene todos los hábitos del usuario, opcionalmente filtrados por mes/año.
    `today` es la fecha LOCAL del cliente, para la racha (ver backend/dates.py).
    """
    query = select(HabitEntry).where(HabitEntry.user_id == current_user.id)
    
    if month and year:
        # Filtrar por mes específico
        start_date = date_type(year, month, 1)
        if month == 12:
            end_date = date_type(year + 1, 1, 1)
        else:
            end_date = date_type(year, month + 1, 1)
        
        query = query.where(
            HabitEntry.entry_date >= start_date,
            HabitEntry.entry_date < end_date
        )
    
    entries = session.exec(query.order_by(HabitEntry.entry_date.desc())).all()
    
    # Calcular estadísticas del mes actual
    stats = calculate_stats(current_user.id, month, year, session)
    
    # Racha y protectores
    walk = calculate_streak(current_user.id, session, current_user, resolve_client_today(today))
    
    # Convertir a formato de respuesta
    entries_response = [
        {
            "id": e.id,
            "date": str(e.entry_date),
            "habits_data": e.habits_data or {}
        }
        for e in entries
    ]
    
    return UserHabitsResponse(
        entries=entries_response,
        stats=stats,
        **_streak_payload(walk)
    )


@router.delete("/delete-habit")
def delete_habit(
    request: dict,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina un hábito específico de todos los registros del usuario
    """
    habit_key = request.get('habit_key')
    if not habit_key:
        raise HTTPException(status_code=400, detail="Se requiere el nombre del hábito")
    
    # Buscar todas las entradas del usuario
    entries = session.exec(
        select(HabitEntry).where(HabitEntry.user_id == current_user.id)
    ).all()
    
    # Eliminar el hábito de cada entrada
    for entry in entries:
        if entry.habits_data and habit_key in entry.habits_data:
            entry.habits_data = {k: v for k, v in entry.habits_data.items() if k != habit_key}
            session.add(entry)
    
    session.commit()
    
    return {"message": f"Hábito '{habit_key}' eliminado de todos los registros"}


@router.post("")
def save_habits(
    habit_entry: HabitEntryCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Guarda o actualiza los hábitos de un día específico
    """
    # Ya viene como diccionario del esquema
    habits_dict = habit_entry.habits
    
    # Buscar si ya existe entrada para esta fecha
    existing_entry = session.exec(
        select(HabitEntry).where(
            HabitEntry.user_id == current_user.id,
            HabitEntry.entry_date == habit_entry.date
        )
    ).first()
    
    if existing_entry:
        # Actualizar existente
        existing_entry.habits_data = habits_dict
        session.commit()
        session.refresh(existing_entry)
    else:
        # Crear nueva entrada
        new_entry = HabitEntry(
            user_id=current_user.id,
            entry_date=habit_entry.date,
            habits_data=habits_dict
        )
        session.add(new_entry)
        session.commit()
        session.refresh(new_entry)
        existing_entry = new_entry
    
    # Devolver como diccionario
    return {
        "id": existing_entry.id,
        "date": str(existing_entry.entry_date),
        "habits_data": existing_entry.habits_data or {}
    }


@router.patch("/day/{entry_date}")
def mark_habit(
    entry_date: date_type,
    mark: HabitMark,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Marca o desmarca UN hábito en un día, sin tocar los demás de ese día.
    Es lo que usa la pantalla: mandar el día completo pisaba lo que ella no
    mostraba (hábitos ocultos, o lo que otro dispositivo guardó entretanto).
    El hábito puede estar oculto, pero tiene que ser del usuario.
    """
    habit = session.exec(
        select(Habit).where(Habit.user_id == current_user.id, Habit.key == mark.habit_key)
    ).first()
    if not habit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hábito no encontrado")

    entry = session.exec(
        select(HabitEntry).where(
            HabitEntry.user_id == current_user.id,
            HabitEntry.entry_date == entry_date
        )
    ).first()
    data = dict(entry.habits_data or {}) if entry else {}
    if mark.done:
        data[mark.habit_key] = True
    else:
        data.pop(mark.habit_key, None)
    if len(data) > MAX_HABITS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Un día admite como máximo {MAX_HABITS_PER_DAY} hábitos"
        )

    if entry:
        # Reasignar el dict completo: mutarlo in-place no lo detecta SQLAlchemy
        entry.habits_data = data
    else:
        entry = HabitEntry(user_id=current_user.id, entry_date=entry_date, habits_data=data)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return {"id": entry.id, "date": str(entry.entry_date), "habits_data": entry.habits_data or {}}


@router.get("/stats", response_model=HabitStats)
def get_stats(
    month: Optional[int] = None,
    year: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene estadísticas de hábitos
    """
    return calculate_stats(current_user.id, month, year, session)


@router.get("/streak")
def get_streak(
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene la racha actual de días consecutivos, con sus protectores.
    `today` es la fecha LOCAL del cliente (ver backend/dates.py).
    """
    walk = calculate_streak(current_user.id, session, current_user, resolve_client_today(today))
    return StreakResponse(**_streak_payload(walk))


@router.get("/report", response_model=HabitReportResponse)
def get_habit_report(
    date_from: date_type,
    date_to: date_type,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Cuántos días se hizo cada hábito activo en el rango (fechas LOCALES,
    incluidas), con su racha actual y su récord. `today` es la fecha local del
    cliente (ver backend/dates.py).
    """
    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from no puede ser posterior a date_to"
        )
    today = resolve_client_today(today)
    rest_days = set(current_user.rest_days or [])

    # Todo el historial hasta hoy: el récord puede ser de hace meses
    entries = session.exec(
        select(HabitEntry).where(
            HabitEntry.user_id == current_user.id,
            HabitEntry.entry_date <= today
        )
    ).all()
    done_by_key: Dict[str, Set[date_type]] = {}
    any_done: Set[date_type] = set()
    for entry in entries:
        for key, value in (entry.habits_data or {}).items():
            if value:
                done_by_key.setdefault(key, set()).add(entry.entry_date)
                any_done.add(entry.entry_date)

    last_day = min(date_to, today)
    days_elapsed = (last_day - date_from).days + 1 if last_day >= date_from else 0
    rest_elapsed = sum(
        1 for i in range(days_elapsed)
        if (date_from + timedelta(days=i)).weekday() in rest_days
    )
    in_range = lambda dates: sum(1 for d in dates if date_from <= d <= date_to)

    habits = session.exec(
        select(Habit).where(Habit.user_id == current_user.id, Habit.is_active == True)
        .order_by(Habit.order, Habit.id)
    ).all()
    items = []
    for habit in habits:
        done = done_by_key.get(habit.key, set())
        walk = _walk_streak(done, rest_days, today)
        items.append(HabitReportItem(
            key=habit.key,
            label=habit.label,
            icon=habit.icon,
            color=habit.color,
            days_done=in_range(done),
            current_streak=walk.current,
            best_streak=walk.best,
        ))

    overall = _walk_streak(any_done, rest_days, today)
    return HabitReportResponse(
        days_elapsed=days_elapsed,
        rest_days_elapsed=rest_elapsed,
        active_days=in_range(any_done),
        streak=overall.current,
        best_streak=overall.best,
        streak_shields=overall.shields,
        habits=items,
    )


# ==================== Endpoints: Definición de Hábitos ====================

@router.get("/definitions", response_model=HabitListResponse)
def get_habit_definitions(
    include_inactive: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los hábitos definidos por el usuario.
    Por defecto solo devuelve los activos (is_active=True).
    Usa include_inactive=true para ver también los archivados.
    """
    query = select(Habit).where(Habit.user_id == current_user.id)

    if not include_inactive:
        query = query.where(Habit.is_active == True)

    habits = session.exec(query.order_by(Habit.order, Habit.id)).all()

    return HabitListResponse(
        habits=[HabitResponse.model_validate(h) for h in habits],
        total=len(habits)
    )


@router.post("/definitions", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
def create_habit_definition(
    habit_in: HabitCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Crea un nuevo hábito para el usuario.
    La clave (key) debe ser única por usuario.
    Si ya existe un hábito con esa key (activo o inactivo), devuelve 409.
    """
    # Verificar que la key no esté duplicada para este usuario
    existing = session.exec(
        select(Habit).where(
            Habit.user_id == current_user.id,
            Habit.key == habit_in.key
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un hábito con la clave '{habit_in.key}' para este usuario"
        )

    new_habit = Habit(
        user_id=current_user.id,
        key=habit_in.key,
        label=habit_in.label,
        icon=habit_in.icon,
        color=habit_in.color,
        order=habit_in.order or 0,
        is_active=True,
    )
    session.add(new_habit)
    session.commit()
    session.refresh(new_habit)

    return HabitResponse.model_validate(new_habit)


@router.patch("/definitions/{habit_id}", response_model=HabitResponse)
def update_habit_definition(
    habit_id: int,
    habit_in: HabitUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente un hábito (label, icon, color, order, is_active).
    Para archivar un hábito sin borrar su historial, envía is_active=false.
    Solo el dueño del hábito puede modificarlo.
    """
    habit = session.exec(
        select(Habit).where(
            Habit.id == habit_id,
            Habit.user_id == current_user.id
        )
    ).first()

    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hábito no encontrado"
        )

    # Aplicar solo los campos enviados (PATCH parcial)
    update_data = habit_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(habit, field, value)

    session.add(habit)
    session.commit()
    session.refresh(habit)

    return HabitResponse.model_validate(habit)


@router.delete("/definitions/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit_definition(
    habit_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina permanentemente la definición de un hábito.
    ADVERTENCIA: Los datos históricos en habit_entries (JSON) se conservan,
    pero el hábito ya no aparecerá en la lista de definiciones.
    Para conservar el historial visible, usa PATCH con is_active=false en su lugar.
    """
    habit = session.exec(
        select(Habit).where(
            Habit.id == habit_id,
            Habit.user_id == current_user.id
        )
    ).first()

    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hábito no encontrado"
        )

    session.delete(habit)
    session.commit()


# ==================== Funciones Auxiliares ====================

def calculate_stats(user_id: int, month: Optional[int], year: Optional[int], session: Session) -> Dict:
    """Calcula las estadísticas de hábitos"""
    query = select(HabitEntry).where(HabitEntry.user_id == user_id)
    
    if month and year:
        start_date = date_type(year, month, 1)
        if month == 12:
            end_date = date_type(year + 1, 1, 1)
        else:
            end_date = date_type(year, month + 1, 1)
        query = query.where(
            HabitEntry.entry_date >= start_date,
            HabitEntry.entry_date < end_date
        )
    
    entries = session.exec(query).all()
    
    stats = {}
    for entry in entries:
        habits_data = entry.habits_data or {}
        for habit_key, habit_value in habits_data.items():
            if habit_value:
                stats[habit_key] = stats.get(habit_key, 0) + 1
    
    return stats


def calculate_streak(
    user_id: int,
    session: Session,
    user: Optional[User] = None,
    today: Optional[date_type] = None,
) -> "StreakWalk":
    """
    La racha general: días con al menos un hábito completado, con la regla de
    _walk_streak (hoy no corta, los días de descanso congelan y los protectores
    cubren los días perdidos).

    `today` debe ser la fecha LOCAL del usuario (ver backend/dates.py): el servidor
    corre en UTC y, de noche, su "hoy" ya es mañana para el usuario. Sin ella se
    usa la fecha del servidor.
    """
    if user is None:
        user = session.get(User, user_id)
    rest_days = set(user.rest_days) if user and user.rest_days else set()

    if today is None:
        today = date_type.today()

    # Todo el historial: los protectores se ganan desde el principio de la racha
    entries = session.exec(
        select(HabitEntry).where(
            HabitEntry.user_id == user_id,
            HabitEntry.entry_date <= today
        )
    ).all()

    done_dates = {
        entry.entry_date for entry in entries
        if entry.habits_data and any(v for v in entry.habits_data.values() if v)
    }
    return _walk_streak(done_dates, rest_days, today)


# Protectores de racha: cada SHIELD_EVERY días hechos de la racha se gana uno,
# y se guardan hasta SHIELD_MAX. No se almacenan: salen de recorrer el historial,
# así que marcar tarde un día olvidado devuelve el protector que se había gastado.
SHIELD_EVERY = 7
SHIELD_MAX = 2


@dataclass
class StreakWalk:
    current: int = 0                  # racha hasta hoy
    best: int = 0                     # la más larga del historial
    shields: int = 0                  # protectores guardados ahora
    progress: int = 0                 # días hechos hacia el próximo (0..SHIELD_EVERY-1)
    protected: List[date_type] = field(default_factory=list)   # días cubiertos
    # Ayer no se hizo nada, no era de descanso y había racha: lo que el cliente
    # pregunta al abrir ("¿olvidaste anotar?"). None si no aplica.
    missed_yesterday: Optional[dict] = None


def _walk_streak(done_dates: Set[date_type], rest_days: Set[int], today: date_type) -> StreakWalk:
    """
    La regla de la racha, en un solo lugar, recorriendo los días hacia adelante:
    - Día con algo hecho: la racha suma 1 y avanza hacia el próximo protector.
    - Hoy sin nada: no corta (el día sigue en curso).
    - Día de descanso sin nada: congela (no suma y no corta).
    - Cualquier otro día sin nada: si hay racha y queda un protector, se gasta y
      la racha sigue sin sumar; si no, la racha se corta.
    Vale igual para todos los hábitos juntos o para uno solo.
    """
    walk = StreakWalk()
    if not done_dates:
        return walk
    yesterday = today - timedelta(days=1)
    run = 0
    day = min(done_dates)
    while day <= today:
        if day in done_dates:
            run += 1
            walk.best = max(walk.best, run)
            walk.progress += 1
            if walk.progress == SHIELD_EVERY:
                walk.progress = 0
                walk.shields = min(SHIELD_MAX, walk.shields + 1)
        elif day == today or day.weekday() in rest_days:
            pass
        elif run > 0 and walk.shields > 0:
            walk.shields -= 1
            walk.protected.append(day)
            if day == yesterday:
                walk.missed_yesterday = {"date": day, "streak": run, "shielded": True}
        else:
            if day == yesterday and run > 0:
                walk.missed_yesterday = {"date": day, "streak": run, "shielded": False}
            run = 0
            walk.progress = 0
        day += timedelta(days=1)
    walk.current = run
    return walk


def _streak_payload(walk: StreakWalk) -> dict:
    """Los campos de racha que comparten GET /api/habits y GET /api/habits/streak."""
    return {
        "streak": walk.current,
        "streak_shields": walk.shields,
        "shield_next_in": SHIELD_EVERY - walk.progress if walk.shields < SHIELD_MAX else None,
        "protected_days": [str(d) for d in walk.protected],
        "missed_yesterday": walk.missed_yesterday,
    }
