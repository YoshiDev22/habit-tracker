from datetime import date as date_type
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import (
    User, Project, Task, BoardColumn, PomodoroSession,
    TaskChecklistItem, TaskComment, Tag, TaskTag, utc_now_naive,
)
from backend.schemas import (
    TaskCreate, TaskUpdate, TaskResponse, TaskListResponse,
    ChecklistItemCreate, ChecklistItemUpdate, ChecklistItemResponse, ChecklistListResponse,
    CommentCreate, CommentUpdate, CommentResponse, CommentListResponse,
)
from backend.auth import get_current_user
from backend.dates import resolve_client_today
from backend.boards import (
    ensure_user_setup, default_board_id, first_column_id, get_owned_board, get_owned_column,
    unassigned_project_id,
)

router = APIRouter(tags=["tasks"])


def _get_owned_task(session: Session, user_id: int, task_id: int) -> Task:
    task = session.exec(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    ).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada"
        )
    return task


def _set_task_tags(session: Session, user_id: int, task_id: int, tag_ids: List[int]) -> None:
    """Deja la tarea con exactamente estas etiquetas. Sin commit. 404 si alguna
    no es del usuario, antes de tocar nada."""
    wanted = set(tag_ids)
    if wanted:
        owned = set(session.exec(
            select(Tag.id).where(Tag.user_id == user_id, Tag.id.in_(wanted))
        ).all())
        if owned != wanted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Etiqueta no encontrada"
            )

    current = session.exec(
        select(TaskTag).where(TaskTag.user_id == user_id, TaskTag.task_id == task_id)
    ).all()
    for link in current:
        if link.tag_id not in wanted:
            session.delete(link)
    for tag_id in wanted - {link.tag_id for link in current}:
        session.add(TaskTag(user_id=user_id, task_id=task_id, tag_id=tag_id))


def _task_responses(session: Session, user_id: int, tasks: List[Task]) -> List[TaskResponse]:
    """TaskResponse con los conteos de checklist y comentarios, en dos
    consultas agrupadas para todas las tareas en vez de dos por tarea."""
    ids = [t.id for t in tasks]
    if not ids:
        return []

    checklist: Dict[int, Dict[str, int]] = {}
    rows = session.exec(
        select(TaskChecklistItem.task_id, TaskChecklistItem.is_done, func.count())
        .where(TaskChecklistItem.user_id == user_id, TaskChecklistItem.task_id.in_(ids))
        .group_by(TaskChecklistItem.task_id, TaskChecklistItem.is_done)
    ).all()
    for task_id, is_done, count in rows:
        entry = checklist.setdefault(task_id, {"total": 0, "done": 0})
        entry["total"] += count
        if is_done:
            entry["done"] += count

    column_ids = {t.column_id for t in tasks if t.column_id is not None}
    board_by_column = dict(session.exec(
        select(BoardColumn.id, BoardColumn.board_id).where(BoardColumn.id.in_(column_ids))
    ).all()) if column_ids else {}

    tags_by_task: Dict[int, List[int]] = {}
    for task_id, tag_id in session.exec(
        select(TaskTag.task_id, TaskTag.tag_id)
        .where(TaskTag.user_id == user_id, TaskTag.task_id.in_(ids))
        .order_by(TaskTag.tag_id)
    ).all():
        tags_by_task.setdefault(task_id, []).append(tag_id)

    comments = dict(session.exec(
        select(TaskComment.task_id, func.count())
        .where(TaskComment.user_id == user_id, TaskComment.task_id.in_(ids))
        .group_by(TaskComment.task_id)
    ).all())

    responses = []
    for t in tasks:
        r = TaskResponse.model_validate(t)
        r.checklist_total = checklist.get(t.id, {}).get("total", 0)
        r.checklist_done = checklist.get(t.id, {}).get("done", 0)
        r.comment_count = comments.get(t.id, 0)
        r.board_id = board_by_column.get(t.column_id)
        r.tag_ids = tags_by_task.get(t.id, [])
        responses.append(r)
    return responses


