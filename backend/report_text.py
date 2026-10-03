"""
El texto de un reporte guardado, escrito con reglas fijas (épica 30, Fase 4):
un resumen, observaciones, recomendaciones y un cierre. Solo lee las cifras de
backend/metrics.py que el reporte ya guarda; no consulta la base. En la Fase 5
la IA podrá escribirlo, con la misma forma, y si falla se usa este.

Tono: describe, no regaña ni celebra de más. Las recomendaciones solo salen
cuando una cifra lo justifica; si no hay nada que decir, la lista va vacía.
"""
from datetime import date as date_type
from typing import List, Optional

WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
PERIOD_NAME = {"week": "la semana", "month": "el mes"}
PREVIOUS_NAME = {"week": "la semana anterior", "month": "el mes anterior"}

# Umbrales de las observaciones y recomendaciones
SIMILAR_PCT = 10           # cambio de horas que se considera "parecido"
MANUAL_NOTICE_PCT = 50     # tiempo registrado a mano
CUT_NOTICE_RATIO = 0.5     # pomodoros cortados
UNTAGGED_NOTICE_PCT = 50   # tiempo sin etiqueta
MAX_LISTED_DAYS = 5        # fechas que se enumeran antes de resumir


def hours(seconds: Optional[int]) -> str:
    """3 h 05 min · 45 min · 0 min"""
    seconds = int(seconds or 0)
    h, m = divmod(round(seconds / 60), 60)
    if h and m:
        return f"{h} h {m:02d} min"
    if h:
        return f"{h} h"
    return f"{m} min"


def short_date(iso: str) -> str:
    d = date_type.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def clock(hour: float) -> str:
    """9.5 -> 09:30; 24.5 (pasada la medianoche) -> 00:30"""
    total = round(hour * 60)
    h, m = divmod(total, 60)
    return f"{h % 24:02d}:{m:02d}"


def _list_days(isos: List[str]) -> str:
    shown = ", ".join(short_date(d) for d in isos[:MAX_LISTED_DAYS])
    rest = len(isos) - MAX_LISTED_DAYS
    return f"{shown} y {rest} más" if rest > 0 else shown


def _change_pct(now: int, before: int) -> Optional[int]:
    if not before:
        return None
    return round((now - before) * 100 / before)


def build_text(kind: str, m: dict) -> dict:
    prev = m.get("previous") or {}
    total = m["total_seconds"]
    period = PERIOD_NAME[kind]
    before = PREVIOUS_NAME[kind]
    observations: List[str] = []
    recommendations: List[str] = []

    if not total:
        return {
            "summary": f"No hubo tiempo registrado en {period}.",
            "observations": [],
            "recommendations": [],
            "closing": "Cuando registres tiempo, este reporte mostrará en qué se fue.",
        }

    # Resumen
    summary = (f"Registraste {hours(total)} en {m['active_days']} "
               f"{'día' if m['active_days'] == 1 else 'días'}")
    if m["workdays"]:
        summary += f" ({m['active_workdays']} de {m['workdays']} días hábiles)"
    summary += "."
    change = _change_pct(total, prev.get("total_seconds", 0))
    if change is not None:
        if abs(change) < SIMILAR_PCT:
            summary += f" Parecido a {before} ({hours(prev['total_seconds'])})."
        else:
            word = "más" if change > 0 else "menos"
            summary += f" {abs(change)} % {word} que {before} ({hours(prev['total_seconds'])})."
    elif prev:
        summary += f" En {before} no hubo tiempo registrado."

    # Observaciones
    if m["by_project"]:
        top = m["by_project"][0]
        if len(m["by_project"]) == 1:
            observations.append(f"Todo el tiempo fue para {top['name']}.")
        else:
            observations.append(f"{top['name']} se llevó el {top['pct']} % del tiempo ({hours(top['seconds'])}).")
    if m["avg_seconds_per_active_day"]:
        observations.append(f"En los días con registro, el promedio fue de {hours(m['avg_seconds_per_active_day'])} "
                            f"y la mediana de {hours(m['median_seconds_per_active_day'])}.")
    if m.get("schedule"):
        observations.append(f"Tu horario habitual en días hábiles fue de {clock(m['schedule']['usual_start'])} "
                            f"a {clock(m['schedule']['usual_end'])}.")
    missing = m["missing_workdays"]
    if missing:
        n = len(missing)
        observations.append(f"{'Hubo un día hábil' if n == 1 else f'Hubo {n} días hábiles'} sin registro: "
                            f"{_list_days(missing)}.")
    if m["weekend_seconds"]:
        observations.append(f"Trabajaste {hours(m['weekend_seconds'])} en fin de semana.")
    night = m["night_sessions"]
    if night:
        observations.append(f"{'Una sesión fue' if len(night) == 1 else f'{len(night)} sesiones fueron'} "
                            "de noche (después de las 23 h o de madrugada).")
    if m["manual_pct"] is not None and m["manual_pct"] >= MANUAL_NOTICE_PCT:
        observations.append(f"El {m['manual_pct']} % del tiempo se registró a mano.")
    if m["pomodoros"]:
        observations.append(f"De {m['pomodoros']} pomodoros, {m['pomodoros_cut']} se cortaron antes de terminar.")
    if m["unconfirmed_seconds"]:
        observations.append(f"Incluye {hours(m['unconfirmed_seconds'])} sin confirmar (cronómetros que llegaron al tope de 8 h).")

    # Recomendaciones: solo cuando una cifra lo pide
    review = m["to_review"]
    if review["unconfirmed"] or review["long_sessions"] or review["overlaps"] or review["inconsistent"]:
        recommendations.append("Revisa los registros de «A revisar»: si alguno no es correcto, corrígelo "
                               "y vuelve a generar el reporte.")
    if missing:
        recommendations.append("Si trabajaste los días hábiles sin registro, anótalos a mano; si no eran "
                               "laborables, márcalos como día libre en Configuración › Días y horario.")
    if len(night) >= 2:
        recommendations.append("Varias sesiones fueron de noche. Si no fue a propósito, intenta cerrar antes.")
    if m["pomodoros"] >= 4 and m["pomodoros_cut"] / m["pomodoros"] > CUT_NOTICE_RATIO:
        recommendations.append("Más de la mitad de los pomodoros se cortaron: prueba con un enfoque más corto "
                               "en Configuración › Pomodoro.")
    untagged_pct = round(m["untagged_seconds"] * 100 / total)
    if untagged_pct >= UNTAGGED_NOTICE_PCT and len(m["by_project"]) > 0:
        recommendations.append(f"El {untagged_pct} % del tiempo no tiene etiqueta: etiquetar las tareas hace más "
                               "útil el desglose por tipo de actividad.")

    # Cierre
    if change is None:
        closing = "Sin tiempo en el periodo anterior no hay con qué comparar; el siguiente reporte ya tendrá referencia."
    elif change >= SIMILAR_PCT:
        closing = f"Más horas que {before}. Revisa que el ritmo sea sostenible."
    elif change <= -SIMILAR_PCT:
        closing = f"Menos horas que {before}. Si fue planeado, todo en orden; si no, mira qué se atravesó."
    else:
        closing = f"Un ritmo parecido al de {before}."

    return {
        "summary": summary,
        "observations": observations,
        "recommendations": recommendations,
        "closing": closing,
    }
