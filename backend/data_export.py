"""
Descargar mis datos (1.28, BACKLOG 39): todo lo que la instancia guarda de una
cuenta, en un JSON. Es el derecho de acceso de la ley de datos personales
(art. 32: se cumple también con documentos electrónicos).

Recorre lo mismo que purge_user() (backend/accounts.py): cada tabla con
user_id. Así una tabla nueva sale sola en la descarga, igual que se borra sola
con la cuenta, y test_data_export.py exige que coincidan. De la fila del
usuario salen todos los campos menos los que solo sirven para la seguridad de
la sesión (el hash de la contraseña y la versión de los tokens).
"""
import os
from datetime import date, datetime
from typing import Any, Dict

from sqlalchemy import select as sa_select
from sqlmodel import Session, SQLModel

from backend.models import User, utc_now_naive

USER_HIDDEN = {"hashed_password", "token_version"}

# La versión que corre, leída una vez como en main.py (importar main desde un
# router sería circular)
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"),
          encoding="utf-8") as f:
    APP_VERSION = f.read().strip()


def _plain(value: Any) -> Any:
    """Un valor de la base, como lo entiende JSON (fechas en ISO, sin huso: UTC)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def user_tables():
    """Las tablas de una cuenta: las que tienen user_id, en orden alfabético."""
    return sorted((t for t in SQLModel.metadata.sorted_tables
                   if t.name != User.__tablename__ and "user_id" in t.columns), key=lambda t: t.name)


def export_user(session: Session, user: User) -> Dict[str, Any]:
    account = {column: _plain(getattr(user, column)) for column in User.__table__.columns.keys()
               if column not in USER_HIDDEN}
    tables = {}
    for table in user_tables():
        # execute() y no exec(): con una tabla (no un modelo), exec() da solo la primera columna
        rows = session.execute(sa_select(table).where(table.c.user_id == user.id)
                                .order_by(*table.primary_key.columns)).mappings().all()
        tables[table.name] = [{key: _plain(value) for key, value in row.items()} for row in rows]
    return {
        "app": "Habit Tracker",
        "version": APP_VERSION,
        "exported_at": utc_now_naive().isoformat(),
        "note": ("Todo lo que esta instalación guarda de tu cuenta. Las fechas con hora van en UTC; "
                 "las fechas sin hora son de tu día local."),
        "account": account,
        "tables": tables,
    }
