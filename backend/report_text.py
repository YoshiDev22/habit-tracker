"""
El texto de un reporte guardado, escrito con reglas fijas (épica 30, Fases 4 y
5). Sigue las secciones de los reportes de ejemplo de Yoshio: resumen con la
limpieza de datos, patrones, legibilidad y etiquetado, observaciones,
comparativa (el mes), próximos pasos o metas, y un cierre con "Bien hecho" y
"Tip". Solo lee las cifras que el reporte ya guarda (backend/reports.py): no
consulta la base. La IA (backend/report_ai.py) escribe la misma forma, y si
falla se usa esta.

Tono: describe, no regaña ni celebra de más. Una sección sin nada que decir va
vacía y la vista la omite. Horas en decimal ("14.3 h"), como los ejemplos.
"""
import re
from datetime import date as date_type, timedelta
from typing import List, Optional

WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
PERIOD = {"week": "la semana", "month": "el mes"}
THIS_PERIOD = {"week": "esta semana", "month": "este mes"}
PREVIOUS = {"week": "la semana pasada", "month": "el mes pasado"}

SIMILAR_RATIO = 0.10        # cambio de ritmo que se considera "parecido"
SHARE_CHANGE_PCT = 5        # cambio de % de un proyecto que vale la pena decir
MANUAL_NOTICE_PCT = 20
UNTAGGED_NOTICE_PCT = 50
CUT_NOTICE_RATIO = 0.5
RECURRING_MIN = 3           # sesiones y días para llamar "constante" a una tarea
MAX_ITEMS = 6
MAX_NEXT = 4
# Una tarea con nombre poco descriptivo: dos palabras o menos y una de estas al
# principio, o una fecha en el nombre ("Tarea 08/09/26")
VAGUE_WORDS = {"ajuste", "ajustes", "cambio", "cambios", "varios", "varias", "pendiente", "pendientes",
               "general", "tarea", "tareas", "cosas", "misc", "arreglos", "fix", "test", "prueba", "pruebas",
               "trabajo", "revisar", "otros"}
DATE_IN_TITLE = re.compile(r"\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?")


def hours(seconds: Optional[int]) -> str:
    """14.3 h · 0.5 h · 0 h"""
    value = round((seconds or 0) / 3600, 1)
    return "0 h" if value == 0 else f"{value:.1f} h"


def clock_hour(value: float) -> str:
    """9.0 -> 9; 9.5 -> 9:30; 24.5 -> 0:30"""
    total = round(value * 60)
    h, m = (total // 60) % 24, total % 60
    return f"{h}" if m == 0 else f"{h}:{m:02d}"


def day_name(iso: str) -> str:
    d = date_type.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day}"


def long_date(iso: str) -> str:
    d = date_type.fromisoformat(iso)
    return f"{d.day} de {MONTHS[d.month - 1]}"


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def is_vague(title: str) -> bool:
    words = title.lower().split()
    if DATE_IN_TITLE.search(title):
        return True
    return 0 < len(words) <= 2 and words[0] in VAGUE_WORDS


# ============================================
# Secciones
# ============================================

def _summary(kind: str, m: dict) -> str:
    total = m["total_seconds"]
    days = m.get("days_detail") or []
    prev = m.get("previous") or {}
    partial = m["through"] < m["date_to"]
    verb = "Llevas" if partial else "Registraste"
    n = m["active_workdays"]
    text = f"{verb} {hours(total)} en {n} {'día hábil' if n == 1 else 'días hábiles'}"

    notes = []
    for d in days:
        if d["status"] == "off" and d["reason"] not in (None, "fin de semana"):
            what = "de vacaciones" if d["reason"] == "Vacaciones" else "festivo"
            notes.append(f"el {day_name(d['date'])} fue {what}")
    if any(d["status"] == "today" for d in days):
        notes.append("hoy sigue en curso")
    pending = [d for d in days if d["status"] == "pending" and d["workday"]]
    if pending:
        notes.append(f"el {WEEKDAYS[date_type.fromisoformat(pending[0]['date']).weekday()]} está pendiente"
                     if len(pending) == 1 else f"faltan {len(pending)} días hábiles")
    if notes:
        text += f" ({_join(notes)})"
    text += "."

    avg = m.get("avg_seconds_per_active_day")
    prev_avg = prev.get("avg_seconds_per_active_day")
    if avg:
        text += f" Son {hours(avg)} por día con registro"
        if prev_avg:
            change = (avg - prev_avg) / prev_avg
            if abs(change) < SIMILAR_RATIO:
                text += f", casi el mismo ritmo que {PREVIOUS[kind]} ({hours(prev_avg)})"
            else:
                text += f", {'más' if change > 0 else 'menos'} que {PREVIOUS[kind]} ({hours(prev_avg)})"
        text += "."
    if m.get("projected_seconds"):
        text += (f" Si mantienes ese ritmo los días que faltan, cerrarías alrededor de "
                 f"{hours(m['projected_seconds'])} (estimado).")
    weeks = [w for w in (m.get("by_week") or []) if not w["pending"]]
    if kind == "month" and len(weeks) >= 2:
        text += (f" Por semana, pasaste de {hours(weeks[0]['seconds'])} en la primera "
                 f"a {hours(weeks[-1]['seconds'])} en la última.")
    return text


