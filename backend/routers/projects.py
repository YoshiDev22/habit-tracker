from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Project, Task, PomodoroSession
from backend.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
    ProjectSummary,
    ProjectSummaryListResponse,
)
from backend.auth import get_current_user

router = APIRouter(tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def get_projects(
    include_inactive: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los proyectos del usuario.
    Por defecto solo devuelve los activos (is_active=True).
    """
    query = select(Project).where(Project.user_id == current_user.id)

    if not include_inactive:
        query = query.where(Project.is_active == True)

    projects = session.exec(query.order_by(Project.order, Project.id)).all()

    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects)
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Crea un nuevo proyecto para el usuario.
    El nombre debe ser único por usuario. Si ya existe (activo o
    archivado), devuelve 409 en vez de reactivarlo automáticamente.
    """
    existing = session.exec(
        select(Project).where(
            Project.user_id == current_user.id,
            Project.name == project_in.name
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un proyecto con el nombre '{project_in.name}' para este usuario"
        )

    new_project = Project(
        user_id=current_user.id,
        name=project_in.name,
        description=project_in.description,
        color=project_in.color,
        icon=project_in.icon,
        order=project_in.order or 0,
        is_active=True,
    )
    session.add(new_project)
    session.commit()
    session.refresh(new_project)

    return ProjectResponse.model_validate(new_project)


@router.get("/summary", response_model=ProjectSummaryListResponse)
def get_projects_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Resumen por proyecto: progreso de tareas y tiempo dedicado (suma de
    PomodoroSession con mode='focus').
    """
    projects = session.exec(
        select(Project).where(
            Project.user_id == current_user.id,
            Project.is_active == True
        ).order_by(Project.order, Project.id)
    ).all()

    tasks = session.exec(
        select(Task).where(Task.user_id == current_user.id)
    ).all()

    pomodoro_sessions = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.user_id == current_user.id,
            PomodoroSession.mode == "focus"
        )
    ).all()

    tasks_by_project: Dict[int, list] = {}
    for t in tasks:
        tasks_by_project.setdefault(t.project_id, []).append(t)

    seconds_by_project: Dict[int, int] = {}
    sessions_by_project: Dict[int, int] = {}
    for s in pomodoro_sessions:
        if s.project_id is None:
            continue
        seconds_by_project[s.project_id] = seconds_by_project.get(s.project_id, 0) + s.duration_seconds
        sessions_by_project[s.project_id] = sessions_by_project.get(s.project_id, 0) + 1

    summaries = []
    for p in projects:
        project_tasks = tasks_by_project.get(p.id, [])
        summaries.append(ProjectSummary(
            project_id=p.id,
            name=p.name,
            color=p.color,
            task_total=len(project_tasks),
            task_done=sum(1 for t in project_tasks if t.is_done),
            total_seconds=seconds_by_project.get(p.id, 0),
            session_count=sessions_by_project.get(p.id, 0),
        ))

    return ProjectSummaryListResponse(summaries=summaries, total=len(summaries))


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Obtiene un proyecto específico del usuario"""
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente un proyecto.
    Para archivarlo sin borrar sus tareas, envía is_active=false.
    """
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    if project_in.name is not None and project_in.name != project.name:
        existing = session.exec(
            select(Project).where(
                Project.user_id == current_user.id,
                Project.name == project_in.name,
                Project.id != project_id
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un proyecto con el nombre '{project_in.name}' para este usuario"
            )

    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    session.add(project)
    session.commit()
    session.refresh(project)

    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina permanentemente un proyecto y sus tareas.
    Para conservar el historial, usa PATCH con is_active=false en su lugar.
    """
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    tasks = session.exec(
        select(Task).where(
            Task.project_id == project_id,
            Task.user_id == current_user.id
        )
    ).all()
    for t in tasks:
        session.delete(t)

    pomodoro_sessions = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.project_id == project_id,
            PomodoroSession.user_id == current_user.id
        )
    ).all()
    for s in pomodoro_sessions:
        session.delete(s)

    session.delete(project)
    session.commit()
