"""
Reportes guardados (épica 30, Fase 4): qué periodo cubre cada uno, cómo se
genera y cuáles le tocan a un usuario. Las cifras salen de backend/metrics.py
y el texto de backend/report_text.py. Lo usan el router (el botón "Generar
reporte") y scripts/generate_reports.py (el timer de systemd).

Periodos: la semana va de lunes a domingo, como la pestaña Reportes, y el mes
del día 1 al último. El automático sale cuando el periodo ya terminó en la
fecha LOCAL del usuario: el lunes, el de la semana anterior; el día 1, el del
mes anterior.
"""
import calendar as calendar_module
from datetime import date as date_type, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from backend.days import DEFAULT_TIMEZONE, user_settings, valid_timezone
from backend.metrics import compute_metrics
from backend.models import PomodoroSession, Report, User, utc_now_naive
from backend.report_text import build_text

KINDS = ("week", "month")
# Si el timer no corrió (servidor apagado), cuántos periodos hacia atrás pone al día
CATCH_UP = {"week": 4, "month": 2}
# Del periodo anterior se guarda solo lo que el reporte compara
PREVIOUS_FIELDS = ("total_seconds", "days", "workdays", "active_days", "active_workdays",
                   "avg_seconds_per_active_day", "median_seconds_per_active_day", "session_count")
PREVIOUS_TOP_PROJECTS = 5


def period_bounds(kind: str, day: date_type) -> Tuple[date_type, date_type]:
    """El periodo de ese tipo que contiene `day`: (inicio, fin), los dos incluidos."""
    if kind == "week":
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


def _previous_summary(metrics: dict) -> dict:
    summary = {field: metrics[field] for field in PREVIOUS_FIELDS}
    summary["date_from"] = metrics["date_from"]
    summary["date_to"] = metrics["date_to"]
    summary["by_project"] = [{"name": p["name"], "seconds": p["seconds"]}
                             for p in metrics["by_project"][:PREVIOUS_TOP_PROJECTS]]
    return summary


def generate_report(session: Session, user: User, kind: str, period_start: date_type,
                    today: date_type, trigger: str = "manual") -> Report:
    """
    Calcula y guarda el reporte del periodo que empieza en `period_start`. Si
    ya existía, lo reemplaza (mismo id): así se corrige un reporte después de
    arreglar registros, y el timer no duplica.
    """
    start, end = period_bounds(kind, period_start)
    metrics = compute_metrics(session, user, start, end, today)
    prev_start, prev_end = previous_period(kind, start)
    metrics["previous"] = _previous_summary(compute_metrics(session, user, prev_start, prev_end, today))

    report = session.exec(select(Report).where(
        Report.user_id == user.id, Report.kind == kind, Report.period_start == start)).first()
    if report is None:
        report = Report(user_id=user.id, kind=kind, period_start=start, period_end=end, through=start)
    report.through = date_type.fromisoformat(metrics["through"])
    # Reasignar el dict entero: los JSON no son MutableDict (ver CLAUDE.md)
    report.metrics = metrics
    report.text = build_text(kind, metrics)
    report.text_source = "rules"
    report.trigger = trigger
    report.created_at = utc_now_naive()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _has_activity(session: Session, user_id: int, start: date_type, end: date_type) -> bool:
    return session.exec(select(PomodoroSession.id).where(
        PomodoroSession.user_id == user_id,
        PomodoroSession.mode == "focus",
        PomodoroSession.session_date >= start,
        PomodoroSession.session_date <= end,
    ).limit(1)).first() is not None


def due_periods(kind: str, today: date_type) -> List[date_type]:
    """Inicios de los últimos periodos ya terminados, del más viejo al más nuevo."""
    starts = []
    start, _ = period_bounds(kind, today)
    for _ in range(CATCH_UP[kind]):
        start, _ = previous_period(kind, start)
        starts.append(start)
    return sorted(starts)


def generate_due_reports(session: Session, user: User, today: Optional[date_type] = None) -> List[Report]:
    """
    Los reportes automáticos que le faltan a un usuario: periodos ya terminados
    (en su fecha local), con algún registro de tiempo y sin reporte completo.
    Uno generado a medio periodo con el botón se rehace con el periodo entero.
    """
    today = today or local_today(session, user)
    made = []
    for kind in KINDS:
        for start in due_periods(kind, today):
            _, end = period_bounds(kind, start)
            existing = session.exec(select(Report).where(
                Report.user_id == user.id, Report.kind == kind, Report.period_start == start)).first()
            if existing is not None and existing.through >= end:
                continue
            if not _has_activity(session, user.id, start, end):
                continue
            made.append(generate_report(session, user, kind, start, today, trigger="auto"))
    return made
