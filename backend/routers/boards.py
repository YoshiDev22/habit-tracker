from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Board, BoardColumn, Task
from backend.schemas import (
    BoardCreate, BoardUpdate, BoardResponse, BoardListResponse,
    ColumnCreate, ColumnUpdate, ColumnResponse,
)
from backend.auth import get_current_user
from backend.boards import (
    COLUMN_CATEGORIES, add_board_with_columns, ensure_user_setup, get_owned_board,
)

router = APIRouter(tags=["boards"])


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre no puede estar vacío"
        )
    return cleaned


def _board_response(session: Session, board: Board) -> BoardResponse:
    columns = session.exec(
        select(BoardColumn).where(BoardColumn.board_id == board.id)
        .order_by(BoardColumn.order, BoardColumn.id)
    ).all()
    return BoardResponse(
        id=board.id,
        name=board.name,
        order=board.order,
        is_active=board.is_active,
        created_at=board.created_at,
        columns=[ColumnResponse.model_validate(c) for c in columns],
    )


def _board_name_taken(session: Session, user_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = select(Board.id).where(Board.user_id == user_id, Board.name == name)
    if exclude_id is not None:
        query = query.where(Board.id != exclude_id)
    return session.exec(query).first() is not None


def _active_board_count(session: Session, user_id: int) -> int:
    return session.exec(
        select(func.count()).select_from(Board).where(
            Board.user_id == user_id, Board.is_active == True  # noqa: E712
        )
    ).one()


def _board_task_count(session: Session, user_id: int, board_id: int) -> int:
    board_columns = select(BoardColumn.id).where(BoardColumn.board_id == board_id)
    return session.exec(
        select(func.count()).select_from(Task).where(
            Task.user_id == user_id, Task.column_id.in_(board_columns)
        )
    ).one()


# ==================== Tableros ====================

@router.get("", response_model=BoardListResponse)
def get_boards(
    include_inactive: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los tableros del usuario con sus columnas. La primera llamada crea
    "Mi tablero" y le asigna columna a las tareas que existían.
    """
    ensure_user_setup(session, current_user.id)

    query = select(Board).where(Board.user_id == current_user.id)
    if not include_inactive:
        query = query.where(Board.is_active == True)  # noqa: E712

    boards: List[Board] = session.exec(query.order_by(Board.order, Board.id)).all()

    return BoardListResponse(
        boards=[_board_response(session, b) for b in boards],
        total=len(boards)
    )


@router.post("", response_model=BoardResponse, status_code=status.HTTP_201_CREATED)
def create_board(
    board_in: BoardCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Crea un tablero con las columnas por defecto (Por hacer, Haciendo, Hecho)."""
    ensure_user_setup(session, current_user.id)

    name = _clean_name(board_in.name)
    if _board_name_taken(session, current_user.id, name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya tienes un tablero llamado '{name}'"
        )

    board = add_board_with_columns(session, current_user.id, name, board_in.order or 0)
    session.commit()
    session.refresh(board)

    return _board_response(session, board)


@router.patch("/{board_id}", response_model=BoardResponse)
def update_board(
    board_id: int,
    board_in: BoardUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Renombra, reordena o archiva un tablero. El último activo no se archiva."""
    board = get_owned_board(session, current_user.id, board_id)

    update_data = {k: v for k, v in board_in.model_dump(exclude_unset=True).items() if v is not None}

    if "name" in update_data:
        update_data["name"] = _clean_name(update_data["name"])
        if _board_name_taken(session, current_user.id, update_data["name"], exclude_id=board.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya tienes un tablero llamado '{update_data['name']}'"
            )

    if update_data.get("is_active") is False and board.is_active \
            and _active_board_count(session, current_user.id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es tu único tablero activo: crea otro antes de archivarlo"
        )

    for field, value in update_data.items():
        setattr(board, field, value)

    session.add(board)
    session.commit()
    session.refresh(board)

    return _board_response(session, board)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board(
    board_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Borra un tablero vacío y sus columnas. Con tareas devuelve 409: moverlas o
    archivar el tablero, que conserva todo. El último activo no se borra.
    """
    board = get_owned_board(session, current_user.id, board_id)

    tasks_inside = _board_task_count(session, current_user.id, board.id)
    if tasks_inside:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{board.name}' tiene {tasks_inside} tareas. Muévelas o archiva el tablero"
        )
    if board.is_active and _active_board_count(session, current_user.id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es tu único tablero activo y no se puede borrar"
        )

    for column in session.exec(select(BoardColumn).where(BoardColumn.board_id == board.id)).all():
        session.delete(column)
    session.delete(board)
    session.commit()


# ==================== Columnas ====================

def _get_board_column(session: Session, user_id: int, board_id: int, column_id: int) -> BoardColumn:
    column = session.exec(
        select(BoardColumn).where(
            BoardColumn.id == column_id,
            BoardColumn.board_id == board_id,
            BoardColumn.user_id == user_id
        )
    ).first()
    if not column:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Columna no encontrada"
        )
    return column


def _column_name_taken(session: Session, board_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    query = select(BoardColumn.id).where(BoardColumn.board_id == board_id, BoardColumn.name == name)
    if exclude_id is not None:
        query = query.where(BoardColumn.id != exclude_id)
    return session.exec(query).first() is not None


@router.post("/{board_id}/columns", response_model=ColumnResponse, status_code=status.HTTP_201_CREATED)
def create_column(
    board_id: int,
    column_in: ColumnCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Agrega una columna, por ejemplo "Bloqueado" de categoría doing. Sin order, va al final."""
    board = get_owned_board(session, current_user.id, board_id)

    if column_in.category not in COLUMN_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category debe ser una de: {', '.join(COLUMN_CATEGORIES)}"
        )

    name = _clean_name(column_in.name)
    if _column_name_taken(session, board.id, name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este tablero ya tiene una columna llamada '{name}'"
        )

    order = column_in.order
    if order is None:
        last = session.exec(
            select(func.max(BoardColumn.order)).where(BoardColumn.board_id == board.id)
        ).one()
        order = 0 if last is None else last + 1

    column = BoardColumn(
        board_id=board.id,
        user_id=current_user.id,
        category=column_in.category,
        name=name,
        color=column_in.color,
        order=order,
    )
    session.add(column)
    session.commit()
    session.refresh(column)

    return ColumnResponse.model_validate(column)


@router.patch("/{board_id}/columns/{column_id}", response_model=ColumnResponse)
def update_column(
    board_id: int,
    column_id: int,
    column_in: ColumnUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Renombra, cambia el color o reordena una columna. La categoría es fija."""
    column = _get_board_column(session, current_user.id, board_id, column_id)

    update_data = {k: v for k, v in column_in.model_dump(exclude_unset=True).items() if v is not None}

    if "name" in update_data:
        update_data["name"] = _clean_name(update_data["name"])
        if _column_name_taken(session, board_id, update_data["name"], exclude_id=column.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Este tablero ya tiene una columna llamada '{update_data['name']}'"
            )

    for field, value in update_data.items():
        setattr(column, field, value)

    session.add(column)
    session.commit()
    session.refresh(column)

    return ColumnResponse.model_validate(column)


@router.delete("/{board_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_column(
    board_id: int,
    column_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Borra una columna vacía. Con tareas devuelve 409: hay que moverlas antes.
    Tampoco se puede borrar la última "todo" (la entrada, donde llegan las
    tareas nuevas y vuelven las que se desmarcan) ni la última "done" (a
    donde las manda el checkbox). La última "doing" sí: no hace nada especial.
    """
    column = _get_board_column(session, current_user.id, board_id, column_id)

    in_use = session.exec(
        select(func.count()).select_from(Task).where(
            Task.user_id == current_user.id, Task.column_id == column.id
        )
    ).one()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{column.name}' tiene {in_use} tareas. Muévelas a otra columna antes de borrarla"
        )

    if column.category in ("todo", "done"):
        siblings = session.exec(
            select(func.count()).select_from(BoardColumn).where(
                BoardColumn.board_id == board_id, BoardColumn.category == column.category
            )
        ).one()
        if siblings <= 1:
            reason = (
                "es la columna de entrada, donde llegan las tareas nuevas"
                if column.category == "todo"
                else "es la única columna que marca las tareas como terminadas"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{column.name}' {reason}, y el tablero la necesita"
            )

    session.delete(column)
    session.commit()
