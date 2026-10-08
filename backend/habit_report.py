"""
El reporte de hábitos de una semana o un mes (1.23): las cifras que se congelan
al generarlo y su texto con reglas. Se guarda en la tabla `reports`, como el de
tiempo, con kind "habits-week" o "habits-month" (backend/reports.py).

Qué cuenta como posible: un día ya transcurrido del periodo, salvo los que
congelan la racha (descanso, vacaciones y festivos que se descansan) y hoy si
aún no se marca nada. Un día así que sí se hizo cuenta, como en la racha
(_walk_streak). Las rachas se miden al cierre del periodo, no a la fecha de hoy:
un reporte viejo dice cómo estaban entonces.

Tono del texto (docs/referencias.md): faltar un día no deshace un hábito (Lally
et al., 2010) y culparse de un corte hace abandonar (Silverman y Barasch, 2023):
describe, propone retomar, nunca regaña.
"""
from datetime import date as date_type, timedelta
from typing import Dict, List, Optional, Set

from sqlmodel import Session, select

from backend.models import Habit, HabitEntry, HabitNote, User

WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
PERIOD = {"week": "la semana", "month": "el mes"}
PREVIOUS = {"week": "la semana pasada", "month": "el mes pasado"}
# Cambio de cumplimiento de un hábito que vale la pena decir (puntos porcentuales)
CHANGE_NOTICE_PTS = 10
# Por debajo de esto, un hábito "costó" en el periodo
LOW_PCT = 50
MAX_ITEMS = 6
# Notas que se guardan en el reporte (las más recientes, si hay más)
MAX_REPORT_NOTES = 60


def _pct(part: int, whole: int) -> Optional[int]:
    """Entero con .5 hacia arriba (como el dinero), None sin base."""
    return (part * 200 + whole) // (whole * 2) if whole else None


def _walk_day(through: date_type, today: date_type) -> date_type:
    """El "hoy" con el que se recorre la racha al cierre del periodo: en uno ya
    terminado, el día siguiente al último, así el último día se juzga entero."""
    return today if through >= today else through + timedelta(days=1)


