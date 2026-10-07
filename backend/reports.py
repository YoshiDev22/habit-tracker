"""
Reportes guardados (épica 30, Fase 4): qué periodo cubre cada uno, cómo se
genera y cuáles le tocan a un usuario. Las cifras salen de backend/metrics.py
y el texto de backend/report_text.py. Lo usan el router (el botón "Generar
reporte") y scripts/generate_reports.py (el timer de systemd).

Periodos: la semana va de lunes a domingo, como la pestaña Reportes, y el mes
del día 1 al último. El automático sale cuando el periodo ya terminó en la
fecha LOCAL del usuario: el lunes, el de la semana anterior; el día 1, el del
mes anterior.

Temas (1.23, backend/report_kinds.py): tiempo (las cifras de metrics.py),
hábitos (habit_report.py) y costos (cost_report.py). Cada uno pone sus cifras
y su texto de reglas; guardar, la IA y el timer son lo mismo para los tres.
"""
import calendar as calendar_module
from datetime import date as date_type, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from backend.cost_report import build_costs_text, cost_metrics, has_cost_activity
from backend.days import DEFAULT_TIMEZONE, user_settings, valid_timezone, work_calendar
from backend.habit_report import build_habit_text, habit_metrics, has_habit_activity, weeks_of_month as habit_weeks
from backend.metrics import compute_metrics
from backend.models import PomodoroSession, Report, User, utc_now_naive
from backend.ai import AiError, ai_config
from backend.report_ai import write_with_ai
from backend.report_kinds import KINDS, MODULE, period_of, subject_of
from backend.report_text import build_text

# Si el timer no corrió (servidor apagado), cuántos periodos hacia atrás pone al día
CATCH_UP = {"week": 4, "month": 2}
# Del periodo anterior se guarda lo que el reporte compara (la tabla de
# métricas, las barras por día y la dona por proyecto)
PREVIOUS_FIELDS = ("total_seconds", "days", "workdays", "active_days", "active_workdays",
                   "avg_seconds_per_active_day", "median_seconds_per_active_day", "session_count",
                   "avg_session_seconds", "manual_pct", "pomodoros", "pomodoros_cut", "weekend_seconds",
                   "unconfirmed_seconds", "missing_workdays", "non_working_days")


def period_bounds(kind: str, day: date_type) -> Tuple[date_type, date_type]:
    """El periodo de ese tipo que contiene `day`: (inicio, fin), los dos incluidos."""
    if period_of(kind) == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    start = day.replace(day=1)
    return start, day.replace(day=calendar_module.monthrange(day.year, day.month)[1])


def is_period_start(kind: str, day: date_type) -> bool:
    return period_bounds(kind, day)[0] == day


def previous_period(kind: str, start: date_type) -> Tuple[date_type, date_type]:
    return period_bounds(kind, start - timedelta(days=1))


def local_today(session: Session, user: User) -> date_type:
    """La fecha de hoy en el huso del usuario (el servidor corre en UTC)."""
    settings = user_settings(session, user.id)
    zone = settings.timezone if settings and valid_timezone(settings.timezone) else DEFAULT_TIMEZONE
    return datetime.now(ZoneInfo(zone)).date()


def previous_summary(metrics: dict) -> dict:
    summary = {field: metrics[field] for field in PREVIOUS_FIELDS}
    summary["date_from"] = metrics["date_from"]
    summary["date_to"] = metrics["date_to"]
    summary["night_count"] = len(metrics["night_sessions"])
    summary["night_sessions"] = metrics["night_sessions"]
    summary["by_project"] = [{"name": p["name"], "color": p["color"], "seconds": p["seconds"], "pct": p["pct"]}
                             for p in metrics["by_project"]]
    summary["by_day"] = [{"date": d["date"], "seconds": d["seconds"]} for d in metrics["by_day"]]
    return summary


