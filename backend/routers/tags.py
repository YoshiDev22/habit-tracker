from datetime import date as date_type
from typing import Dict, List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    tag_ids: Optional[List[int]] = Query(default=None),
    date_from: Optional[date_type] = None,
    date_to: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Tiempo de enfoque por etiqueta, opcionalmente entre dos fechas
    (session_date, la fecha local del usuario).

    - summaries: desglose por etiqueta. Una sesión cuenta en cada etiqueta de
      su tarea, así que estos totales no se suman entre sí.
    - combined_*: las sesiones con CUALQUIERA de las etiquetas de ?tag_ids=
      (repetible: ?tag_ids=1&tag_ids=2), o con alguna etiqueta si no se pasa;
      cada sesión UNA vez.
    - untagged_*: sesiones sin ninguna etiqueta, con o sin tarea.
    """
    tags = session.exec(
        select(Tag).where(Tag.user_id == current_user.id).order_by(Tag.name)
    ).all()

    tags_by_task: Dict[int, Set[int]] = {}
    for task_id, tag_id in session.exec(
        select(TaskTag.task_id, TaskTag.tag_id).where(TaskTag.user_id == current_user.id)
    ).all():
        tags_by_task.setdefault(task_id, set()).add(tag_id)

    selected = set(tag_ids) if tag_ids else {t.id for t in tags}

    query = select(PomodoroSession).where(
        PomodoroSession.user_id == current_user.id,
        PomodoroSession.mode == "focus",
    )
    if date_from is not None:
        query = query.where(PomodoroSession.session_date >= date_from)
    if date_to is not None:
        query = query.where(PomodoroSession.session_date <= date_to)

    seconds: Dict[int, int] = {}
    sessions: Dict[int, int] = {}
    combined_seconds = combined_count = untagged_seconds = untagged_count = 0
    for s in session.exec(query).all():
        session_tags = tags_by_task.get(s.task_id, set())
        if not session_tags:
            untagged_seconds += s.duration_seconds
            untagged_count += 1
            continue
        for tag_id in session_tags:
            seconds[tag_id] = seconds.get(tag_id, 0) + s.duration_seconds
            sessions[tag_id] = sessions.get(tag_id, 0) + 1
        if session_tags & selected:
            combined_seconds += s.duration_seconds
            combined_count += 1

    task_count: Dict[int, int] = {}
    for task_tags in tags_by_task.values():
        for tag_id in task_tags:
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
    return TagSummaryListResponse(
        summaries=summaries,
        total=len(summaries),
        combined_seconds=combined_seconds,
        combined_session_count=combined_count,
        untagged_seconds=untagged_seconds,
        untagged_session_count=untagged_count,
    )


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
