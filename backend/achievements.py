"""
Logros: lo que no es la API en sí (routers/achievements.py).

- Las listas de inicio de cada cuenta (categorías y acciones del SOS), perezosas
  como las categorías de gastos.
- Los hitos automáticos: al cruzar 10, 25, 50, 100, 250 o 500 horas de enfoque en
  un proyecto, o esa misma cantidad de días cumplidos de un hábito (los hábitos
  son sí/no y no tienen horas). Solo LEEN sesiones y registros de hábitos.
- El botón SOS: logros al azar (las anécdotas y los destacados pesan más), un dato
  real y siempre acumulado (nunca de la semana) y una acción pequeña.
"""
import random
from datetime import date as date_type
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import (Achievement, AchievementCategory, Habit, HabitEntry, PomodoroSession, Project,
                            SosAction, Task)

KINDS = ("diploma", "anecdote", "milestone")
PRECISIONS = ("day", "month")
ORIGINS = ("manual", "auto", "objective")   # "objective": reservado, nada lo crea aún

DEFAULT_CATEGORIES = ["Académico", "Profesional", "Docencia", "Concursos", "Personal", "Superación"]
DEFAULT_SOS_ACTIONS = [
    "Salir a caminar 10 minutos",
    "Escribir un párrafo de lo que tengas pendiente",
    "Ordenar tu escritorio por 10 minutos",
    "Tomar un vaso de agua y estirarte",
    "Avanzar 10 minutos en la tarea más pequeña de tu tablero",
]

# Los mismos números para horas de un proyecto y días cumplidos de un hábito
MILESTONES = (10, 25, 50, 100, 250, 500)

# Cuánto pesa en el sorteo del SOS una anécdota o un destacado frente a los demás
SOS_WEIGHT = 3
SOS_COUNT = 3

# Las pruebas lo cambian por random.Random(semilla) para que el sorteo se repita
rng = random.SystemRandom()


def _seed_once(session: Session, model, user_id: int, rows: Sequence[dict]) -> None:
    """Las filas de inicio, una sola vez: con alguna fila, la cuenta ya entró (la
    última no se puede borrar). Una restricción única o la doble petición se
    resuelven con el rollback."""
    if session.exec(select(model.id).where(model.user_id == user_id)).first() is not None:
        return
    for order, fields in enumerate(rows):
        session.add(model(user_id=user_id, order=order, **fields))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()


def ensure_defaults(session: Session, user_id: int) -> None:
    _seed_once(session, AchievementCategory, user_id, [{"name": name} for name in DEFAULT_CATEGORIES])
    _seed_once(session, SosAction, user_id, [{"text": text} for text in DEFAULT_SOS_ACTIONS])


# ==================== Hitos automáticos ====================

def _crossings(points: List[tuple], thresholds: Sequence[int]) -> Dict[int, date_type]:
    """Para una serie (fecha, cantidad) en orden, el día en que el acumulado llega
    a cada umbral."""
    reached: Dict[int, date_type] = {}
    total = 0
    pending = list(thresholds)
    for day, amount in points:
        total += amount
        while pending and total >= pending[0]:
            reached[pending.pop(0)] = day
        if not pending:
            break
    return reached


def project_milestones(session: Session, user_id: int) -> List[dict]:
    """Los hitos de horas de enfoque por proyecto ("Sin asignar" no cuenta)."""
    projects = {p.id: p for p in session.exec(
        select(Project).where(Project.user_id == user_id, Project.is_system == False)  # noqa: E712
    ).all()}
    sessions = session.exec(
        select(PomodoroSession.project_id, PomodoroSession.session_date, PomodoroSession.duration_seconds)
        .where(PomodoroSession.user_id == user_id, PomodoroSession.mode == "focus",
               PomodoroSession.project_id.is_not(None))
        .order_by(PomodoroSession.session_date, PomodoroSession.started_at, PomodoroSession.id)
    ).all()
    by_project: Dict[int, List[tuple]] = {}
    for project_id, day, seconds in sessions:
        if project_id in projects:
            by_project.setdefault(project_id, []).append((day, seconds or 0))
    found = []
    for project_id, points in by_project.items():
        for hours, day in _crossings(points, [h * 3600 for h in MILESTONES]).items():
            hours //= 3600
            found.append({"auto_key": f"project:{project_id}:{hours}h", "achieved_on": day,
                          "title": f"{hours} h de enfoque en {projects[project_id].name}"})
    return found