def days_detail(session: Session, user: User, start: date_type, end: date_type, today: date_type,
                by_day: dict) -> List[dict]:
    """Cada día del periodo, con su estado: worked, today (hoy, sin tiempo aún),
    missing (hábil y sin registro), off (fin de semana, festivo o vacaciones,
    con el motivo) o pending (aún no llega)."""
    calendar = work_calendar(session, user.id, start, end)
    out = []
    day = start
    while day <= end:
        seconds = by_day.get(day.isoformat(), 0)
        reason = None
        if day > today:
            status = "pending"
        elif not calendar.is_workday(day):
            status = "off"
            reason = calendar.off_days.get(day) or "fin de semana"
        elif seconds:
            status = "worked"
        elif day == today:
            status = "today"
        else:
            status = "missing"
        out.append({"date": day.isoformat(), "seconds": seconds, "status": status, "reason": reason,
                    "workday": calendar.is_workday(day)})
        day += timedelta(days=1)
    return out


def weeks_of_month(days: List[dict], today: date_type) -> List[dict]:
    """Las semanas (de lunes a domingo) del mes, recortadas al mes: horas y días
    hábiles transcurridos de cada una ("28–30 sep, 2 días hábiles")."""
    weeks: List[dict] = []
    for day in days:
        d = date_type.fromisoformat(day["date"])
        if not weeks or d.weekday() == 0:
            weeks.append({"start": day["date"], "end": day["date"], "seconds": 0, "workdays": 0, "pending": True})
        week = weeks[-1]
        week["end"] = day["date"]
        week["seconds"] += day["seconds"]
        if day["workday"] and d <= today:
            week["workdays"] += 1
        if d <= today:
            week["pending"] = False
    return weeks


# Días hábiles con registro antes de proyectar: con uno solo, un mes empezado
# "cerraba" en 146 h (ese día por los 20 que faltaban)
PROJECTION_MIN_DAYS = 3


def projection(days: List[dict], total: int) -> Optional[int]:
    """Con el periodo a medias: el total si los días hábiles que faltan siguen
    el promedio de los días hábiles con registro. None si ya terminó o aún no
    hay base (menos de PROJECTION_MIN_DAYS días hábiles con registro)."""
    remaining = sum(1 for d in days if d["status"] == "pending" and d["workday"])
    worked = [d["seconds"] for d in days if d["workday"] and d["status"] == "worked"]
    if not remaining or len(worked) < PROJECTION_MIN_DAYS:
        return None
    return total + round(sum(worked) / len(worked)) * remaining


def _modules(session: Session, user: User) -> dict:
    # Importado aquí: routers.auth importa la app de rutas, no al revés
    from backend.routers.auth import user_modules
    return user_modules(session, user.id)


def ai_enabled(session: Session, user: User) -> bool:
    return _modules(session, user)["ai"]["enabled"]


def rules_text(kind: str, metrics: dict) -> dict:
    """El texto con reglas del tema del reporte."""
    subject = subject_of(kind)
    if subject == "habits":
        return build_habit_text(period_of(kind), metrics)
    if subject == "costs":
        return build_costs_text(metrics)
    return build_text(kind, metrics)


def write_text(session: Session, user: User, report: Report, use_ai: bool) -> Report:
    """
    Pone el texto del reporte a partir de sus cifras: el de la IA si la cuenta
    la tiene encendida y responde bien; si no, el de las reglas, con el motivo
    en text_note cuando la IA debía escribirlo. No hace commit.
    """
    report.text = rules_text(report.kind, report.metrics)
    report.text_source, report.text_model, report.text_note = "rules", None, None
    if not use_ai or not ai_enabled(session, user):
        return report
    config = ai_config()
    if config is None:
        report.text_note = "La IA no está configurada en este servidor"
        return report
    try:
        report.text, report.text_model = write_with_ai(session, user, report.kind, report.metrics, config)
        report.text_source = "ai"
    except AiError as error:
        report.text_note = str(error)
    return report


