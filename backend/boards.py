from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import Board, BoardColumn, ProjectStatus, Project, Task


# Lo único fijo de una columna o de un estado de proyecto es su categoría: el
# código decide con ella (una tarea está hecha si su columna es "done", el
# pomodoro ofrece los proyectos "active") y el usuario es libre con el nombre,
# el color y cuántas hay.
COLUMN_CATEGORIES = ("todo", "doing", "done")
PROJECT_STATUS_CATEGORIES = ("idea", "active", "paused", "done")

DEFAULT_BOARD_NAME = "Mi tablero"

# Las que recibe cada tablero nuevo y cada usuario: (categoría, nombre, color).
DEFAULT_COLUMNS = [
    ("todo", "Por hacer", "#95a5a6"),
    ("doing", "Haciendo", "#3498db"),
    ("done", "Hecho", "#2ecc71"),
]
DEFAULT_PROJECT_STATUSES = [
    ("idea", "Ideas", "#9b59b6"),
    ("active", "En curso", "#3498db"),
    ("paused", "En pausa", "#f39c12"),
    ("done", "Terminado", "#2ecc71"),
]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def get_owned_board(session: Session, user_id: int, board_id: int) -> Board:
    board = session.exec(
        select(Board).where(Board.id == board_id, Board.user_id == user_id)
    ).first()
    if not board:
        raise _not_found("Tablero no encontrado")
    return board


def get_owned_column(session: Session, user_id: int, column_id: int) -> BoardColumn:
    column = session.exec(
        select(BoardColumn).where(BoardColumn.id == column_id, BoardColumn.user_id == user_id)
    ).first()
    if not column:
        raise _not_found("Columna no encontrada")
    return column


def get_owned_project_status(session: Session, user_id: int, status_id: int) -> ProjectStatus:
    found = session.exec(
        select(ProjectStatus).where(ProjectStatus.id == status_id, ProjectStatus.user_id == user_id)
    ).first()
    if not found:
        raise _not_found("Estado de proyecto no encontrado")
    return found


def default_board_id(session: Session, user_id: int) -> Optional[int]:
    """El primer tablero activo: a donde va una tarea creada sin decir dónde."""
    return session.exec(
        select(Board.id).where(Board.user_id == user_id, Board.is_active == True)  # noqa: E712
        .order_by(Board.order, Board.id)
    ).first()


def first_column_id(session: Session, board_id: int, category: str) -> Optional[int]:
    """La primera columna (por orden) de una categoría dentro de un tablero:
    a donde va una tarea que se marca o desmarca con el checkbox."""
    return session.exec(
        select(BoardColumn.id).where(
            BoardColumn.board_id == board_id,
            BoardColumn.category == category,
        ).order_by(BoardColumn.order, BoardColumn.id)
    ).first()


def first_project_status_id(session: Session, user_id: int, category: str) -> Optional[int]:
    return session.exec(
        select(ProjectStatus.id).where(
            ProjectStatus.user_id == user_id,
            ProjectStatus.category == category,
        ).order_by(ProjectStatus.order, ProjectStatus.id)
    ).first()


def add_board_with_columns(session: Session, user_id: int, name: str, order: int = 0) -> Board:
    """Crea un tablero con las columnas por defecto. Sin commit."""
    board = Board(user_id=user_id, name=name, order=order)
    session.add(board)
    session.flush()  # para tener board.id
    for column_order, (category, column_name, color) in enumerate(DEFAULT_COLUMNS):
        session.add(BoardColumn(
            board_id=board.id, user_id=user_id, category=category,
            name=column_name, color=color, order=column_order,
        ))
    return board


def _commit_seed(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        # Otro request del mismo usuario sembró a la vez: la restricción única
        # por nombre lo frena, y lo suyo vale igual que lo nuestro.
        session.rollback()


def ensure_user_setup(session: Session, user_id: int) -> None:
    """
    Deja al usuario listo para el tablero, y es idempotente:
    - estados de proyecto por defecto, si no tiene;
    - un tablero "Mi tablero" con sus columnas, si no tiene ninguno;
    - estado para los proyectos y columna para las tareas que no lo tengan.

    Vive aquí y no en scripts/migrate.py por el orden del deploy: migrate.py
    corre ANTES de reiniciar el servicio, y estas tablas las crea
    create_all() al arrancar, después. Así que migrate.py solo añade las
    columnas (NULL) y este relleno ocurre en el primer request. También cubre
    a los usuarios que se registren después, sin tocar /register.
    """
    has_statuses = session.exec(
        select(ProjectStatus.id).where(ProjectStatus.user_id == user_id)
    ).first()
    if has_statuses is None:
        for order, (category, name, color) in enumerate(DEFAULT_PROJECT_STATUSES):
            session.add(ProjectStatus(
                user_id=user_id, category=category, name=name, color=color, order=order,
            ))
        _commit_seed(session)

    has_board = session.exec(select(Board.id).where(Board.user_id == user_id)).first()
    if has_board is None:
        add_board_with_columns(session, user_id, DEFAULT_BOARD_NAME)
        _commit_seed(session)

    orphan_tasks = session.exec(
        select(Task).where(Task.user_id == user_id, Task.column_id == None)  # noqa: E711
    ).all()
    orphan_projects = session.exec(
        select(Project).where(Project.user_id == user_id, Project.status_id == None)  # noqa: E711
    ).all()
    if not orphan_tasks and not orphan_projects:
        return

    # Lo que ya existía se traduce sin perder nada: una tarea marcada va a
    # "Hecho" y una pendiente a "Por hacer" del primer tablero; los proyectos
    # quedan "En curso". is_active no se toca: lo archivado sigue archivado.
    board_id = default_board_id(session, user_id)
    if board_id is None:
        # Solo tableros archivados: las tareas sueltas van al primero de ellos
        board_id = session.exec(
            select(Board.id).where(Board.user_id == user_id).order_by(Board.order, Board.id)
        ).first()
    done_id = first_column_id(session, board_id, "done")
    todo_id = first_column_id(session, board_id, "todo")
    active_id = first_project_status_id(session, user_id, "active")

    for t in orphan_tasks:
        t.column_id = done_id if t.is_done else todo_id
        session.add(t)
    for p in orphan_projects:
        p.status_id = active_id
        session.add(p)
    session.commit()
