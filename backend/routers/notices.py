"""
/api/notices: el centro de avisos (1.26), la campanita. Ver backend/notices.py.
Todo filtra por el usuario de la sesión.
"""
from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel, select

from backend.auth import get_current_user
from backend.database import get_session
from backend.dates import resolve_client_today
from backend.models import Notice, User, utc_now_naive
from backend.notices import INFO_KINDS, PENDING_KINDS, list_notices

router = APIRouter(tags=["notices"])


class NoticeRead(SQLModel):
    """Leer avisos informativos: los de estos ids, o todos si no se manda ninguno."""
    ids: Optional[List[int]] = None


def _habits_on(session: Session, user: User) -> bool:
    from backend.routers.auth import user_modules
    return user_modules(session, user.id)["habits"]["enabled"]


def _current_version() -> Optional[str]:
    """La versión que corre, si tiene Novedades (si no, no hay aviso)."""
    from backend.main import APP_VERSION, NOVEDADES
    return APP_VERSION if any(v["version"] == APP_VERSION for v in NOVEDADES) else None


@router.get("")
def get_notices(today: Optional[date_type] = None, session: Session = Depends(get_session),
                current_user: User = Depends(get_current_user)) -> dict:
    """Los avisos de la cuenta: pendientes (por confirmar, día sin anotar),
    informativos (reporte listo, Novedades) y hechos recientes, más cuántos
    piden atención (pendientes + informativos sin leer). `today` es la fecha
    local del cliente: el día sin anotar es su "ayer"."""
    return list_notices(session, current_user, resolve_client_today(today), _habits_on(session, current_user),
                        _current_version())


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notices(body: NoticeRead, session: Session = Depends(get_session),
                 current_user: User = Depends(get_current_user)):
    """Marca leídos los informativos (los pendientes se resuelven, no se leen)."""
    query = select(Notice).where(Notice.user_id == current_user.id, Notice.kind.in_(INFO_KINDS),
                                 Notice.read_at == None)  # noqa: E711
    if body.ids is not None:
        query = query.where(Notice.id.in_(body.ids[:500]))
    now = utc_now_naive()
    for notice in session.exec(query).all():
        notice.read_at = now
        session.add(notice)
    session.commit()


@router.post("/{notice_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_notice(notice_id: int, session: Session = Depends(get_session),
                   current_user: User = Depends(get_current_user)):
    """Descartar un pendiente ("no lo voy a anotar"). Deja de contar en el círculo rojo."""
    notice = session.exec(select(Notice).where(Notice.id == notice_id, Notice.user_id == current_user.id)).first()
    if notice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aviso no encontrado")
    if notice.kind not in PENDING_KINDS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese aviso solo se lee")
    notice.dismissed_at = utc_now_naive()
    session.add(notice)
    session.commit()
