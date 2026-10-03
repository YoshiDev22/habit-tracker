"""
GET /api/metrics: las cifras de un periodo, calculadas en backend/metrics.py
(épica 30, Fase 3). Solo lee, y solo del usuario de la sesión.
"""
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from backend.auth import get_current_user
from backend.database import get_session
from backend.dates import resolve_client_today
from backend.metrics import compute_metrics
from backend.models import User

router = APIRouter(tags=["metrics"])

MAX_METRICS_DAYS = 400   # un año y un poco: el reporte anual cabe


@router.get("")
def get_metrics(
    date_from: date_type,
    date_to: date_type,
    today: Optional[date_type] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Métricas del periodo (fechas LOCALES, incluidas): horas, días con registro
    contra hábiles, promedio y mediana, origen, pomodoros cortados, sesiones
    nocturnas, fin de semana, horario habitual, tiempo por proyecto, tarea y
    etiqueta, y lo que hay que revisar (por confirmar, largas, solapes). Hasta
    `today`, la fecha local del cliente.
    """
    if date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="date_from no puede ser posterior a date_to")
    if (date_to - date_from).days + 1 > MAX_METRICS_DAYS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"El periodo no puede pasar de {MAX_METRICS_DAYS} días")
    return compute_metrics(session, current_user, date_from, date_to, resolve_client_today(today))
