from datetime import date as date_type
from typing import Dict, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Tag, TaskTag, PomodoroSession
from backend.schemas import (
    TagCreate, TagUpdate, TagResponse, TagListResponse, TagSummary, TagSummaryListResponse,
)
from backend.auth import get_current_user

router = APIRouter(tags=["tags"])


def _get_owned_tag(session: Session, user_id: int, tag_id: int) -> Tag:
    tag = session.exec(
        select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
    ).first()
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Etiqueta no encontrada"
        )
    return tag


def _clean_name(session: Session, user_id: int, value: str, exclude_id: Optional[int] = None) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre no puede estar vacío"
        )
    query = select(Tag.id).where(Tag.user_id == user_id, Tag.name == name)
    if exclude_id is not None:
        query = query.where(Tag.id != exclude_id)
    if session.exec(query).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya tienes una etiqueta llamada '{name}'"
        )
    return name


@router.get("", response_model=TagListResponse)
def get_tags(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Etiquetas del usuario, por nombre."""
    tags = session.exec(
        select(Tag).where(Tag.user_id == current_user.id).order_by(Tag.name)
    ).all()

    return TagListResponse(
        tags=[TagResponse.model_validate(t) for t in tags],
        total=len(tags)
    )


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    tag_in: TagCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Crea una etiqueta. El nombre es único por usuario."""
    tag = Tag(
        user_id=current_user.id,
        name=_clean_name(session, current_user.id, tag_in.name),
        color=tag_in.color,
    )
    session.add(tag)
    session.commit()
    session.refresh(tag)

    return TagResponse.model_validate(tag)


# Literal antes que /{tag_id}: al revés, FastAPI intentaría leer "summary" como int
@router.get("/summary", response_model=TagSummaryListResponse)
def get_tags_summary(
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Tiempo de enfoque por etiqueta: la suma de las sesiones "focus" de las
    tareas que la llevan, opcionalmente entre dos fechas (session_date,
    la fecha local del usuario). Una sesión cuenta en cada etiqueta de su
    tarea, así que los totales pueden sumar más que el tiempo real.
    """
    tags = session.exec(
        select(Tag).where(Tag.user_id == current_user.id).order_by(Tag.name)
    ).all()

    tags_by_task: Dict[int, Set[int]] = {}
    for task_id, tag_id in session.exec(
        select(TaskTag.task_id, TaskTag.tag_id).where(TaskTag.user_id == current_user.id)
    ).all():
        tags_by_task.setdefault(task_id, set()).add(tag_id)

    seconds: Dict[int, int] = {}
    sessions: Dict[int, int] = {}
    if tags_by_task:
        query = select(PomodoroSession).where(
            PomodoroSession.user_id == current_user.id,
            PomodoroSession.mode == "focus",
            PomodoroSession.task_id.in_(list(tags_by_task)),
        )
        if date_from is not None:
            query = query.where(PomodoroSession.session_date >= date_from)
        if date_to is not None:
            query = query.where(PomodoroSession.session_date <= date_to)

        for s in session.exec(query).all():
            for tag_id in tags_by_task[s.task_id]:
                seconds[tag_id] = seconds.get(tag_id, 0) + s.duration_seconds
                sessions[tag_id] = sessions.get(tag_id, 0) + 1

    task_count: Dict[int, int] = {}
    for tag_ids in tags_by_task.values():
        for tag_id in tag_ids:
            task_count[tag_id] = task_count.get(tag_id, 0) + 1

    summaries = [
        TagSummary(
            tag_id=t.id,
            name=t.name,
            color=t.color,
            task_count=task_count.get(t.id, 0),
            total_seconds=seconds.get(t.id, 0),
            session_count=sessions.get(t.id, 0),
        )
        for t in tags
    ]
    return TagSummaryListResponse(summaries=summaries, total=len(summaries))


@router.patch("/{tag_id}", response_model=TagResponse)
def update_tag(
    tag_id: int,
    tag_in: TagUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Renombra o recolorea una etiqueta."""
    tag = _get_owned_tag(session, current_user.id, tag_id)

    update_data = {k: v for k, v in tag_in.model_dump(exclude_unset=True).items() if v is not None}
    if "name" in update_data:
        update_data["name"] = _clean_name(session, current_user.id, update_data["name"], exclude_id=tag.id)

    for field, value in update_data.items():
        setattr(tag, field, value)

    session.add(tag)
    session.commit()
    session.refresh(tag)

    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Borra una etiqueta y la quita de sus tareas. Las tareas y su tiempo no se tocan."""
    tag = _get_owned_tag(session, current_user.id, tag_id)

    for link in session.exec(
        select(TaskTag).where(TaskTag.user_id == current_user.id, TaskTag.tag_id == tag.id)
    ).all():
        session.delete(link)
    session.delete(tag)
    session.commit()