def _cleanup(m: dict) -> str:
    review = m["to_review"]
    parts = []
    if review["unconfirmed"]:
        n = len(review["unconfirmed"])
        parts.append(f"{n} {'sesión' if n == 1 else 'sesiones'} sin confirmar ({hours(m['unconfirmed_seconds'])})")
    if review["long_sessions"]:
        n = len(review["long_sessions"])
        parts.append(f"{n} de más de 4 h")
    if review["overlaps"]:
        n = len(review["overlaps"])
        parts.append(f"{n} {'solape' if n == 1 else 'solapes'}")
    if review["inconsistent"]:
        n = len(review["inconsistent"])
        parts.append(f"{n} con duración mayor que su horario")
    if not parts:
        return ("Limpieza de datos: no hay sesiones sin confirmar, de más de 4 h, solapes ni duraciones raras. "
                "No se excluyó nada.")
    text = f"Limpieza de datos: hay {_join(parts)}. Se cuentan todas: no se excluyó nada"
    if m["unconfirmed_seconds"]:
        text += f"; sin lo no confirmado serían {hours(m['total_without_unconfirmed_seconds'])}"
    return text + "."


def _patterns(kind: str, m: dict) -> List[str]:
    out = []
    if m.get("schedule"):
        out.append(f"Horario promedio de trabajo: {clock_hour(m['schedule']['usual_start'])} a "
                   f"{clock_hour(m['schedule']['usual_end'])} h · {hours(m['seconds_after_16h'])} después de las 16 h.")
    for task in m["top_tasks"]:
        if task.get("sessions", 0) >= RECURRING_MIN and task.get("days", 0) >= RECURRING_MIN:
            out.append(f"«{task['title']}»: {task['sessions']} sesiones en {task['days']} días "
                       f"({hours(task['seconds'])}). Hay seguimiento constante.")
            break
    if m["missing_workdays"]:
        out.append(f"Días hábiles sin registro: {_join([day_name(d) for d in m['missing_workdays']])}.")
    night = m["night_sessions"]
    if night:
        latest = max(night, key=lambda s: (s["date"], s["end"]))
        out.append(f"Descanso: {len(night)} {'sesión nocturna' if len(night) == 1 else 'sesiones nocturnas'} "
                   f"(la más tarde, el {day_name(latest['date'])} hasta las {latest['end']}). Cuida tu descanso.")
    else:
        out.append(f"Descanso: {THIS_PERIOD[kind]} no te desvelaste.")
    if m["manual_pct"] is not None and m["manual_pct"] >= MANUAL_NOTICE_PCT:
        out.append(f"Registrado a mano: {m['manual_pct']} % del tiempo.")
    if m["pomodoros"]:
        out.append(f"Pomodoros: {m['pomodoros']}, de los cuales {m['pomodoros_cut']} quedaron cortados.")
    if m["weekend_seconds"]:
        out.append(f"Fin de semana: {hours(m['weekend_seconds'])}.")
    return out[:MAX_ITEMS]


def _vague_tasks(m: dict) -> List[dict]:
    return [t for t in m["top_tasks"] if is_vague(t["title"])]


def _legibility(m: dict) -> List[str]:
    out = []
    vague = _vague_tasks(m)
    if vague:
        names = _join([f"«{t['title']}» ({hours(t['seconds'])})" for t in vague[:3]])
        out.append(f"Tareas poco descriptivas: {names}. Un nombre que diga qué hiciste ayuda a leer tus horas después.")
    total = m["total_seconds"]
    untagged_pct = round(m["untagged_seconds"] * 100 / total) if total else 0
    if untagged_pct >= UNTAGGED_NOTICE_PCT:
        out.append(f"Etiquetas: el {untagged_pct} % del tiempo no tiene etiqueta.")
    return out


def _observations(kind: str, m: dict) -> List[str]:
    out = []
    prev = m.get("previous") or {}
    prev_share = {p["name"]: p["pct"] for p in prev.get("by_project", [])}
    projects = m["by_project"]
    if prev.get("total_seconds") and projects:
        for p in projects[:4]:
            before = prev_share.get(p["name"])
            if before is None:
                out.append(f"{p['name']} es nuevo: {p['pct']} % del tiempo ({hours(p['seconds'])}).")
            elif p["pct"] - before >= SHARE_CHANGE_PCT:
                out.append(f"{p['name']} subió de {before} % a {p['pct']} % del tiempo.")
            elif before - p["pct"] >= SHARE_CHANGE_PCT:
                out.append(f"{p['name']} bajó de {before} % a {p['pct']} % del tiempo.")
            elif p is projects[0]:
                out.append(f"{p['name']} se mantiene en {p['pct']} % del tiempo.")
        current = {p["name"] for p in projects}
        for p in prev.get("by_project", [])[:3]:
            if p["name"] not in current:
                out.append(f"{p['name']} no tuvo tiempo {THIS_PERIOD[kind]} ({PREVIOUS[kind]}: {p['pct']} %).")
    elif projects:
        top = projects[0]
        out.append(f"{top['name']} se llevó el {top['pct']} % del tiempo ({hours(top['seconds'])}).")
        if len(projects) > 1:
            out.append(f"Le siguió {projects[1]['name']}, con {projects[1]['pct']} % ({hours(projects[1]['seconds'])}).")
    if m["top_tasks"]:
        task = m["top_tasks"][0]
        out.append(f"La tarea con más horas fue «{task['title']}» ({hours(task['seconds'])}).")
    return out[:MAX_ITEMS]