def generate_report(session: Session, user: User, kind: str, period_start: date_type,
                    today: date_type, trigger: str = "manual", use_ai: bool = True) -> Report:
    """
    Calcula y guarda el reporte del periodo que empieza en `period_start`. Si
    ya existía, lo reemplaza (mismo id): así se corrige un reporte después de
    arreglar registros, y el timer no duplica. Con la IA encendida, ella
    escribe el texto (write_text).
    """
    start, end = period_bounds(kind, period_start)
    metrics = report_metrics(session, user, kind, start, end, today)

    report = session.exec(select(Report).where(
        Report.user_id == user.id, Report.kind == kind, Report.period_start == start)).first()
    if report is None:
        report = Report(user_id=user.id, kind=kind, period_start=start, period_end=end, through=start)
    report.through = date_type.fromisoformat(metrics["through"])
    # Reasignar el dict entero: los JSON no son MutableDict (ver CLAUDE.md)
    report.metrics = metrics
    write_text(session, user, report, use_ai)
    report.trigger = trigger
    report.created_at = utc_now_naive()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def report_metrics(session: Session, user: User, kind: str, start: date_type, end: date_type,
                   today: date_type) -> dict:
    """Las cifras que congela el reporte, según su tema."""
    subject = subject_of(kind)
    if subject == "habits":
        metrics = habit_metrics(session, user, start, end, today)
        metrics["by_week"] = habit_weeks(metrics) if period_of(kind) == "month" else None
    elif subject == "costs":
        metrics = cost_metrics(session, user, start, end, today)
    else:
        metrics = compute_metrics(session, user, start, end, today)
        prev_start, prev_end = previous_period(kind, start)
        metrics["previous"] = previous_summary(compute_metrics(session, user, prev_start, prev_end, today))
        # Lo que solo usa el reporte (no GET /api/metrics): el estado de cada día,
        # las semanas del mes, la proyección al cierre y el total sin lo dudoso
        metrics["days_detail"] = days_detail(session, user, start, end, today,
                                             {d["date"]: d["seconds"] for d in metrics["by_day"]})
        metrics["by_week"] = weeks_of_month(metrics["days_detail"], today) if kind == "month" else None
        metrics["projected_seconds"] = projection(metrics["days_detail"], metrics["total_seconds"])
        metrics["total_without_unconfirmed_seconds"] = metrics["total_seconds"] - metrics["unconfirmed_seconds"]
    metrics["kind"] = kind
    metrics["today"] = today.isoformat()
    return metrics


def _has_time(session: Session, user_id: int, start: date_type, end: date_type) -> bool:
    return session.exec(select(PomodoroSession.id).where(
        PomodoroSession.user_id == user_id,
        PomodoroSession.mode == "focus",
        PomodoroSession.session_date >= start,
        PomodoroSession.session_date <= end,
    ).limit(1)).first() is not None


def _has_activity(session: Session, user_id: int, kind: str, start: date_type, end: date_type) -> bool:
    """¿Hay algo que reportar? Tiempo registrado, un hábito marcado o un gasto."""
    subject = subject_of(kind)
    if subject == "habits":
        return has_habit_activity(session, user_id, start, end)
    if subject == "costs":
        return has_cost_activity(session, user_id, start, end)
    return _has_time(session, user_id, start, end)


def due_periods(kind: str, today: date_type) -> List[date_type]:
    """Inicios de los últimos periodos ya terminados, del más viejo al más nuevo."""
    starts = []
    start, _ = period_bounds(kind, today)
    for _ in range(CATCH_UP[period_of(kind)]):
        start, _ = previous_period(kind, start)
        starts.append(start)
    return sorted(starts)


def missing_reports(session: Session, user: User, today: date_type) -> List[Tuple[str, date_type]]:
    """
    Los reportes automáticos que le faltan a un usuario, como (tipo, inicio):
    periodos ya terminados (en su fecha local), con algo que reportar y sin
    reporte completo. Uno generado a medio periodo con el botón cuenta como
    faltante: se rehace con el periodo entero. Los de hábitos y costos, solo
    con su módulo encendido.
    """
    missing = []
    modules = _modules(session, user)
    for kind in KINDS:
        module = MODULE[subject_of(kind)]
        if module and not modules[module]["enabled"]:
            continue
        for start in due_periods(kind, today):
            _, end = period_bounds(kind, start)
            existing = session.exec(select(Report).where(
                Report.user_id == user.id, Report.kind == kind, Report.period_start == start)).first()
            if existing is not None and existing.through >= end:
                continue
            if _has_activity(session, user.id, kind, start, end):
                missing.append((kind, start))
    return missing


def generate_due_reports(session: Session, user: User, today: Optional[date_type] = None) -> List[Report]:
    """Genera los reportes que faltan (missing_reports) con la fecha local del usuario."""
    today = today or local_today(session, user)
    return [generate_report(session, user, kind, start, today, trigger="auto")
            for kind, start in missing_reports(session, user, today)]
