from datetime import date as date_type, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Project, Task, PomodoroSession
from backend.schemas import (
    PomodoroSessionCreate,
    PomodoroSessionUpdate,
    PomodoroSessionResponse,
    PomodoroSessionListResponse,
    PomodoroStatsResponse,
)
from backend.auth import get_current_user

router = APIRouter(tags=["pomodoro"])


@router.post("", response_model=PomodoroSessionResponse, status_code=status.HTTP_201_CREATED)
def create_pomodoro_session(
    session_in: PomodoroSessionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Registra una sesión de pomodoro ya finalizada (el timer vive en el
    cliente; este endpoint solo persiste el resultado).
    """
    if session_in.duration_seconds <= 0 or session_in.duration_seconds > 86400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duration_seconds fuera de rango"
        )

    source = session_in.source or "timer"
    if source not in ("timer", "manual"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source debe ser 'timer' o 'manual'"
        )

    if source == "manual":
        # Un día de margen: session_date es la fecha LOCAL del usuario y puede
        # ir por delante de la del servidor según su huso horario.
        if session_in.session_date > date_type.today() + timedelta(days=1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede registrar trabajo en una fecha futura"
            )
        if session_in.ended_at <= session_in.started_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La hora de fin debe ser posterior a la de inicio"
            )

    if session_in.project_id is not None:
        project = session.exec(
            select(Project).where(
                Project.id == session_in.project_id,
                Project.user_id == current_user.id
            )
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado"
            )

    if session_in.task_id is not None:
        task = session.exec(
            select(Task).where(
                Task.id == session_in.task_id,
                Task.user_id == current_user.id
            )
        ).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tarea no encontrada"
            )

    new_session = PomodoroSession(
        user_id=current_user.id,
        project_id=session_in.project_id,
        task_id=session_in.task_id,
        session_date=session_in.session_date,
        started_at=session_in.started_at,
        ended_at=session_in.ended_at,
        duration_seconds=session_in.duration_seconds,
        planned_seconds=session_in.planned_seconds or 1500,
        mode=session_in.mode or "focus",
        was_completed=session_in.was_completed if session_in.was_completed is not None else True,
        note=session_in.note,
        source=source,
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)

    return PomodoroSessionResponse.model_validate(new_session)


@router.get("", response_model=PomodoroSessionListResponse)
def get_pomodoro_sessions(
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    project_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Lista las sesiones de pomodoro del usuario, más recientes primero."""
    query = select(PomodoroSession).where(PomodoroSession.user_id == current_user.id)

    if date_from:
        query = query.where(PomodoroSession.session_date >= date_from)
    if date_to:
        query = query.where(PomodoroSession.session_date <= date_to)
    if project_id is not None:
        query = query.where(PomodoroSession.project_id == project_id)

    sessions = session.exec(query.order_by(PomodoroSession.started_at.desc())).all()

    return PomodoroSessionListResponse(
        sessions=[PomodoroSessionResponse.model_validate(s) for s in sessions],
        total=len(sessions)
    )


@router.get("/stats", response_model=PomodoroStatsResponse)
def get_pomodoro_stats(
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Estadísticas agregadas de pomodoros (solo mode='focus').
    Agregación en Python, igual que calculate_stats() en habits.py.
    """
    query = select(PomodoroSession).where(
        PomodoroSession.user_id == current_user.id,
        PomodoroSession.mode == "focus"
    )
    if date_from:
        query = query.where(PomodoroSession.session_date >= date_from)
    if date_to:
        query = query.where(PomodoroSession.session_date <= date_to)

    sessions = session.exec(query).all()
    today = date_type.today()

    total_seconds = 0
    today_seconds = 0
    by_project: Dict[str, int] = {}
    by_date: Dict[str, int] = {}

    for s in sessions:
        total_seconds += s.duration_seconds
        if s.session_date == today:
            today_seconds += s.duration_seconds

        project_key = str(s.project_id) if s.project_id is not None else "sin_proyecto"
        by_project[project_key] = by_project.get(project_key, 0) + s.duration_seconds

        date_key = str(s.session_date)
        by_date[date_key] = by_date.get(date_key, 0) + s.duration_seconds

    return PomodoroStatsResponse(
        total_seconds=total_seconds,
        session_count=len(sessions),
        today_seconds=today_seconds,
        by_project=by_project,
        by_date=by_date,
    )


@router.patch("/{session_id}", response_model=PomodoroSessionResponse)
def update_pomodoro_session(
    session_id: int,
    session_in: PomodoroSessionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Corrige una sesión ya registrada: tarea, fecha, horas, duración o nota.
    El proyecto y el origen no se tocan.
    """
    pomodoro_session = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.id == session_id,
            PomodoroSession.user_id == current_user.id
        )
    ).first()

    if not pomodoro_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro no encontrado"
        )

    update_data = session_in.model_dump(exclude_unset=True)

    if update_data.get("task_id") is not None:
        task = session.exec(
            select(Task).where(
                Task.id == update_data["task_id"],
                Task.user_id == current_user.id
            )
        ).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tarea no encontrada"
            )

    for field, value in update_data.items():
        setattr(pomodoro_session, field, value)

    # Se valida el resultado del merge, no lo que vino en el cuerpo: un PATCH
    # parcial puede dejar la sesión inconsistente combinándose con lo que ya
    # había guardado.
    if pomodoro_session.duration_seconds <= 0 or pomodoro_session.duration_seconds > 86400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="duration_seconds fuera de rango"
        )
    if pomodoro_session.ended_at <= pomodoro_session.started_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La hora de fin debe ser posterior a la de inicio"
        )
    if pomodoro_session.session_date > date_type.today() + timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede registrar trabajo en una fecha futura"
        )

    session.add(pomodoro_session)
    session.commit()
    session.refresh(pomodoro_session)

    return PomodoroSessionResponse.model_validate(pomodoro_session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pomodoro_session(
    session_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Elimina una sesión de pomodoro registrada."""
    pomodoro_session = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.id == session_id,
            PomodoroSession.user_id == current_user.id
        )
    ).first()

    if not pomodoro_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada"
        )

    session.delete(pomodoro_session)
    session.commit()
