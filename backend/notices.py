"""
El centro de avisos (1.26): la campanita, guardada por cuenta.

Dos tipos de aviso, en la misma tabla `notices` (uno por usuario, tipo y
referencia):

- **Pendientes**, que se calculan de los datos y piden algo: un registro por
  confirmar (`review`, ref = id de la sesión) o un día sin anotar con racha
  (`missed_day`, ref = la fecha). La fila se crea la primera vez que aparecen
  (sync_pending) y su estado sale siempre de los datos: "pending" mientras siga
  sin resolverse, "done" al resolverse (corregir, confirmar, marcar algo ese
  día) y "dismissed" si se descartó. Así nunca dicen algo que ya no es cierto.
- **Informativos**, que se guardan cuando pasan: reporte automático listo
  (`report_ready`, ref = id del reporte), Novedades de una versión
  (`novedades`, ref = la versión) y avisos para todas las cuentas
  (`announcement`, ref = id del anuncio: mantenimiento, por ejemplo; los
  publica scripts/announce.py). Se leen y ya. Un anuncio vencido o terminado
  desaparece de todas las campanitas.

El círculo rojo cuenta los pendientes más los informativos sin leer. Lo que no
es pendiente se borra a los 60 días.
"""
from datetime import date as date_type, timedelta
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import Announcement, HabitEntry, Notice, PomodoroSession, Report, User, utc_now_naive

PENDING_KINDS = ("review", "missed_day")
INFO_KINDS = ("report_ready", "novedades", "announcement")
KEEP_DAYS = 60
SUBJECT_TITLE = {"time": "tiempo", "habits": "hábitos", "costs": "costos"}
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _short(day: date_type) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def add_notice(session: Session, user_id: int, kind: str, ref: str) -> Optional[Notice]:
    """Crea el aviso si no existe ya (único por usuario, tipo y referencia). No
    hace commit (sí flush). Devuelve el que quedó."""
    existing = session.exec(select(Notice).where(
        Notice.user_id == user_id, Notice.kind == kind, Notice.ref == ref)).first()
    if existing is not None:
        return existing
    notice = Notice(user_id=user_id, kind=kind, ref=ref)
    session.add(notice)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        return session.exec(select(Notice).where(
            Notice.user_id == user_id, Notice.kind == kind, Notice.ref == ref)).first()
    return notice


def sync_pending(session: Session, user: User, today: date_type, habits_on: bool) -> None:
    """Crea la fila de los pendientes que aparecieron desde la última vez."""
    for sid in session.exec(select(PomodoroSession.id).where(
            PomodoroSession.user_id == user.id, PomodoroSession.needs_review == True)).all():  # noqa: E712
        add_notice(session, user.id, "review", str(sid))
    if habits_on:
        # La misma regla que "¿Olvidaste anotar ayer?" (la racha la calcula el backend)
        from backend.routers.habits import calculate_streak
        missed = calculate_streak(user.id, session, user, today).missed_yesterday
        if missed:
            add_notice(session, user.id, "missed_day", missed["date"].isoformat())


def _day_has_habit(session: Session, user_id: int, day: date_type) -> bool:
    entry = session.exec(select(HabitEntry).where(
        HabitEntry.user_id == user_id, HabitEntry.entry_date == day)).first()
    return bool(entry and any((entry.habits_data or {}).values()))


def describe(session: Session, notice: Notice) -> Optional[Dict]:
    """El aviso como lo pinta la campanita, con su estado calculado. None si ya
    no tiene a qué referirse (un reporte borrado con su cuenta, p. ej.)."""
    base = {"id": notice.id, "kind": notice.kind, "ref": notice.ref, "created_at": notice.created_at,
            "read": notice.read_at is not None}
    if notice.kind == "review":
        s = session.exec(select(PomodoroSession).where(
            PomodoroSession.user_id == notice.user_id, PomodoroSession.id == int(notice.ref))).first()
        pending = bool(s and s.needs_review)
        status = "dismissed" if notice.dismissed_at and not pending else ("pending" if pending else "done")
        return {**base, "status": status, "title": "Registro por confirmar",
                "detail": ("Un cronómetro llegó a 8 h sin que dijeras cuánto trabajaste."
                           if pending else "Lo confirmaste o lo corregiste."),
                "session_id": s.id if s else None, "session_date": s.session_date.isoformat() if s else None}
    if notice.kind == "missed_day":
        day = date_type.fromisoformat(notice.ref)
        done = _day_has_habit(session, notice.user_id, day)
        status = "done" if done else ("dismissed" if notice.dismissed_at else "pending")
        return {**base, "status": status, "title": "Día sin anotar",
                "detail": ("Ese día no anotaste ningún hábito. Si sí lo hiciste, márcalo y tu racha vuelve."
                           if status == "pending" else "Ya anotaste ese día." if done else "Lo descartaste."),
                "date": notice.ref}
    if notice.kind == "report_ready":
        report = session.exec(select(Report).where(
            Report.user_id == notice.user_id, Report.id == int(notice.ref))).first()
        if report is None:
            return None
        from backend.report_kinds import period_of, subject_of
        period = "semanal" if period_of(report.kind) == "week" else "mensual"
        return {**base, "status": "info", "title": f"Tu reporte {period} de {SUBJECT_TITLE[subject_of(report.kind)]} está listo",
                "detail": f"Del {_short(report.period_start)} al {_short(report.period_end)} de {report.period_end.year}.",
                "report_id": report.id, "report_kind": report.kind}
    if notice.kind == "announcement":
        ann = session.get(Announcement, int(notice.ref))
        if ann is None or (ann.ends_at is not None and ann.ends_at <= utc_now_naive()):
            return None   # terminado o vencido: se va de la campanita
        return {**base, "status": "info", "title": ann.title, "detail": ann.body, "announcement": True}
    if notice.kind == "novedades":
        return {**base, "status": "info", "title": f"Novedades de la versión {notice.ref}",
                "detail": "Mira qué hay de nuevo.", "version": notice.ref}
    return None


def list_notices(session: Session, user: User, today: date_type, habits_on: bool,
                 current_version: Optional[str]) -> Dict:
    """Sincroniza, limpia lo viejo y devuelve {unread, notices} (lo pendiente arriba)."""
    sync_pending(session, user, today, habits_on)
    if current_version:
        add_notice(session, user.id, "novedades", current_version)
    # Los anuncios vigentes para todas las cuentas
    now = utc_now_naive()
    for ann in session.exec(select(Announcement).where(
            (Announcement.ends_at == None) | (Announcement.ends_at > now))).all():  # noqa: E711
        add_notice(session, user.id, "announcement", str(ann.id))
    cutoff = utc_now_naive() - timedelta(days=KEEP_DAYS)
    rows = session.exec(select(Notice).where(Notice.user_id == user.id)
                        .order_by(Notice.created_at.desc(), Notice.id.desc())).all()
    out: List[Dict] = []
    for notice in rows:
        item = describe(session, notice)
        if item is None or (item["status"] != "pending" and notice.created_at < cutoff):
            session.delete(notice)
            continue
        out.append(item)
    session.commit()
    order = {"pending": 0, "info": 1, "done": 2, "dismissed": 2}
    out.sort(key=lambda n: (order[n["status"]], -n["created_at"].timestamp()))
    unread = sum(1 for n in out if n["status"] == "pending" or (n["status"] == "info" and not n["read"]))
    return {"unread": unread, "notices": out}
