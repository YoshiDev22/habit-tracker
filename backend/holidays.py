"""
Festivos oficiales por país, de Nager.Date (gratis y sin clave):

    GET https://date.nager.at/api/v3/PublicHolidays/{año}/{país}

Se piden una vez por país y año y se guardan en `holiday_cache`. Si la petición
falla (sin red, el servicio caído), se devuelve una lista vacía SIN guardarla,
para reintentar la próxima vez: un año sin festivos no se queda así para
siempre. Solo los festivos nacionales (`global`); los regionales los agrega
cada usuario como días libres propios.

Sin dependencias: urllib de la biblioteca estándar. Las pruebas reemplazan
`fetch_official` para no salir a internet.
"""
import json
import logging
import os
import time
import urllib.request
from datetime import date as date_type
from typing import Dict, List, Tuple

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import HolidayCache

NAGER_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
TIMEOUT_SECONDS = 8
RETRY_AFTER_SECONDS = 3600
log = logging.getLogger(__name__)

# Tras un fallo no se reintenta ese país y año durante una hora: si Nager.Date
# está caído, cada reporte esperaría el tiempo de espera completo (en memoria)
_failed_until: Dict[Tuple[str, int], float] = {}


def fetch_official(country: str, year: int) -> List[dict]:
    """Los festivos nacionales del país y año, de Nager.Date. Lanza si falla.
    Con HABIT_HOLIDAYS_OFFLINE=1 (las pruebas) no sale a internet."""
    if os.getenv("HABIT_HOLIDAYS_OFFLINE"):
        raise RuntimeError("festivos sin red (HABIT_HOLIDAYS_OFFLINE)")
    request = urllib.request.Request(
        NAGER_URL.format(year=year, country=country),
        headers={"Accept": "application/json", "User-Agent": "habit-tracker"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [
        {"date": item["date"], "name": item.get("localName") or item.get("name") or "Festivo"}
        for item in data
        if item.get("global", True)
    ]


def official_holidays(session: Session, country: str, year: int) -> List[dict]:
    """Los festivos de la caché o, si no están, de Nager.Date (y se guardan)."""
    cached = session.exec(
        select(HolidayCache).where(HolidayCache.country == country, HolidayCache.year == year)
    ).first()
    if cached:
        return cached.days
    if _failed_until.get((country, year), 0) > time.monotonic():
        return []
    try:
        days = fetch_official(country, year)
    except Exception as error:  # red, JSON raro, país desconocido: no rompe nada
        log.warning("No se pudieron obtener los festivos de %s %s: %s", country, year, error)
        _failed_until[(country, year)] = time.monotonic() + RETRY_AFTER_SECONDS
        return []
    session.add(HolidayCache(country=country, year=year, days=days))
    try:
        session.commit()
    except IntegrityError:
        # Otra petición los guardó a la vez
        session.rollback()
    return days


def official_holidays_between(session: Session, country: str, start: date_type, end: date_type) -> dict:
    """{fecha: nombre} de los festivos oficiales entre dos fechas, incluidas."""
    result = {}
    for year in range(start.year, end.year + 1):
        for item in official_holidays(session, country, year):
            day = date_type.fromisoformat(item["date"])
            if start <= day <= end:
                result[day] = item["name"]
    return result
