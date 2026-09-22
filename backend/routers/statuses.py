from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Status, Project, Task
from backend.schemas import StatusCreate, StatusUpdate, StatusResponse, StatusListResponse
from backend.auth import get_current_user
from backend.statuses import CATEGORIES_BY_SCOPE, ensure_user_statuses

router = APIRouter(tags=["statuses"])


def _name_taken(session: Session, user_id: int, scope: str, name: str, exclude_id: Optional[int] = None) -> bool:
    query = select(Status.id).where(
        Status.user_id == user_id,
        Status.scope == scope,
        Status.name == name,
    )
    if exclude_id is not None:
        query = query.where(Status.id != exclude_id)
    return session.exec(query).first() is not None


def _get_owned(session: Session, user_id: int, status_id: int) -> Status:
    target = session.exec(
        select(Status).where(Status.id == status_id, Status.user_id == user_id)
    ).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Estado no encontrado"
        )
    return target


def _name_conflict(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Ya existe un estado llamado '{name}'"
    )


@router.get("", response_model=StatusListResponse)
def get_statuses(
    scope: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los estados del usuario (columnas del tablero y estados de proyecto),
    ordenados. La primera llamada crea los estados por defecto.
    """
    ensure_user_statuses(session, current_user.id)

    query = select(Status).where(Status.user_id == current_user.id)
    if scope is not None:
        query = query.where(Status.scope == scope)

    statuses = session.exec(query.order_by(Status.scope, Status.order, Status.id)).all()

    return StatusListResponse(
        statuses=[StatusResponse.model_validate(s) for s in statuses],
        total=len(statuses)
    )


@router.post("", response_model=StatusResponse, status_code=status.HTTP_201_CREATED)
def create_status(
    status_in: StatusCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Crea un estado nuevo, por ejemplo una columna "Bloqueado" de categoría doing."""
    categories = CATEGORIES_BY_SCOPE.get(status_in.scope)
    if categories is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"scope debe ser uno de: {', '.join(CATEGORIES_BY_SCOPE)}"
        )
    if status_in.category not in categories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Para '{status_in.scope}', category debe ser una de: {', '.join(categories)}"
        )

    # Los defaults primero: si no, crear el primer estado propio dejaría al
    # usuario con esa sola columna y sin "Por hacer" ni "Hecho".
    ensure_user_statuses(session, current_user.id)

    name = status_in.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre no puede estar vacío"
        )
    if _name_taken(session, current_user.id, status_in.scope, name):
        raise _name_conflict(name)

    new_status = Status(
        user_id=current_user.id,
        scope=status_in.scope,
        category=status_in.category,
        name=name,
        color=status_in.color,
        order=status_in.order or 0,
    )
    session.add(new_status)
    session.commit()
    session.refresh(new_status)

    return StatusResponse.model_validate(new_status)


@router.patch("/{status_id}", response_model=StatusResponse)
def update_status(
    status_id: int,
    status_in: StatusUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Renombra, cambia el color o reordena un estado. La categoría es fija."""
    target = _get_owned(session, current_user.id, status_id)

    update_data = status_in.model_dump(exclude_unset=True)

    if "name" in update_data:
        name = (update_data["name"] or "").strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El nombre no puede estar vacío"
            )
        if _name_taken(session, current_user.id, target.scope, name, exclude_id=target.id):
            raise _name_conflict(name)
        update_data["name"] = name

    if "order" in update_data and update_data["order"] is None:
        del update_data["order"]

    for field, value in update_data.items():
        setattr(target, field, value)

    session.add(target)
    session.commit()
    session.refresh(target)

    return StatusResponse.model_validate(target)


@router.delete("/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_status(
    status_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Borra un estado vacío. Con tareas o proyectos dentro devuelve 409: hay
    que moverlos antes, para que nada quede sin columna. Tampoco se puede
    borrar el último estado de una categoría, porque el checkbox de "hecho"
    y los proyectos nuevos necesitan siempre a dónde ir.
    """
    target = _get_owned(session, current_user.id, status_id)

    model = Task if target.scope == "task" else Project
    in_use = session.exec(
        select(func.count()).select_from(model).where(
            model.user_id == current_user.id,
            model.status_id == target.id
        )
    ).one()
    if in_use:
        what = "tareas" if target.scope == "task" else "proyectos"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{target.name}' tiene {in_use} {what}. Muévelos a otro estado antes de borrarlo"
        )

    siblings = session.exec(
        select(func.count()).select_from(Status).where(
            Status.user_id == current_user.id,
            Status.scope == target.scope,
            Status.category == target.category,
        )
    ).one()
    if siblings <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{target.name}' es el único estado de su categoría y no se puede borrar"
        )

    session.delete(target)
    session.commit()

