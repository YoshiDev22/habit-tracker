from datetime import date as date_type, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, HabitEntry, Habit
from backend.schemas import (
    HabitEntryCreate,
    HabitEntryResponse,
    HabitStats,
    UserHabitsResponse,
    HabitData,
    HabitCreate,
    HabitUpdate,
    HabitResponse,
    HabitListResponse,
)
from backend.auth import get_current_user

router = APIRouter(tags=["habits"])

HABIT_FIELDS = ["study", "capoeira", "reading", "diet", "others"]


@router.get("", response_model=UserHabitsResponse)
def get_habits(
    month: Optional[int] = None,
    year: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene todos los hábitos del usuario, opcionalmente filtrados por mes/año
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
    
    # Calcular racha
    streak = calculate_streak(current_user.id, session)
    
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
        streak=streak
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
            del entry.habits_data[habit_key]
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
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene la racha actual de días consecutivos
    """
    streak = calculate_streak(current_user.id, session)
    return {"streak": streak}


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


def calculate_streak(user_id: int, session: Session) -> int:
    """Calcula la racha actual de días consecutivos"""
    today = date_type.today()
    streak = 0
    check_date = today
    max_days_back = 365  # No buscar más de 365 días atrás
    
    # Empezar desde hoy
    while max_days_back > 0:
        entry = session.exec(
            select(HabitEntry).where(
                HabitEntry.user_id == user_id,
                HabitEntry.entry_date == check_date
            )
        ).first()
        
        if entry and entry.habits_data:
            # Verificar si tiene al menos un hábito completado (cualquiera)
            habits_data = entry.habits_data or {}
            has_any_habit = any(v for v in habits_data.values() if v)
            
            if has_any_habit:
                streak += 1
                check_date -= timedelta(days=1)
            elif streak == 0:
                # Hoy no tiene hábitos, empezar desde ayer
                check_date -= timedelta(days=1)
            else:
                break
        elif streak == 0:
            # Empezar desde ayer si hoy no tiene datos
            check_date -= timedelta(days=1)
        else:
            break
        
        max_days_back -= 1
    
    return streak
