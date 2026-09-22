from datetime import date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Project, Task, Status, PomodoroSession
from backend.schemas import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
from backend.auth import get_current_user
from backend.dates import resolve_client_today
from backend.statuses import ensure_user_statuses, first_status_id, get_owned_status

router = APIRouter(tags=["tasks"])


@router.get("", response_model=TaskListResponse)
def get_tasks(
    project_id: Optional[int] = None,
    status_id: Optional[int] = None,
    include_done: bool = True,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista las tareas del usuario, opcionalmente filtradas por proyecto o
    por columna del tablero.
    """
    ensure_user_statuses(session, current_user.id)

    query = select(Task).where(Task.user_id == current_user.id)

    if project_id is not None:
        query = query.where(Task.project_id == project_id)

    if status_id is not None:
        query = query.where(Task.status_id == status_id)

    if not include_done:
        query = query.where(Task.is_done == False)

    tasks = session.exec(query.order_by(Task.order, Task.id)).all()

    return TaskListResponse(
        tasks=[TaskResponse.model_validate(t) for t in tasks],
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
    Crea una tarea dentro de un proyecto del usuario. Sin status_id va a la
    primera columna "todo"; creada directamente en una columna "done" nace
    hecha, con completed_at = ?today.
    """
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

    ensure_user_statuses(session, current_user.id)

    if task_in.status_id is not None:
        column = get_owned_status(session, current_user.id, task_in.status_id, "task")
        status_id, is_done = column.id, column.category == "done"
    else:
        status_id, is_done = first_status_id(session, current_user.id, "task", "todo"), False

    new_task = Task(
        user_id=current_user.id,
        project_id=task_in.project_id,
        title=task_in.title,
        notes=task_in.notes,
        order=task_in.order or 0,
        status_id=status_id,
        is_done=is_done,
        completed_at=resolve_client_today(today) if is_done else None,
    )
    session.add(new_task)
    session.commit()
    session.refresh(new_task)

    return TaskResponse.model_validate(new_task)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente una tarea (título, notas, estado, orden,
    o moverla a otro proyecto).

    is_done y status_id van siempre juntos:
    - status_id (mover de columna) manda: is_done pasa a ser "la columna es
      de categoría done".
    - is_done solo (el checkbox) mueve la tarea a la primera columna "done"
      o "todo", salvo que ya esté en una columna de la categoría correcta.

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
    ensure_user_statuses(session, current_user.id)
    session.refresh(task)

    update_data = task_in.model_dump(exclude_unset=True)

    # Un null explícito no significa nada para estos dos: se ignora en vez de
    # dejar la tarea sin columna o con is_done nulo.
    for field in ("status_id", "is_done"):
        if field in update_data and update_data[field] is None:
            del update_data[field]

    if "project_id" in update_data:
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

    if "status_id" in update_data:
        column = get_owned_status(session, current_user.id, update_data["status_id"], "task")
        update_data["is_done"] = column.category == "done"
    elif "is_done" in update_data:
        current = session.get(Status, task.status_id) if task.status_id else None
        current_done = current is not None and current.category == "done"
        if current is None or current_done != update_data["is_done"]:
            category = "done" if update_data["is_done"] else "todo"
            update_data["status_id"] = first_status_id(session, current_user.id, "task", category)

    if "is_done" in update_data:
        if update_data["is_done"] and not task.is_done:
            update_data["completed_at"] = resolve_client_today(today)
        elif not update_data["is_done"]:
            update_data["completed_at"] = None

    for field, value in update_data.items():
        setattr(task, field, value)

    session.add(task)
    session.commit()
    session.refresh(task)

    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Elimina permanentemente una tarea."""
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
