from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status


def resolve_client_today(client_today: Optional[date]) -> date:
    """
    "Hoy" para el usuario, no para el servidor.

    El VPS corre en UTC: para alguien en UTC−6, de 18:00 a medianoche la fecha
    del servidor ya es mañana. Todo lo que dependa de "hoy" (la racha, el tiempo
    de hoy del pomodoro) tiene que usar la fecha LOCAL del cliente, que el
    frontend manda como ?today=AAAA-MM-DD con getDateKey(new Date()) — el mismo
    criterio que ya sigue PomodoroSession.session_date.

    Sin parámetro se usa la fecha del servidor, para no romper a una pestaña con
    el JS viejo en caché. Con parámetro solo se acepta a ±1 día de la fecha UTC:
    ningún huso horario real (UTC−12 a UTC+14) se aleja más, así que cualquier
    otra fecha es un reloj roto o alguien pidiendo "hoy" en otro día.
    """
    if client_today is None:
        return date.today()

    utc_today = datetime.now(timezone.utc).date()
    if abs(client_today - utc_today) > timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha 'today' debe estar a un día como máximo de la fecha actual"
        )
    return client_today