@router.get("", response_model=TaskListResponse)
def get_tasks(
    project_id: Optional[int] = None,
    board_id: Optional[int] = None,
    column_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    include_done: bool = True,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista las tareas del usuario, opcionalmente filtradas por proyecto,
    tablero, columna o etiqueta.
    """
    ensure_user_setup(session, current_user.id)

    query = select(Task).where(Task.user_id == current_user.id)

    if project_id is not None:
        query = query.where(Task.project_id == project_id)

    if board_id is not None:
        board_columns = select(BoardColumn.id).where(
            BoardColumn.board_id == board_id,
            BoardColumn.user_id == current_user.id
        )
        query = query.where(Task.column_id.in_(board_columns))

    if column_id is not None:
        query = query.where(Task.column_id == column_id)

    if tag_id is not None:
        tagged = select(TaskTag.task_id).where(
            TaskTag.user_id == current_user.id,
            TaskTag.tag_id == tag_id
        )
        query = query.where(Task.id.in_(tagged))

    if not include_done:
        query = query.where(Task.is_done == False)

    tasks = session.exec(query.order_by(Task.order, Task.id)).all()

    return TaskListResponse(
        tasks=_task_responses(session, current_user.id, tasks),
        total=len(tasks)
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: TaskCreate,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Crea una tarea con su proyecto (etiqueta); sin project_id va a
    "Sin asignar". Dónde queda:
    - column_id: en esa columna. Si es "done", nace hecha, con
      completed_at = ?today.
    - board_id sin column_id: en la primera columna "todo" de ese tablero.
    - ninguno: en la primera "todo" del primer tablero activo.
    """
    ensure_user_setup(session, current_user.id)

    if task_in.project_id is None:
        project_id = unassigned_project_id(session, current_user.id)
    else:
        project = session.exec(
            select(Project).where(
                Project.id == task_in.project_id,
                Project.user_id == current_user.id
            )
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado"
            )
        project_id = project.id

    if task_in.column_id is not None:
        column = get_owned_column(session, current_user.id, task_in.column_id)
        column_id, is_done = column.id, column.category == "done"
    else:
        if task_in.board_id is not None:
            board_id = get_owned_board(session, current_user.id, task_in.board_id).id
        else:
            board_id = default_board_id(session, current_user.id)
        column_id, is_done = first_column_id(session, board_id, "todo"), False

    new_task = Task(
        user_id=current_user.id,
        project_id=project_id,
        title=task_in.title,
        notes=task_in.notes,
        order=task_in.order or 0,
        column_id=column_id,
        is_done=is_done,
        completed_at=resolve_client_today(today) if is_done else None,
    )
    session.add(new_task)
    session.flush()  # para tener new_task.id
    if task_in.tag_ids:
        _set_task_tags(session, current_user.id, new_task.id, task_in.tag_ids)
    session.commit()
    session.refresh(new_task)

    return _task_responses(session, current_user.id, [new_task])[0]


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente una tarea (título, notas, orden, cambiarle el
    proyecto o moverla de columna, incluso a la de otro tablero).
    project_id: null la deja en "Sin asignar". Al cambiar de proyecto, el
    tiempo registrado en la tarea se va con ella.

    is_done y column_id van siempre juntos:
    - column_id (mover de columna) manda: is_done pasa a ser "la columna es
      de categoría done".
    - is_done solo (el checkbox) mueve la tarea a la primera columna "done"
      o "todo" DE SU MISMO TABLERO, salvo que ya esté en una columna de la
      categoría correcta.

    completed_at se pone al PASAR a hecha, con la fecha LOCAL del cliente
    (?today=AAAA-MM-DD, ver resolve_client_today), no la del servidor en UTC;
    moverla entre dos columnas "done" conserva la fecha original. Al dejar
    de estar hecha se borra.
    """
    task = session.exec(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == current_user.id
        )
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tarea no encontrada"
        )

    # El relleno puede haberle asignado columna a esta misma tarea
    ensure_user_setup(session, current_user.id)
    session.refresh(task)

    update_data = task_in.model_dump(exclude_unset=True)

    # Un null explícito no significa nada para estos dos: se ignora en vez de
    # dejar la tarea sin columna o con is_done nulo.
    for field in ("column_id", "is_done"):
        if field in update_data and update_data[field] is None:
            del update_data[field]

    if "project_id" in update_data and update_data["project_id"] is None:
        update_data["project_id"] = unassigned_project_id(session, current_user.id)
    elif "project_id" in update_data:
        target_project = session.exec(
            select(Project).where(
                Project.id == update_data["project_id"],
                Project.user_id == current_user.id
            )
        ).first()
        if not target_project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proyecto no encontrado"
            )

    if "column_id" in update_data:
        column = get_owned_column(session, current_user.id, update_data["column_id"])
        update_data["is_done"] = column.category == "done"
    elif "is_done" in update_data:
        current = session.get(BoardColumn, task.column_id)
        if (current.category == "done") != update_data["is_done"]:
            category = "done" if update_data["is_done"] else "todo"
            update_data["column_id"] = first_column_id(session, current.board_id, category)

    if "is_done" in update_data:
        if update_data["is_done"] and not task.is_done:
            update_data["completed_at"] = resolve_client_today(today)
        elif not update_data["is_done"]:
            update_data["completed_at"] = None

    tag_ids = update_data.pop("tag_ids", None)
    if tag_ids is not None:
        _set_task_tags(session, current_user.id, task.id, tag_ids)

    # El tiempo es de la tarea: si cambia de proyecto, sus sesiones también.
    # Sin esto, asignarle proyecto a una tarea de "Sin asignar" dejaba sus
    # horas en "Sin asignar" para siempre.
    if "project_id" in update_data and update_data["project_id"] != task.project_id:
        for s in session.exec(
            select(PomodoroSession).where(
                PomodoroSession.user_id == current_user.id,
                PomodoroSession.task_id == task.id
            )
        ).all():
            s.project_id = update_data["project_id"]
            session.add(s)

    for field, value in update_data.items():
        setattr(task, field, value)

    session.add(task)
    session.commit()
    session.refresh(task)

    return _task_responses(session, current_user.id, [task])[0]


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Elimina permanentemente una tarea, con su checklist y sus comentarios."""
    task = _get_owned_task(session, current_user.id, task_id)

    delete_task_details(session, current_user.id, [task_id])

    # El tiempo sigue siendo real aunque la tarea se borre: conservamos las
    # sesiones (y el total del proyecto), solo se les quita la referencia.
    pomodoro_sessions = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.task_id == task_id,
            PomodoroSession.user_id == current_user.id
        )
    ).all()
    for s in pomodoro_sessions:
        s.task_id = None
        session.add(s)

    session.delete(task)
    session.commit()