def _comparison(kind: str, m: dict) -> str:
    if kind != "month":
        return ""
    prev = m.get("previous") or {}
    name = MONTHS[date_type.fromisoformat(m["date_from"]).month - 1]
    if not prev.get("total_seconds"):
        return (f"No hay tiempo registrado el mes anterior, así que no hay con qué comparar. "
                f"{_cap(name)} queda como línea base.")
    before = prev["total_seconds"]
    diff = m["total_seconds"] - before
    pct = round(abs(diff) * 100 / before)
    word = "más" if diff >= 0 else "menos"
    return f"Frente al mes anterior ({hours(before)}): {hours(abs(diff))} {word} ({pct} %)."


def _next_steps(kind: str, m: dict) -> List[str]:
    out = []
    review = m["to_review"]
    if review["unconfirmed"]:
        out.append("Confirma o corrige los registros sin confirmar (en la campanita de arriba) y regenera el reporte.")
    elif review["long_sessions"] or review["overlaps"] or review["inconsistent"]:
        out.append("Revisa los registros marcados para revisar al final de este reporte.")
    if m["missing_workdays"]:
        out.append("Si trabajaste los días sin registro, anótalos a mano; si no eran laborables, márcalos como "
                   "día libre en Configuración › Días y horario.")
    vague = _vague_tasks(m)
    if vague:
        out.append(f"Cambia «{vague[0]['title']}» por lo que hiciste en concreto.")
    if len(m["night_sessions"]) >= 2:
        out.append("Intenta cerrar antes de las 23 h.")
    if m["pomodoros"] >= 4 and m["pomodoros_cut"] / m["pomodoros"] > CUT_NOTICE_RATIO:
        out.append("Más de la mitad de tus pomodoros se cortaron: prueba un enfoque más corto en "
                   "Configuración › Pomodoro.")
    total = m["total_seconds"]
    if total and m["untagged_seconds"] * 100 / total >= UNTAGGED_NOTICE_PCT:
        out.append("Etiqueta tus tareas: el desglose por actividad será más útil.")
    return out[:MAX_NEXT]


def _closing(kind: str, m: dict) -> dict:
    prev = m.get("previous") or {}
    total = m["total_seconds"]
    elapsed_workdays = m["workdays"]
    if elapsed_workdays and m["active_workdays"] >= elapsed_workdays:
        well = "registraste todos los días hábiles."
    elif prev.get("total_seconds") and total >= prev["total_seconds"] * (1 + SIMILAR_RATIO):
        well = f"subiste de {hours(prev['total_seconds'])} a {hours(total)}."
    elif not m["night_sessions"]:
        well = f"{THIS_PERIOD[kind]} no te desvelaste."
    else:
        well = f"registraste {hours(total)} en {m['active_days']} días."

    vague = _vague_tasks(m)
    if vague:
        tip = (f"cambia «{vague[0]['title']}» por lo que hiciste en concreto; en un mes no sabrás qué fueron "
               f"esas {hours(vague[0]['seconds'])}.")
    elif m["unconfirmed_seconds"]:
        tip = "pausa el cronómetro cada vez que te levantes: una sesión olvidada infla el total."
    elif m["missing_workdays"]:
        tip = "registra el tiempo el mismo día, aunque sea a mano: es más fácil que reconstruirlo después."
    else:
        tip = f"revisa tu reporte cada {'lunes' if kind == 'week' else 'día 1'}: ver la tendencia ayuda a sostener el ritmo."
    return {"well_done": _cap(well), "tip": _cap(tip)}


def build_text(kind: str, m: dict) -> dict:
    if not m["total_seconds"]:
        return {
            "summary": f"No registraste tiempo en {PERIOD[kind]}.",
            "data_cleanup": "",
            "patterns": [],
            "legibility": [],
            "observations": [],
            "comparison": "",
            "next_steps": [],
            "closing": {"well_done": "", "tip": "Cuando registres tiempo, este reporte mostrará en qué se fue."},
        }
    return {
        "summary": _summary(kind, m),
        "data_cleanup": _cleanup(m),
        "patterns": _patterns(kind, m),
        "legibility": _legibility(m),
        "observations": _observations(kind, m),
        "comparison": _comparison(kind, m),
        "next_steps": _next_steps(kind, m),
        "closing": _closing(kind, m),
    }
