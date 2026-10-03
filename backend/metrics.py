"""
Capa de métricas (épica 30, Fase 3): las cifras de los reportes, calculadas una
sola vez en el backend. Las usarán la vista de reportes, la IA (que recibe este
JSON, nunca los registros crudos) y el export.

Mismo criterio que Reportes, la Lista y las tarjetas: solo sesiones `focus`, por
`session_date` (la fecha LOCAL que mandó el cliente). Las horas del día
(nocturnas, horario habitual) se calculan con el huso del usuario
(backend/days.py) sobre `started_at`/`ended_at`, que están en UTC.

Nada se excluye: el tiempo por confirmar (needs_review), las sesiones largas,
los solapes y las duraciones raras se cuentan y se listan en `to_review`, para
que el usuario decida.
"""
import statistics
from collections import Counter, defaultdict
from datetime import date as date_type, datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from sqlmodel import Session, select

from backend.days import work_calendar
from backend.models import PomodoroSession, Project, Tag, Task, TaskTag, User

NIGHT_FROM = time(23, 0)          # "sesiones nocturnas: después de las 23 h"
NIGHT_UNTIL = time(5, 0)          # ...y de madrugada
AFTERNOON_FROM = time(16, 0)      # "0.9 h después de las 16 h"
LONG_SESSION_SECONDS = 4 * 3600   # el brief las listaba aparte
POMODORO_CUT_MARGIN = 60          # un pomodoro de 25 min con menos de 24 está cortado
TOP_TASKS = 10


def _local(moment: datetime, zone) -> datetime:
    return moment.replace(tzinfo=timezone.utc).astimezone(zone)