def habit_done_days(session: Session, user_id: int) -> Dict[str, List[date_type]]:
    """Los días cumplidos de cada hábito (por su clave), en orden."""
    done: Dict[str, List[date_type]] = {}
    for entry in session.exec(select(HabitEntry).where(HabitEntry.user_id == user_id)).all():
        for key, value in (entry.habits_data or {}).items():
            if value:
                done.setdefault(key, []).append(entry.entry_date)
    return {key: sorted(set(days)) for key, days in done.items()}


def habit_milestones(session: Session, user_id: int) -> List[dict]:
    """Los hitos de días cumplidos de cada hábito, activo u oculto."""
    labels = {h.key: h.label for h in session.exec(select(Habit).where(Habit.user_id == user_id)).all()}
    found = []
    for key, days in habit_done_days(session, user_id).items():
        if key not in labels:
            continue
        for count, day in _crossings([(d, 1) for d in days], MILESTONES).items():
            found.append({"auto_key": f"habit:{key}:{count}d", "achieved_on": day,
                          "title": f"{count} días cumplidos de {labels[key]}"})
    return found


def sync_milestones(session: Session, user_id: int, habits: bool = True) -> int:
    """
    Crea los hitos que se cruzaron y aún no existen. Uno que ya existe (también
    oculto o borrado) no se toca: ni su título ni su fecha, aunque después cambie
    el nombre del proyecto o se borren horas. Devuelve cuántos creó.
    """
    found = project_milestones(session, user_id) + (habit_milestones(session, user_id) if habits else [])
    if not found:
        return 0
    existing = set(session.exec(
        select(Achievement.auto_key).where(Achievement.user_id == user_id, Achievement.auto_key.is_not(None))
    ).all())
    new = [m for m in found if m["auto_key"] not in existing]
    for milestone in new:
        session.add(Achievement(user_id=user_id, kind="milestone", origin="auto", date_precision="day", **milestone))
    if new:
        try:
            session.commit()
        except IntegrityError:   # otra petición los creó al mismo tiempo
            session.rollback()
            return 0
    return len(new)


# ==================== Botón SOS ====================

def sos_weight(achievement: Achievement) -> int:
    return SOS_WEIGHT if achievement.kind == "anecdote" or achievement.is_featured else 1


def pick_achievements(candidates: List[Achievement], exclude: Sequence[int], count: int = SOS_COUNT):
    """
    Hasta `count` logros al azar, sin repetir los de `exclude` (los ya vistos en
    esta apertura del SOS) ni entre sí. Sorteo con peso (Efraimidis y Spirakis):
    cada uno saca rng.random() ** (1 / peso) y ganan los más altos. Si ya no queda
    ninguno sin ver, vuelve a empezar con todos y `restarted` lo dice.
    """
    seen = set(exclude)
    pool = [a for a in candidates if a.id not in seen]
    restarted = False
    if not pool and candidates:
        pool, restarted = list(candidates), True
    keyed = sorted(pool, key=lambda a: rng.random() ** (1.0 / sos_weight(a)), reverse=True)
    return keyed[:count], restarted


def _hours(seconds: int) -> str:
    hours = seconds / 3600
    return f"{hours:.1f}".rstrip("0").rstrip(".")


def cumulative_facts(session: Session, user_id: int, habits: bool, best_streak: Optional[int]) -> List[str]:
    """
    Datos reales del registro, siempre acumulados desde el principio: horas
    totales de cada proyecto, días cumplidos de cada hábito, la racha más larga y
    las tareas terminadas. Solo los que tienen algo (nunca un "0 h").
    """
    facts = []
    rows = session.exec(
        select(Project.name, func.sum(PomodoroSession.duration_seconds))
        .join(Project, Project.id == PomodoroSession.project_id)
        .where(PomodoroSession.user_id == user_id, Project.user_id == user_id, PomodoroSession.mode == "focus",
               Project.is_system == False)  # noqa: E712
        .group_by(Project.id)
    ).all()
    for name, seconds in rows:
        if seconds and seconds >= 3600:
            facts.append(f"Llevas {_hours(seconds)} h de enfoque registradas en {name}.")
    if habits:
        labels = {h.key: h.label for h in session.exec(select(Habit).where(Habit.user_id == user_id)).all()}
        for key, days in habit_done_days(session, user_id).items():
            if key in labels and len(days) >= 2:
                facts.append(f"Has cumplido {labels[key]} {len(days)} días en total.")
        if best_streak and best_streak >= 2:
            facts.append(f"Tu racha más larga es de {best_streak} días.")
    done = session.exec(
        select(func.count(Task.id)).where(Task.user_id == user_id, Task.is_done == True)  # noqa: E712
    ).one()
    if done:
        facts.append(f"Has terminado {done} tareas desde que usas la app." if done > 1
                     else "Ya terminaste tu primera tarea en la app.")
    return facts
