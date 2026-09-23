from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import Board, BoardColumn, Project, Task


# Lo único fijo de una columna es su categoría: el código decide con ella (una
# tarea está hecha si su columna es "done", las nuevas llegan a la primera
# "todo") y el usuario es libre con el nombre, el color y cuántas hay.
COLUMN_CATEGORIES = ("todo", "doing", "done")

DEFAULT_BOARD_NAME = "Mi tablero"
UNASSIGNED_PROJECT_NAME = "Sin asignar"

# Las que recibe cada tablero nuevo: (categoría, nombre, color).
DEFAULT_COLUMNS = [
    ("todo", "Por hacer", "#95a5a6"),
    ("doing", "Haciendo", "#3498db"),
    ("done", "Hecho", "#2ecc71"),
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


def unassigned_project_id(session: Session, user_id: int) -> Optional[int]:
    """El proyecto "Sin asignar" del usuario: el de las tareas sin proyecto."""
    return session.exec(
        select(Project.id).where(Project.user_id == user_id, Project.is_system == True)  # noqa: E712
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
    - el proyecto "Sin asignar", si no lo tiene;
    - columna para las tareas que no la tengan.

    "Mi tablero" solo se crea si hay tareas que acomodar (las que existían
    antes de los tableros): un usuario nuevo empieza sin tableros y la
    pantalla le ofrece crear el primero. Crear una tarea sin tablero lo crea
    en ese momento (ver create_task).

    Vive aquí y no en scripts/migrate.py por el orden del deploy: migrate.py
    corre ANTES de reiniciar el servicio, y estas tablas las crea
    create_all() al arrancar, después. Así que migrate.py solo añade las
    columnas (NULL) y este relleno ocurre en el primer request. También cubre
    a los usuarios que se registren después, sin tocar /register.
    """
    if unassigned_project_id(session, user_id) is None:
        # Si el usuario ya tenía un proyecto llamado así, ese pasa a ser el
        # suyo: lo que tenga dentro es, justamente, lo que no tiene proyecto.
        same_name = session.exec(
            select(Project).where(Project.user_id == user_id, Project.name == UNASSIGNED_PROJECT_NAME)
        ).first()
        if same_name is not None:
            same_name.is_system = True
            same_name.is_active = True  # "Sin asignar" no se archiva
            session.add(same_name)
        else:
            session.add(Project(
                user_id=user_id, name=UNASSIGNED_PROJECT_NAME, color="#95a5a6", is_system=True,
            ))
        _commit_seed(session)

    orphan_tasks = session.exec(
        select(Task).where(Task.user_id == user_id, Task.column_id == None)  # noqa: E711
    ).all()
    if not orphan_tasks:
        return

    if session.exec(select(Board.id).where(Board.user_id == user_id)).first() is None:
        add_board_with_columns(session, user_id, DEFAULT_BOARD_NAME)
        _commit_seed(session)

    # Lo que ya existía se traduce sin perder nada: una tarea marcada va a
    # "Hecho" y una pendiente a "Por hacer" del primer tablero.
    board_id = default_board_id(session, user_id)
    if board_id is None:
        # Solo tableros archivados: las tareas sueltas van al primero de ellos
        board_id = session.exec(
            select(Board.id).where(Board.user_id == user_id).order_by(Board.order, Board.id)
        ).first()
    done_id = first_column_id(session, board_id, "done")
    todo_id = first_column_id(session, board_id, "todo")

    for t in orphan_tasks:
        t.column_id = done_id if t.is_done else todo_id
        session.add(t)
    session.commit()