def _clock(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def _hours_since(day: date_type, moment: datetime) -> float:
    """Horas desde la medianoche local de `day`: una sesión del lunes que acaba
    a las 00:30 del martes termina a las 24.5 h del lunes, no a las 0.5 h."""
    midnight = datetime.combine(day, time(0), tzinfo=moment.tzinfo)
    return (moment - midnight).total_seconds() / 3600


def _overlap_seconds(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> int:
    return max(0, int((min(end, window_end) - max(start, window_start)).total_seconds()))


def _is_night(start: datetime, end: datetime) -> bool:
    if end.date() > start.date():
        return True
    return any(t.time() >= NIGHT_FROM or t.time() < NIGHT_UNTIL for t in (start, end))


def compute_metrics(session: Session, user: User, date_from: date_type, date_to: date_type,
                    today: date_type) -> dict:
    calendar = work_calendar(session, user.id, date_from, date_to)
    zone = calendar.zone
    last_day = min(date_to, today)

    sessions = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.user_id == user.id,
            PomodoroSession.mode == "focus",
            PomodoroSession.session_date >= date_from,
            PomodoroSession.session_date <= date_to,
        ).order_by(PomodoroSession.started_at)
    ).all()

    task_ids = {s.task_id for s in sessions if s.task_id is not None}
    tasks = {t.id: t for t in session.exec(select(Task).where(Task.user_id == user.id)).all()} if task_ids else {}
    projects = {p.id: p for p in session.exec(select(Project).where(Project.user_id == user.id)).all()}
    tags_by_task: Dict[int, List[Tag]] = defaultdict(list)
    if task_ids:
        for task_id, tag in session.exec(
            select(TaskTag.task_id, Tag).join(Tag, Tag.id == TaskTag.tag_id)
            .where(TaskTag.user_id == user.id, TaskTag.task_id.in_(list(task_ids)))
        ).all():
            tags_by_task[task_id].append(tag)

    rows = []
    for s in sessions:
        start, end = _local(s.started_at, zone), _local(s.ended_at, zone)
        rows.append((s, start, end))

    total = sum(s.duration_seconds for s in sessions)
    by_day = Counter()
    for s in sessions:
        by_day[s.session_date] += s.duration_seconds

    # Días del periodo (hasta hoy) y cuáles eran hábiles
    days = [date_from + timedelta(days=i) for i in range((last_day - date_from).days + 1)] if last_day >= date_from else []
    workdays = [d for d in days if calendar.is_workday(d)]
    active_days = sorted(d for d in by_day if by_day[d] > 0)
    active_values = [by_day[d] for d in active_days]

    # Origen y pomodoros
    by_source = Counter()
    for s in sessions:
        by_source[s.source] += s.duration_seconds
    pomodoros = [s for s in sessions if s.source == "timer" and s.planned_seconds > 0]
    cut = [s for s in pomodoros if not s.was_completed or s.duration_seconds < s.planned_seconds - POMODORO_CUT_MARGIN]

    # Horario: primera hora de inicio y última de fin de cada día hábil con tiempo
    first_start: Dict[date_type, datetime] = {}
    last_end: Dict[date_type, datetime] = {}
    after_afternoon = 0
    night = []
    for s, start, end in rows:
        if s.session_date not in first_start or start < first_start[s.session_date]:
            first_start[s.session_date] = start
        if s.session_date not in last_end or end > last_end[s.session_date]:
            last_end[s.session_date] = end
        afternoon = datetime.combine(start.date(), AFTERNOON_FROM, tzinfo=start.tzinfo)
        midnight = datetime.combine(start.date() + timedelta(days=1), time(0), tzinfo=start.tzinfo)
        after_afternoon += _overlap_seconds(start, end, afternoon, midnight)
        if _is_night(start, end):
            night.append({"date": s.session_date.isoformat(), "start": _clock(start), "end": _clock(end),
                          "seconds": s.duration_seconds})
    work_with_time = [d for d in active_days if calendar.is_workday(d)]
    schedule = None
    if work_with_time:
        schedule = {
            "usual_start": round(statistics.median(_hours_since(d, first_start[d]) for d in work_with_time), 1),
            "usual_end": round(statistics.median(_hours_since(d, last_end[d]) for d in work_with_time), 1),
        }

    # En qué se fue el tiempo
    by_project = Counter()
    by_task = Counter()
    by_tag = Counter()
    untagged = 0
    for s in sessions:
        by_project[s.project_id] += s.duration_seconds
        if s.task_id is not None:
            by_task[s.task_id] += s.duration_seconds
        task_tags = tags_by_task.get(s.task_id, []) if s.task_id is not None else []
        if not task_tags:
            untagged += s.duration_seconds
        for tag in task_tags:
            by_tag[tag.id] += s.duration_seconds
    tag_info = {tag.id: tag for tags in tags_by_task.values() for tag in tags}

    def pct(seconds: int) -> Optional[int]:
        return round(seconds * 100 / total) if total else None

    projects_out = []
    for project_id, seconds in by_project.most_common():
        project = projects.get(project_id)
        projects_out.append({
            "project_id": project_id,
            "name": project.name if project else "Sin proyecto",
            "color": project.color if project else None,
            "seconds": seconds,
            "pct": pct(seconds),
        })
    tasks_out = []
    for task_id, seconds in by_task.most_common(TOP_TASKS):
        task = tasks.get(task_id)
        project = projects.get(task.project_id) if task else None
        tasks_out.append({
            "task_id": task_id,
            "title": task.title if task else "Tarea borrada",
            "project": project.name if project else None,
            "color": project.color if project else None,
            "seconds": seconds,
        })
    tags_out = [
        {"tag_id": tag_id, "name": tag_info[tag_id].name, "color": tag_info[tag_id].color, "seconds": seconds}
        for tag_id, seconds in by_tag.most_common()
    ]

    # Para revisar: nada se excluye, se lista
    def describe(s: PomodoroSession, start: datetime, end: datetime) -> dict:
        task = tasks.get(s.task_id) if s.task_id is not None else None
        return {"session_id": s.id, "date": s.session_date.isoformat(), "start": _clock(start), "end": _clock(end),
                "seconds": s.duration_seconds, "task": task.title if task else None}

    unconfirmed = [describe(s, a, b) for s, a, b in rows if s.needs_review]
    long_sessions = [describe(s, a, b) for s, a, b in rows if s.duration_seconds > LONG_SESSION_SECONDS]
    inconsistent = [describe(s, a, b) for s, a, b in rows
                    if s.duration_seconds > (s.ended_at - s.started_at).total_seconds() + 60]
    overlaps = []
    for (s1, a1, b1), (s2, a2, b2) in zip(rows, rows[1:]):
        if (b1 - a2).total_seconds() > 60:
            overlaps.append({"first": describe(s1, a1, b1), "second": describe(s2, a2, b2)})

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "through": last_day.isoformat(),
        "timezone": calendar.timezone,
        "country": calendar.country,
        "total_seconds": total,
        "unconfirmed_seconds": sum(item["seconds"] for item in unconfirmed),
        "session_count": len(sessions),
        "avg_session_seconds": round(total / len(sessions)) if sessions else None,
        "days": len(days),
        "workdays": len(workdays),
        "active_days": len(active_days),
        "active_workdays": len(work_with_time),
        "missing_workdays": [d.isoformat() for d in workdays if by_day[d] == 0 and d != today],
        "non_working_days": [{"date": d.isoformat(), "reason": why}
                             for d, why in sorted(calendar.off_days.items()) if date_from <= d <= last_day],
        "avg_seconds_per_active_day": round(statistics.mean(active_values)) if active_values else None,
        "median_seconds_per_active_day": round(statistics.median(active_values)) if active_values else None,
        "by_day": [{"date": d.isoformat(), "seconds": by_day[d], "workday": calendar.is_workday(d)} for d in days],
        "by_source": dict(by_source),
        "manual_pct": pct(by_source.get("manual", 0)),
        "pomodoros": len(pomodoros),
        "pomodoros_cut": len(cut),
        "night_sessions": night,
        "weekend_seconds": sum(seconds for d, seconds in by_day.items() if d.weekday() >= 5),
        "schedule": schedule,
        "seconds_after_16h": after_afternoon,
        "by_project": projects_out,
        "top_tasks": tasks_out,
        "by_tag": tags_out,
        "untagged_seconds": untagged,
        "to_review": {
            "unconfirmed": unconfirmed,
            "long_sessions": long_sessions,
            "overlaps": overlaps,
            "inconsistent": inconsistent,
        },
    }
