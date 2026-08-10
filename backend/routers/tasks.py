from datetime import date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Project, Task, PomodoroSession
from backend.schemas import TaskCreate, TaskUpdate, TaskResponse, TaskListResponse
from backend.auth import get_current_user

router = APIRouter(tags=["tasks"])


@router.get("", response_model=TaskListResponse)
def get_tasks(
    project_id: Optional[int] = None,
    include_done: bool = True,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista las tareas del usuario, opcionalmente filtradas por proyecto.
    """
    query = select(Task).where(Task.user_id == current_user.id)

    if project_id is not None:
        query = query.where(Task.project_id == project_id)

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
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Crea una tarea dentro de un proyecto del usuario.
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

    new_task = Task(
        user_id=current_user.id,
        project_id=task_in.project_id,
        title=task_in.title,
        notes=task_in.notes,
        order=task_in.order or 0,
        is_done=False,
    )
    session.add(new_task)
    session.commit()
    session.refresh(new_task)

    return TaskResponse.model_validate(new_task)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente una tarea (título, notas, estado, orden,
    o moverla a otro proyecto). Marcar/desmarcar is_done actualiza
    completed_at automáticamente.
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

    update_data = task_in.model_dump(exclude_unset=True)

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

    if "is_done" in update_data:
        update_data["completed_at"] = date_type.today() if update_data["is_done"] else None

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