def habit_metrics(session: Session, user: User, start: date_type, end: date_type,
                  today: date_type, with_previous: bool = True) -> dict:
    """Las cifras del reporte de hábitos del periodo [start, end]."""
    # Importado aquí: el router de hábitos tiene la regla de la racha y importa más cosas
    from backend.routers.habits import _holiday_days, _is_done_day, _paused_days, _walk_streak

    through = min(end, today)
    rest_days = set(user.rest_days or [])
    paused = _paused_days(session, user.id)
    holidays = _holiday_days(session, user.id, today)
    frozen = paused | set(holidays)
    walk_today = _walk_day(through, today)

    entries = session.exec(select(HabitEntry).where(
        HabitEntry.user_id == user.id, HabitEntry.entry_date <= through)).all()
    by_date = {e.entry_date: (e.habits_data or {}) for e in entries}
    done_dates = {d for d, data in by_date.items() if _is_done_day(data)}
    overall = _walk_streak(done_dates, rest_days, walk_today, frozen)
    protected = set(overall.protected)

    # Los activos, más los ocultos con algún registro en el periodo (como el calendario)
    with_records = {key for d, data in by_date.items() if start <= d <= through
                    for key, value in data.items() if value}
    habits = [h for h in session.exec(select(Habit).where(Habit.user_id == user.id)
                                      .order_by(Habit.order, Habit.id)).all()
              if h.is_active or h.key in with_records]

    def off_reason(d: date_type) -> Optional[str]:
        if d.weekday() in rest_days:
            return "descanso"
        if d in paused:
            return "vacaciones"
        if d in holidays:
            return holidays[d] or "festivo"
        return None

    days: List[dict] = []
    d = start
    while d <= end:
        data = by_date.get(d, {}) if d <= through else {}
        keys = [h.key for h in habits if data.get(h.key)]
        reason = None
        if d > through:
            status = "pending"
        elif _is_done_day(data):
            status = "done"
        elif d == today:
            status = "today"
        elif off_reason(d):
            status, reason = "off", off_reason(d)
        elif d in protected:
            status = "protected"
        else:
            status = "missed"
        days.append({"date": d.isoformat(), "status": status, "reason": reason, "done": keys})
        d += timedelta(days=1)

    def possible(day: dict, key: Optional[str] = None) -> bool:
        """¿Ese día contaba (para un hábito, o para cualquiera)?"""
        if day["status"] == "pending":
            return False
        done = (key in day["done"]) if key else day["status"] == "done"
        if done:
            return True
        return day["status"] not in ("off", "today")

    first_record: Dict[str, date_type] = {}
    for day_date, data in sorted(by_date.items()):
        for key, value in data.items():
            if value:
                first_record.setdefault(key, day_date)

    items = []
    counted_dates: Set[str] = set()   # días que contaban para algún hábito
    weekday_done = [0] * 7
    weekday_possible = [0] * 7
    total_done = total_possible = 0
    for habit in habits:
        # Un hábito nuevo cuenta desde que existe (o desde su primer registro, si es anterior)
        since = min(habit.created_at, first_record.get(habit.key, habit.created_at))
        done = possible_n = 0
        missed: List[str] = []
        by_wd_done, by_wd_possible = [0] * 7, [0] * 7
        for day in days:
            day_date = date_type.fromisoformat(day["date"])
            if day_date < since or not possible(day, habit.key):
                continue
            possible_n += 1
            counted_dates.add(day["date"])
            by_wd_possible[day_date.weekday()] += 1
            if habit.key in day["done"]:
                done += 1
                by_wd_done[day_date.weekday()] += 1
            else:
                missed.append(day["date"])
        habit_dates = {dd for dd, data in by_date.items() if data.get(habit.key)}
        walk = _walk_streak(habit_dates, rest_days, walk_today, frozen)
        rates = [(_pct(by_wd_done[i], by_wd_possible[i]), i) for i in range(7) if by_wd_possible[i]]
        items.append({
            "key": habit.key, "label": habit.label, "icon": habit.icon, "color": habit.color,
            "active": habit.is_active, "days_done": done, "days_possible": possible_n,
            "pct": _pct(done, possible_n), "missed_days": missed,
            "current_streak": walk.current, "best_streak": walk.best,
            "best_weekday": max(rates)[1] if rates else None,
            "weak_weekday": min(rates)[1] if len(rates) > 1 and min(rates)[0] < max(rates)[0] else None,
        })
        total_done += done
        total_possible += possible_n
        for i in range(7):
            weekday_done[i] += by_wd_done[i]
            weekday_possible[i] += by_wd_possible[i]

    # Antes de que existiera algún hábito no había nada que hacer: ni cuenta ni falla
    for day in days:
        if day["status"] in ("missed", "protected") and day["date"] not in counted_dates:
            day["status"] = "none"
    # Las notas del periodo (1.25): texto del usuario, para el reporte y la IA
    labels = {h.key: h.label for h in habits}
    notes = session.exec(select(HabitNote).where(
        HabitNote.user_id == user.id, HabitNote.entry_date >= start, HabitNote.entry_date <= through,
    ).order_by(HabitNote.entry_date.desc(), HabitNote.habit_key)).all()[:MAX_REPORT_NOTES]
    notes_out = [{"date": n.entry_date.isoformat(), "habit": labels.get(n.habit_key, n.habit_key),
                  "text": n.text} for n in reversed(notes)]

    counted = [day for day in days if day["date"] in counted_dates]
    off = [day for day in days if day["status"] == "off"]
    metrics = {
        "date_from": start.isoformat(), "date_to": end.isoformat(), "through": through.isoformat(),
        "today": today.isoformat(),
        "habit_count": len(habits),
        "days": days,
        "habits": items,
        # Hábito-días hechos de los posibles: el cumplimiento del periodo
        "done_total": total_done, "possible_total": total_possible,
        "completion_pct": _pct(total_done, total_possible),
        # Días con al menos un hábito, de los que contaban
        "active_days": sum(1 for day in days if day["status"] == "done"),
        "counted_days": len(counted),
        "missed_days": [day["date"] for day in days if day["status"] == "missed"],
        "protected_days": [day["date"] for day in days if day["status"] == "protected"],
        "off_days": [{"date": day["date"], "reason": day["reason"]} for day in off],
        "streak": overall.current, "best_streak": overall.best, "shields": overall.shields,
        "by_weekday": [{"weekday": i, "name": WEEKDAYS[i], "done": weekday_done[i], "possible": weekday_possible[i],
                        "pct": _pct(weekday_done[i], weekday_possible[i])} for i in range(7)],
        "notes": notes_out,
        "previous": None,
    }
    if with_previous:
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6) if (end - start).days == 6 else prev_end.replace(day=1)
        prev = habit_metrics(session, user, prev_start, prev_end, today, with_previous=False)
        metrics["previous"] = {
            "date_from": prev["date_from"], "date_to": prev["date_to"],
            "completion_pct": prev["completion_pct"], "done_total": prev["done_total"],
            "possible_total": prev["possible_total"], "active_days": prev["active_days"],
            "counted_days": prev["counted_days"], "streak": prev["streak"],
            "missed_count": len(prev["missed_days"]), "protected_count": len(prev["protected_days"]),
            "off_count": len(prev["off_days"]),
            "habits": [{"key": h["key"], "label": h["label"], "pct": h["pct"], "days_done": h["days_done"],
                        "days_possible": h["days_possible"]} for h in prev["habits"]],
            "by_day": [{"date": day["date"], "count": len(day["done"]), "status": day["status"]}
                       for day in prev["days"]],
        }
    return metrics


