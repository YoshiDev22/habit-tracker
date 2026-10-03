"""
El calendario de trabajo de cada usuario (épica 30, Fase 3): su huso horario y
qué días son hábiles. Lo usan las métricas (backend/metrics.py) y, después, los
reportes.

Un día es **hábil** si es de lunes a viernes y no es:
- festivo oficial de su país (Nager.Date), salvo que lo marque "laboral";
- un día "libre" que el usuario agregó (un festivo local, un puente);
- un día de vacaciones (las pausas de la racha, `streak_pauses`).

Los días de descanso semanal de los hábitos (`users.rest_days`) no cambian esto:
son de la racha, no del trabajo.
"""
from dataclasses import dataclass
from datetime import date as date_type, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from backend.holidays import official_holidays_between
from backend.models import StreakPause, UserDay, UserSettings

DEFAULT_TIMEZONE = "America/Mexico_City"
DEFAULT_COUNTRY = "MX"


@dataclass
class WorkCalendar:
    timezone: str
    country: str
    configured: bool                  # False: valores por defecto, sin fila
    off_days: Dict[date_type, str]    # día no hábil entre semana -> por qué

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_workday(self, day: date_type) -> bool:
        return day.weekday() < 5 and day not in self.off_days


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def user_settings(session: Session, user_id: int) -> Optional[UserSettings]:
    return session.exec(select(UserSettings).where(UserSettings.user_id == user_id)).first()


def holiday_rest_days(session: Session, user_id: int, start: date_type, end: date_type) -> Dict[date_type, str]:
    """
    Los festivos que el usuario descansa entre dos fechas (incluidas), con su
    motivo: los oficiales de su país que no marcó "laboral", más sus días
    "libre". Cualquier día de la semana. Además de no ser hábiles, congelan la
    racha como un día de descanso (routers/habits.py, decisión 2026-10-03).
    """
    settings = user_settings(session, user_id)
    country = settings.country if settings else DEFAULT_COUNTRY
    rest: Dict[date_type, str] = {
        day: f"Festivo: {name}" for day, name in official_holidays_between(session, country, start, end).items()
    }
    for mark in session.exec(
        select(UserDay).where(UserDay.user_id == user_id, UserDay.date >= start, UserDay.date <= end)
    ).all():
        if mark.kind == "laboral":
            rest.pop(mark.date, None)
        else:
            rest[mark.date] = f"Día libre: {mark.name}" if mark.name else "Día libre"
    return rest


def work_calendar(session: Session, user_id: int, start: date_type, end: date_type) -> WorkCalendar:
    """El calendario del usuario entre dos fechas (incluidas)."""
    settings = user_settings(session, user_id)
    timezone = settings.timezone if settings and valid_timezone(settings.timezone) else DEFAULT_TIMEZONE
    country = settings.country if settings else DEFAULT_COUNTRY

    off: Dict[date_type, str] = dict(holiday_rest_days(session, user_id, start, end))
    for pause in session.exec(select(StreakPause).where(StreakPause.user_id == user_id)).all():
        day = max(pause.start_date, start)
        while day <= min(pause.end_date, end):
            off.setdefault(day, "Vacaciones")
            day += timedelta(days=1)
    # Solo importan entre semana: el sábado y el domingo ya no son hábiles
    off = {day: why for day, why in off.items() if day.weekday() < 5}
    return WorkCalendar(timezone=timezone, country=country, configured=settings is not None, off_days=off)
