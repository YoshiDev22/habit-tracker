from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, ProjectStatus, Project
from backend.schemas import (
    ProjectStatusCreate, ProjectStatusUpdate, ProjectStatusResponse, ProjectStatusListResponse,
)
from backend.auth import get_current_user
from backend.boards import PROJECT_STATUS_CATEGORIES, ensure_user_setup, get_owned_project_status

router = APIRouter(tags=["project-statuses"])


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre no puede estar vacío"
        )
    return cleaned


def _name_taken(session: Session, user_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = select(ProjectStatus.id).where(ProjectStatus.user_id == user_id, ProjectStatus.name == name)
    if exclude_id is not None:
        query = query.where(ProjectStatus.id != exclude_id)
    return session.exec(query).first() is not None


def _name_conflict(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Ya existe un estado llamado '{name}'"
    )


@router.get("", response_model=ProjectStatusListResponse)
def get_project_statuses(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Estados de proyecto del usuario, en orden. La primera llamada crea los de por defecto."""
    ensure_user_setup(session, current_user.id)

    statuses = session.exec(
        select(ProjectStatus).where(ProjectStatus.user_id == current_user.id)
        .order_by(ProjectStatus.order, ProjectStatus.id)
    ).all()

    return ProjectStatusListResponse(
        statuses=[ProjectStatusResponse.model_validate(s) for s in statuses],
        total=len(statuses)
    )


@router.post("", response_model=ProjectStatusResponse, status_code=status.HTTP_201_CREATED)
def create_project_status(
    status_in: ProjectStatusCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Crea un estado de proyecto. Sin order, va al final."""
    if status_in.category not in PROJECT_STATUS_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category debe ser una de: {', '.join(PROJECT_STATUS_CATEGORIES)}"
        )

    # Los defaults primero: si no, crear el primer estado propio dejaría al
    # usuario con ese solo estado y sin "En curso" a donde van los proyectos.
    ensure_user_setup(session, current_user.id)

    name = _clean_name(status_in.name)
    if _name_taken(session, current_user.id, name):
        raise _name_conflict(name)

    order = status_in.order
    if order is None:
        last = session.exec(
            select(func.max(ProjectStatus.order)).where(ProjectStatus.user_id == current_user.id)
        ).one()
        order = 0 if last is None else last + 1

    new_status = ProjectStatus(
        user_id=current_user.id,
        category=status_in.category,
        name=name,
        color=status_in.color,
        order=order,
    )
    session.add(new_status)
    session.commit()
    session.refresh(new_status)

    return ProjectStatusResponse.model_validate(new_status)


@router.patch("/{status_id}", response_model=ProjectStatusResponse)
def update_project_status(
    status_id: int,
    status_in: ProjectStatusUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Renombra, cambia el color o reordena un estado. La categoría es fija."""
    target = get_owned_project_status(session, current_user.id, status_id)

    update_data = {k: v for k, v in status_in.model_dump(exclude_unset=True).items() if v is not None}

    if "name" in update_data:
        update_data["name"] = _clean_name(update_data["name"])
        if _name_taken(session, current_user.id, update_data["name"], exclude_id=target.id):
            raise _name_conflict(update_data["name"])

    for field, value in update_data.items():
        setattr(target, field, value)

    session.add(target)
    session.commit()
    session.refresh(target)

    return ProjectStatusResponse.model_validate(target)


@router.delete("/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_status(
    status_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Borra un estado sin proyectos. Con proyectos devuelve 409: hay que
    moverlos antes. Tampoco se puede borrar el último de su categoría.
    """
    target = get_owned_project_status(session, current_user.id, status_id)

    in_use = session.exec(
        select(func.count()).select_from(Project).where(
            Project.user_id == current_user.id, Project.status_id == target.id
        )
    ).one()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{target.name}' tiene {in_use} proyectos. Muévelos a otro estado antes de borrarlo"
        )

    siblings = session.exec(
        select(func.count()).select_from(ProjectStatus).where(
            ProjectStatus.user_id == current_user.id,
            ProjectStatus.category == target.category,
        )
    ).one()
    if siblings <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{target.name}' es el único estado de su categoría y no se puede borrar"
        )

    session.delete(target)
    session.commit()