def weeks_of_month(m: dict) -> List[dict]:
    """Las semanas (lunes a domingo) del mes, recortadas al mes: cumplimiento de cada una."""
    weeks: List[dict] = []
    keys = [h["key"] for h in m["habits"]]
    for day in m["days"]:
        d = date_type.fromisoformat(day["date"])
        if not weeks or d.weekday() == 0:
            weeks.append({"start": day["date"], "end": day["date"], "done": 0, "possible": 0, "pending": True})
        week = weeks[-1]
        week["end"] = day["date"]
        if day["status"] == "pending":
            continue
        week["pending"] = False
        for key in keys:
            if key in day["done"]:
                week["done"] += 1
                week["possible"] += 1
            elif day["status"] not in ("off", "today"):
                week["possible"] += 1
    for week in weeks:
        week["pct"] = _pct(week["done"], week["possible"])
    return weeks


def has_habit_activity(session: Session, user_id: int, start: date_type, end: date_type) -> bool:
    """¿Marcó algún hábito en el periodo? Sin nada, no hay reporte automático."""
    entries = session.exec(select(HabitEntry).where(
        HabitEntry.user_id == user_id, HabitEntry.entry_date >= start, HabitEntry.entry_date <= end)).all()
    return any(value for e in entries for value in (e.habits_data or {}).values())


# ============================================
# El texto, con reglas
# ============================================

def _name(h: dict) -> str:
    return f"{h['icon']} {h['label']}" if h.get("icon") else h["label"]


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def _day(iso: str) -> str:
    d = date_type.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d.day}"


def _days_word(n: int) -> str:
    return f"{n} {'día' if n == 1 else 'días'}"


def _summary(period: str, m: dict) -> str:
    parts = [f"Cumpliste el {m['completion_pct']} % de tus hábitos en {PERIOD[period]}: "
             f"{m['done_total']} de {m['possible_total']} marcas posibles, "
             f"con algo hecho {_days_word(m['active_days'])} de {m['counted_days']} que contaban."]
    prev = m.get("previous") or {}
    if prev.get("completion_pct") is not None:
        diff = m["completion_pct"] - prev["completion_pct"]
        if abs(diff) < 5:
            parts.append(f"Parecido a {PREVIOUS[period]} ({prev['completion_pct']} %).")
        else:
            parts.append(f"{'Más' if diff > 0 else 'Menos'} que {PREVIOUS[period]}, que fue {prev['completion_pct']} %.")
    if m["streak"]:
        parts.append(f"Tu racha al cierre: {_days_word(m['streak'])} (la mejor: {m['best_streak']}).")
    if m["through"] < m["date_to"]:
        parts.append(f"El periodo sigue en curso: cuenta hasta el {_day(m['through'])}.")
    return " ".join(parts)


def _days_note(m: dict) -> str:
    """Qué días no contaron, y por qué: congelan la racha, no son fallos."""
    off = m["off_days"]
    notes = []
    rest = sum(1 for d in off if d["reason"] == "descanso")
    vacation = sum(1 for d in off if d["reason"] == "vacaciones")
    holidays = [d for d in off if d["reason"] not in ("descanso", "vacaciones")]
    if rest:
        notes.append(f"{_days_word(rest)} de descanso")
    if vacation:
        notes.append(f"{_days_word(vacation)} de vacaciones")
    if holidays:
        named = [_day(d["date"]) + " (" + d["reason"] + ")" for d in holidays]
        notes.append(f"{'el festivo' if len(holidays) == 1 else 'los festivos'} {_join(named)}")
    if m["protected_days"]:
        notes.append(f"{_days_word(len(m['protected_days']))} cubierto{'s' if len(m['protected_days']) > 1 else ''} "
                     f"por un protector ({_join([_day(d) for d in m['protected_days']])})")
    if not notes:
        return ""
    return f"No contaron como fallo: {_join(notes)}."


def _patterns(period: str, m: dict) -> List[str]:
    out = []
    ranked = sorted((h for h in m["habits"] if h["pct"] is not None), key=lambda h: -h["pct"])
    if ranked:
        top = ranked[0]
        out.append(f"Tu hábito más constante fue {_name(top)}: {top['days_done']} de {top['days_possible']} días "
                   f"({top['pct']} %).")
    if len(ranked) > 1 and ranked[-1]["pct"] < LOW_PCT:
        low = ranked[-1]
        out.append(f"{_name(low)} es el que más costó: {low['days_done']} de {low['days_possible']} días "
                   f"({low['pct']} %).")
    if period == "month":
        rated = [w for w in m["by_weekday"] if w["possible"] and w["pct"] is not None]
        if len(rated) > 1:
            best = max(rated, key=lambda w: w["pct"])
            worst = min(rated, key=lambda w: w["pct"])
            if best["pct"] > worst["pct"]:
                out.append(f"Los {best['name']} son tu mejor día ({best['pct']} %) y los "
                           f"{worst['name']} el más difícil ({worst['pct']} %).")
    streaks = [h for h in m["habits"] if h["current_streak"] >= 3]
    for h in sorted(streaks, key=lambda h: -h["current_streak"])[:2]:
        out.append(f"{_name(h)} lleva {_days_word(h['current_streak'])} seguidos.")
    if m["missed_days"]:
        out.append(f"Días sin ningún hábito: {_join([_day(d) for d in m['missed_days'][:5]])}"
                   f"{' y otros' if len(m['missed_days']) > 5 else ''}.")
    notes = m.get("notes") or []
    if notes:
        by_habit: Dict[str, int] = {}
        for n in notes:
            by_habit[n["habit"]] = by_habit.get(n["habit"], 0) + 1
        parts = [f"{name} ({count})" for name, count in sorted(by_habit.items(), key=lambda kv: -kv[1])]
        out.append(f"Anotaste {len(notes)} {'nota' if len(notes) == 1 else 'notas'} del día: {_join(parts)}.")
    return out[:MAX_ITEMS]


