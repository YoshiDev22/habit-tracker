"""
Calendario de trabajo (épica 30, Fase 3): huso horario, país y días marcados a
mano. Los festivos oficiales salen de Nager.Date (backend/holidays.py). Todo
filtra por el usuario de la sesión; las rutas literales van antes que /{day_id}.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.database import get_session
from backend.days import DEFAULT_COUNTRY, DEFAULT_TIMEZONE, user_settings, valid_timezone
from backend.holidays import official_holidays
from backend.models import User, UserDay, UserSettings
from backend.schemas import (
    OfficialDay,
    UserDayCreate,
    UserDayResponse,
    WorkSettingsResponse,
    WorkSettingsUpdate,
    YearDaysResponse,
)

router = APIRouter(tags=["days"])


def _settings_response(settings) -> WorkSettingsResponse:
    if settings is None:
        return WorkSettingsResponse(timezone=DEFAULT_TIMEZONE, country=DEFAULT_COUNTRY, configured=False)
    return WorkSettingsResponse(timezone=settings.timezone, country=settings.country, configured=True)


@router.get("/settings", response_model=WorkSettingsResponse)
def get_work_settings(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Huso horario y país del usuario. `configured: false` hasta que se guarden:
    el frontend guarda entonces el huso del navegador."""
    return _settings_response(user_settings(session, current_user.id))


@router.put("/settings", response_model=WorkSettingsResponse)
def update_work_settings(body: WorkSettingsUpdate, session: Session = Depends(get_session),
                         current_user: User = Depends(get_current_user)):
    """Guarda el huso horario (nombre IANA) y/o el país (dos letras)."""
    if body.timezone is not None and not valid_timezone(body.timezone):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Huso horario desconocido: {body.timezone}")
    settings = user_settings(session, current_user.id) or UserSettings(
        user_id=current_user.id, timezone=DEFAULT_TIMEZONE, country=DEFAULT_COUNTRY)
    if body.timezone is not None:
        settings.timezone = body.timezone
    if body.country is not None:
        settings.country = body.country
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return _settings_response(settings)


@router.get("", response_model=YearDaysResponse)
def get_year_days(year: int = Query(ge=2000, le=2100), session: Session = Depends(get_session),
                  current_user: User = Depends(get_current_user)):
    """Los festivos oficiales del año de su país y los días que marcó a mano."""
    settings = user_settings(session, current_user.id)
    country = settings.country if settings else DEFAULT_COUNTRY
    own = session.exec(
        select(UserDay).where(
            UserDay.user_id == current_user.id,
            UserDay.date >= date_type(year, 1, 1),
            UserDay.date <= date_type(year, 12, 31),
        ).order_by(UserDay.date)
    ).all()
    worked = {d.date.isoformat() for d in own if d.kind == "laboral"}
    official = [
        OfficialDay(date=item["date"], name=item["name"], observed=item["date"] not in worked)
        for item in official_holidays(session, country, year)
    ]
    return YearDaysResponse(year=year, country=country, official=official,
                            own=[UserDayResponse.model_validate(d) for d in own])


@router.post("", response_model=UserDayResponse, status_code=status.HTTP_201_CREATED)
def mark_day(body: UserDayCreate, session: Session = Depends(get_session),
             current_user: User = Depends(get_current_user)):
    """Marca un día como libre (no se trabaja) o laboral (sí, aunque sea festivo).
    Un día ya marcado se reemplaza."""
    day = session.exec(
        select(UserDay).where(UserDay.user_id == current_user.id, UserDay.date == body.date)
    ).first() or UserDay(user_id=current_user.id, date=body.date, kind=body.kind)
    day.kind = body.kind
    day.name = (body.name or "").strip() or None
    session.add(day)
    session.commit()
    session.refresh(day)
    return UserDayResponse.model_validate(day)


@router.delete("/{day_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark_day(day_id: int, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Quita una marca: el día vuelve a ser como dice el calendario oficial."""
    day = session.exec(select(UserDay).where(UserDay.id == day_id, UserDay.user_id == current_user.id)).first()
    if not day:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Día no encontrado")
    session.delete(day)
    session.commit()
