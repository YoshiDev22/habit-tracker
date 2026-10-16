"""
/api/feedback: "Reportar un problema" desde Mi perfil (1.27, épica 32). Solo
guarda: lo lee YoshiDev22 en el panel de administración, que la app pública no
monta. Cada cuenta puede enviar FEEDBACK_DAILY_LIMIT al día (día UTC).
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend import ratelimit, security_log
from backend.auth import get_current_user
from backend.database import get_session
from backend.models import Feedback, User, utc_now_naive
from backend.schemas import FeedbackCreate, FeedbackResponse

router = APIRouter(tags=["feedback"])

FEEDBACK_DAILY_LIMIT = 5


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def report_problem(body: FeedbackCreate, request: Request, session: Session = Depends(get_session),
                   current_user: User = Depends(get_current_user)) -> Feedback:
    """Guarda un problema reportado. 429 con Retry-After pasado el límite del día."""
    now = utc_now_naive()
    start = _day_start(now)
    sent_today = session.exec(select(func.count(Feedback.id)).where(
        Feedback.user_id == current_user.id, Feedback.created_at >= start)).one()
    if sent_today >= FEEDBACK_DAILY_LIMIT:
        security_log.record("feedback_limit", ratelimit.client_ip(request), current_user.id)
        wait = int((start + timedelta(days=1) - now).total_seconds()) + 1
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Ya enviaste {FEEDBACK_DAILY_LIMIT} reportes hoy. Puedes enviar otro mañana.",
                            headers={"Retry-After": str(wait)})
    feedback = Feedback(user_id=current_user.id, created_at=now, text=body.text, details=body.details)
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback
