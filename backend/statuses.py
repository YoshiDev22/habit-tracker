from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import Status, Project, Task


# Lo único fijo de un estado es su categoría: el código decide con ella (una
# tarea está hecha si su columna es "done", el pomodoro ofrece los proyectos
# "active") y el usuario es libre con el nombre, el color y cuántas hay.
CATEGORIES_BY_SCOPE = {
    "task": ("todo", "doing", "done"),
    "project": ("idea", "active", "paused", "done"),
}

# Los que recibe cada usuario la primera vez: (categoría, nombre, color).
DEFAULT_STATUSES = {
    "task": [
        ("todo", "Por hacer", "#95a5a6"),
        ("doing", "Haciendo", "#3498db"),
        ("done", "Hecho", "#2ecc71"),
    ],
    "project": [
        ("idea", "Ideas", "#9b59b6"),
        ("active", "En curso", "#3498db"),
        ("paused", "En pausa", "#f39c12"),
        ("done", "Terminado", "#2ecc71"),
    ],
}


def first_status_id(session: Session, user_id: int, scope: str, category: str) -> Optional[int]:
    """La primera columna (por orden) de una categoría: a donde va una tarea
    que se marca o desmarca con el checkbox, sin elegir columna."""
    return session.exec(
        select(Status.id).where(
            Status.user_id == user_id,
            Status.scope == scope,
            Status.category == category,
        ).order_by(Status.order, Status.id)
    ).first()


def get_owned_status(session: Session, user_id: int, status_id: int, scope: str) -> Status:
    """Un estado del usuario y del scope pedido, o el error HTTP que toca."""
    found = session.exec(
        select(Status).where(Status.id == status_id, Status.user_id == user_id)
    ).first()

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Estado no encontrado"
        )
    if found.scope != scope:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ese estado es de tipo '{found.scope}', no '{scope}'"
        )
    return found


def _seed_scope(session: Session, user_id: int, scope: str) -> None:
    exists = session.exec(
        select(Status.id).where(Status.user_id == user_id, Status.scope == scope)
    ).first()
    if exists is not None:
        return

    for order, (category, name, color) in enumerate(DEFAULT_STATUSES[scope]):
        session.add(Status(
            user_id=user_id, scope=scope, category=category,
            name=name, color=color, order=order,
        ))
    try:
        session.commit()
    except IntegrityError:
        # Otro request del mismo usuario los creó a la vez: la restricción
        # única por nombre lo frena, y los suyos valen igual que los nuestros.
        session.rollback()


def ensure_user_statuses(session: Session, user_id: int) -> None:
    """
    Crea los estados por defecto del usuario si no tiene, y asigna estado a
    los proyectos y tareas que todavía no lo tienen. Idempotente.

    Vive aquí y no en scripts/migrate.py por el orden del deploy: migrate.py
    corre ANTES de reiniciar el servicio, y la tabla `statuses` la crea
    create_all() al arrancar, después. Así que migrate.py solo añade las
    columnas status_id (NULL) y este relleno ocurre en el primer request.
    También cubre a los usuarios que se registren después, sin tocar /register.
    """
    for scope in DEFAULT_STATUSES:
        _seed_scope(session, user_id, scope)

    orphan_tasks = session.exec(
        select(Task).where(Task.user_id == user_id, Task.status_id == None)  # noqa: E711
    ).all()
    orphan_projects = session.exec(
        select(Project).where(Project.user_id == user_id, Project.status_id == None)  # noqa: E711
    ).all()
    if not orphan_tasks and not orphan_projects:
        return

    # Lo que ya existía se traduce sin perder nada: una tarea marcada va a
    # "Hecho" y una pendiente a "Por hacer"; los proyectos quedan "En curso".
    # is_active no se toca: un proyecto archivado sigue archivado.
    done_id = first_status_id(session, user_id, "task", "done")
    todo_id = first_status_id(session, user_id, "task", "todo")
    active_id = first_status_id(session, user_id, "project", "active")

    for t in orphan_tasks:
        t.status_id = done_id if t.is_done else todo_id
        session.add(t)
    for p in orphan_projects:
        p.status_id = active_id
        session.add(p)
    session.commit()