def delete_task_details(session: Session, user_id: int, task_ids: List[int]) -> None:
    """Borra el checklist, los comentarios y las etiquetas (el vínculo, no la
    etiqueta) de unas tareas. Sin commit: lo
    hace quien borra las tareas, para que todo caiga en la misma transacción.
    Lo usa también DELETE /api/projects/{id}."""
    if not task_ids:
        return
    for model in (TaskChecklistItem, TaskComment, TaskTag):
        rows = session.exec(
            select(model).where(model.user_id == user_id, model.task_id.in_(task_ids))
        ).all()
        for row in rows:
            session.delete(row)


# ==================== Checklist ====================

def _get_owned_item(session: Session, user_id: int, task_id: int, item_id: int) -> TaskChecklistItem:
    item = session.exec(
        select(TaskChecklistItem).where(
            TaskChecklistItem.id == item_id,
            TaskChecklistItem.task_id == task_id,
            TaskChecklistItem.user_id == user_id
        )
    ).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Elemento del checklist no encontrado"
        )
    return item


def _clean_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} no puede estar vacío"
        )
    return cleaned


@router.get("/{task_id}/checklist", response_model=ChecklistListResponse)
def get_checklist(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Checklist de una tarea, en orden."""
    _get_owned_task(session, current_user.id, task_id)

    items = session.exec(
        select(TaskChecklistItem).where(
            TaskChecklistItem.task_id == task_id,
            TaskChecklistItem.user_id == current_user.id
        ).order_by(TaskChecklistItem.order, TaskChecklistItem.id)
    ).all()

    return ChecklistListResponse(
        items=[ChecklistItemResponse.model_validate(i) for i in items],
        total=len(items)
    )


@router.post("/{task_id}/checklist", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
def create_checklist_item(
    task_id: int,
    item_in: ChecklistItemCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Agrega una línea al checklist. Sin order, va al final."""
    _get_owned_task(session, current_user.id, task_id)

    order = item_in.order
    if order is None:
        last = session.exec(
            select(func.max(TaskChecklistItem.order)).where(
                TaskChecklistItem.task_id == task_id,
                TaskChecklistItem.user_id == current_user.id
            )
        ).one()
        order = 0 if last is None else last + 1

    item = TaskChecklistItem(
        user_id=current_user.id,
        task_id=task_id,
        text=_clean_text(item_in.text, "El texto"),
        order=order,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    return ChecklistItemResponse.model_validate(item)


@router.patch("/{task_id}/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    task_id: int,
    item_id: int,
    item_in: ChecklistItemUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Marca, renombra o reordena una línea del checklist."""
    item = _get_owned_item(session, current_user.id, task_id, item_id)

    update_data = item_in.model_dump(exclude_unset=True)
    update_data = {k: v for k, v in update_data.items() if v is not None}
    if "text" in update_data:
        update_data["text"] = _clean_text(update_data["text"], "El texto")

    for field, value in update_data.items():
        setattr(item, field, value)

    session.add(item)
    session.commit()
    session.refresh(item)

    return ChecklistItemResponse.model_validate(item)


@router.delete("/{task_id}/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_checklist_item(
    task_id: int,
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Borra una línea del checklist."""
    item = _get_owned_item(session, current_user.id, task_id, item_id)
    session.delete(item)
    session.commit()


# ==================== Comentarios ====================

def _author_name(user: Optional[User]) -> str:
    if user is None:
        return "Usuario eliminado"
    return user.display_name or user.email


def _comment_response(comment: TaskComment, author: Optional[User]) -> CommentResponse:
    return CommentResponse(
        id=comment.id,
        task_id=comment.task_id,
        author_id=comment.author_id,
        author_name=_author_name(author),
        body=comment.body,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


def _get_own_comment(session: Session, current_user: User, task_id: int, comment_id: int) -> TaskComment:
    """Un comentario de una tarea del usuario. Editarlo o borrarlo es solo
    cosa de su autor: hoy siempre coincide con el dueño, pero no mañana."""
    comment = session.exec(
        select(TaskComment).where(
            TaskComment.id == comment_id,
            TaskComment.task_id == task_id,
            TaskComment.user_id == current_user.id
        )
    ).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comentario no encontrado"
        )
    if comment.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo quien escribió el comentario puede cambiarlo"
        )
    return comment


@router.get("/{task_id}/comments", response_model=CommentListResponse)
def get_comments(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Comentarios de una tarea, del más viejo al más nuevo, con su autor."""
    _get_owned_task(session, current_user.id, task_id)

    comments = session.exec(
        select(TaskComment).where(
            TaskComment.task_id == task_id,
            TaskComment.user_id == current_user.id
        ).order_by(TaskComment.created_at, TaskComment.id)
    ).all()

    author_ids = {c.author_id for c in comments}
    authors = {
        u.id: u for u in session.exec(select(User).where(User.id.in_(author_ids))).all()
    } if author_ids else {}

    return CommentListResponse(
        comments=[_comment_response(c, authors.get(c.author_id)) for c in comments],
        total=len(comments)
    )


@router.post("/{task_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    task_id: int,
    comment_in: CommentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Comenta una tarea. El autor es quien hace la petición."""
    task = _get_owned_task(session, current_user.id, task_id)

    comment = TaskComment(
        user_id=task.user_id,
        task_id=task_id,
        author_id=current_user.id,
        body=_clean_text(comment_in.body, "El comentario"),
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)

    return _comment_response(comment, current_user)


@router.patch("/{task_id}/comments/{comment_id}", response_model=CommentResponse)
def update_comment(
    task_id: int,
    comment_id: int,
    comment_in: CommentUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Edita un comentario propio. Conserva la fecha original y marca edited_at."""
    comment = _get_own_comment(session, current_user, task_id, comment_id)

    comment.body = _clean_text(comment_in.body, "El comentario")
    comment.edited_at = utc_now_naive()
    session.add(comment)
    session.commit()
    session.refresh(comment)

    return _comment_response(comment, current_user)


@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    task_id: int,
    comment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Borra un comentario propio."""
    comment = _get_own_comment(session, current_user, task_id, comment_id)
    session.delete(comment)
    session.commit()