def _observations(period: str, m: dict) -> List[str]:
    prev = {h["key"]: h for h in ((m.get("previous") or {}).get("habits") or [])}
    out = []
    for h in m["habits"]:
        before = prev.get(h["key"])
        if not before or before["pct"] is None or h["pct"] is None:
            continue
        diff = h["pct"] - before["pct"]
        if abs(diff) >= CHANGE_NOTICE_PTS:
            out.append(f"{_name(h)} {'subió' if diff > 0 else 'bajó'} de {before['pct']} % a {h['pct']} %.")
    new = [h for h in m["habits"] if h["key"] not in prev and h["days_possible"]]
    if new and prev:
        out.append(f"Nuevo en {PERIOD[period]}: {_join([_name(h) for h in new])}.")
    if not out and prev:
        out.append(f"Tus hábitos se mantuvieron parecidos a {PREVIOUS[period]}.")
    return out[:MAX_ITEMS]


def _comparison(period: str, m: dict) -> str:
    prev = m.get("previous") or {}
    if period != "month" or prev.get("completion_pct") is None:
        return ""
    return (f"Contra el mes anterior: {m['completion_pct']} % de cumplimiento frente a {prev['completion_pct']} %, "
            f"y {_days_word(m['active_days'])} con algo hecho frente a {prev['active_days']}.")


def _next_steps(period: str, m: dict) -> List[str]:
    out = []
    low = [h for h in m["habits"] if h["pct"] is not None and h["pct"] < LOW_PCT]
    for h in sorted(low, key=lambda h: h["pct"])[:2]:
        if h["best_weekday"] is not None and h["weak_weekday"] is not None:
            out.append(f"{_name(h)}: te sale mejor los {WEEKDAYS[h['best_weekday']]}; prueba hacerlo a la misma "
                       f"hora y en el mismo lugar los {WEEKDAYS[h['weak_weekday']]}.")
        else:
            out.append(f"{_name(h)}: átalo a algo que ya haces cada día (después del café, al llegar a casa).")
    if m["missed_days"]:
        out.append("Si un día se te pasa, retómalo al siguiente: faltar uno no deshace el hábito.")
    if not out:
        out.append("Mantén lo que te está funcionando; no hace falta agregar más hábitos para avanzar.")
    return out[:4]


def _closing(period: str, m: dict) -> dict:
    ranked = sorted((h for h in m["habits"] if h["pct"] is not None), key=lambda h: (-h["pct"], -h["days_done"]))
    if m["streak"] >= 7:
        well = f"sostuviste una racha de {_days_word(m['streak'])}."
    elif ranked and ranked[0]["pct"]:
        well = f"{_name(ranked[0])} estuvo presente {ranked[0]['days_done']} de {ranked[0]['days_possible']} días."
    else:
        well = "registraste tus hábitos y ya tienes con qué comparar."
    tip = ("los días de descanso y las vacaciones no rompen la racha: úsalos en lugar de forzarte."
           if not m["off_days"] else
           "anotar el mismo día ayuda a ver el avance; si olvidas uno, puedes marcarlo después.")
    return {"well_done": well[:1].upper() + well[1:], "tip": tip[:1].upper() + tip[1:]}


def build_habit_text(period: str, m: dict) -> dict:
    """La misma forma que el texto del reporte de tiempo (report_text.build_text)."""
    if not m["habit_count"] or not m["possible_total"]:
        return {
            "summary": f"No hubo hábitos que marcar en {PERIOD[period]}.",
            "data_cleanup": _days_note(m), "patterns": [], "legibility": [], "observations": [],
            "comparison": "", "next_steps": [],
            "closing": {"well_done": "", "tip": "Cuando marques tus hábitos, este reporte mostrará cómo vas."},
        }
    return {
        "summary": _summary(period, m),
        "data_cleanup": _days_note(m),
        "patterns": _patterns(period, m),
        "legibility": [],
        "observations": _observations(period, m),
        "comparison": _comparison(period, m),
        "next_steps": _next_steps(period, m),
        "closing": _closing(period, m),
    }
