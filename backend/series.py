"""
La regla de la serie de los cobros que se repiten, sin base de datos: la usan
los gastos recurrentes de Costos (backend/recurring_costs.py) y los fijos de
Finanzas (backend/finance.py), para que el "31 cae en el último día de un mes
más corto" viva en un solo lugar.

Una serie es un objeto con start_date, frequency, generated (cobros ya hechos
o saltados) y end_date (None = sin fin). Una quincenal de Finanzas puede traer
first_day y second_day (sus dos días de pago); sin ellos, el 15 y el último.

También vive aquí el periodo de Finanzas (mes o quincena), por la misma razón:
el servidor lo calcula y la pantalla solo lo pinta.
"""
import calendar
from datetime import date as date_type, timedelta
from typing import Optional, Tuple


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


SEMIMONTHLY_DAYS = (15, 31)   # el 15 y el último día: el 31 se recorta


def _semimonthly(start: date_type, n: int, days: Tuple[int, int] = SEMIMONTHLY_DAYS) -> date_type:
    """El cobro n de una quincenal: sus dos días de cada mes (el menor primero;
    un día que el mes no tiene cae en el último), empezando por el primero de
    ellos en o después de start. Solo Finanzas la acepta: Costos sigue con
    mensual y anual (RECURRING_FREQUENCIES en schemas.py)."""
    first, second = sorted(days)
    last_here = _last_day(start.year, start.month)
    # Después del segundo día del mes de start, el primero es el del mes siguiente
    slot = 0 if start.day <= min(first, last_here) else 1 if start.day <= min(second, last_here) else 2
    index = (start.year * 12 + start.month - 1) * 2 + slot + n
    month_index, slot = divmod(index, 2)
    year, month = divmod(month_index, 12)
    return date_type(year, month + 1, min(first if slot == 0 else second, _last_day(year, month + 1)))


def semimonthly_days(series) -> Tuple[int, int]:
    """Los dos días de pago de una quincenal (los de inicio si no trae)."""
    first, second = getattr(series, "first_day", None), getattr(series, "second_day", None)
    return (first, second) if first and second else SEMIMONTHLY_DAYS


def occurrence(start: date_type, frequency: str, n: int, days: Tuple[int, int] = SEMIMONTHLY_DAYS) -> date_type:
    """El cobro número n (0 = el primero): mismo día del mes, o el último si el
    mes es más corto; cada año, el mismo día (el 29 de febrero, el 28 si no hay)."""
    if frequency == "semimonthly":
        return _semimonthly(start, n, days)
    months = n * (12 if frequency == "yearly" else 1)
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date_type(year, month, min(start.day, _last_day(year, month)))


def next_date(series) -> Optional[date_type]:
    """El siguiente cobro por generar, o None si ya terminó."""
    d = occurrence(series.start_date, series.frequency, series.generated, semimonthly_days(series))
    return None if series.end_date is not None and d > series.end_date else d


def skip_past(series, today: date_type) -> None:
    """Al reanudar una pausada: los cobros del tiempo en pausa no se generan."""
    for _ in range(10000):
        due = next_date(series)
        if due is None or due >= today:
            return
        series.generated += 1


def period_start(frequency: str, today: date_type) -> date_type:
    """El inicio del periodo actual de un recurrente: el día 1 del mes (o el 1
    o el 16, si es quincenal), o el 1 de enero."""
    if frequency == "yearly":
        return today.replace(month=1, day=1)
    if frequency == "semimonthly":
        return today.replace(day=1 if today.day <= 15 else 16)
    return today.replace(day=1)


def period_bounds(period: str, day: date_type) -> Tuple[date_type, date_type]:
    """El periodo de Finanzas que contiene `day`: el mes, o la quincena (del 1
    al 15 y del 16 al último día)."""
    last = date_type(day.year, day.month, _last_day(day.year, day.month))
    if period == "biweekly":
        if day.day <= 15:
            return day.replace(day=1), day.replace(day=15)
        return day.replace(day=16), last
    return day.replace(day=1), last


def adjacent_period(period: str, day: date_type, step: int) -> Tuple[date_type, date_type]:
    """El periodo anterior (step = -1) o el siguiente (step = 1) al de `day`."""
    start, end = period_bounds(period, day)
    return period_bounds(period, start - timedelta(days=1) if step < 0 else end + timedelta(days=1))
