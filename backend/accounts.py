"""
Borrar una cuenta (BACKLOG 26, parte sin correo). Dos caminos, a elección del
usuario: "irme unos días" programa el borrado para dentro de GRACE_DAYS
(users.delete_after) y entrar antes deja conservarla; "borrar ahora" lo hace al
momento. Los programados que ya vencieron los borra scripts/purge_accounts.py,
desde el mismo timer diario de los reportes.
"""
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import delete
from sqlmodel import Session, SQLModel, select

from backend.models import User, utc_now_naive

GRACE_DAYS = 30


def purge_user(session: Session, user: User) -> None:
    """
    Borra la cuenta y todo lo suyo: cada tabla con user_id, de las que dependen
    de otras hacia las de las que dependen, y al final el usuario. Las tablas
    que no son de nadie (holiday_cache) no se tocan. Hace commit.
    """
    user_id = user.id
    for table in reversed(SQLModel.metadata.sorted_tables):
        if table.name != User.__tablename__ and "user_id" in table.columns:
            session.exec(delete(table).where(table.c.user_id == user_id))
    session.delete(user)
    session.commit()


def schedule_deletion(user: User, now: datetime = None) -> datetime:
    """Programa el borrado; no hace commit."""
    user.delete_after = (now or utc_now_naive()) + timedelta(days=GRACE_DAYS)
    return user.delete_after


def due_for_purge(session: Session, now: datetime = None) -> List[User]:
    """Las cuentas con el borrado programado ya vencido."""
    now = now or utc_now_naive()
    return list(session.exec(select(User).where(User.delete_after.is_not(None), User.delete_after <= now)).all())
