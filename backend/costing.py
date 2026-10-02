"""
Cálculos de dinero del plan maker (épica 24): mano de obra, gastos, costo y
margen. Los usan la ficha del proyecto (routers/projects.py) y la pestaña
Costos (routers/costs.py), así que las cifras son las mismas en las dos.

Todo en centavos enteros. Lo único decimal es la cantidad de un gasto (2.5 m),
que no es dinero: el total del renglón se redondea al centavo una sola vez.

También vive aquí el estimado contra real (Fase 4), por la misma razón: la ficha
y Costos lo calculan con la misma función y sus cifras cuadran.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from backend.models import PomodoroSession, ProjectCost, ProjectFinance, Tag, Task, TaskTag
from backend.schemas import EstimateDeviation, EstimateRow, EstimateTagRow, ProjectFinanceResponse

# Con menos tareas que esto, una fila dice "todavía hay poco historial": una
# sola tarea que salió muy mal (o muy bien) no es una tendencia
ESTIMATE_MIN_TASKS = 3


def line_total_cents(quantity: float, unit_cost_cents: int) -> int:
    """Cantidad × costo unitario, con .5 hacia arriba como se espera del dinero
    (round() de Python redondea al par). Decimal desde el texto de la cantidad
    para que 2.675 sea 2.675 y no 2.67499..."""
    exact = Decimal(str(quantity)) * unit_cost_cents
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def labor_cents(total_seconds: int, hourly_rate_cents: Optional[int]) -> Optional[int]:
    """Horas × tarifa, redondeado al centavo; None sin tarifa"""
    if hourly_rate_cents is None:
        return None
    # Enteros: segundos × tarifa ÷ 3600, con .5 hacia arriba
    return (total_seconds * hourly_rate_cents + 1800) // 3600


def percent(part: int, whole: Optional[int]) -> Optional[int]:
    return (part * 100 * 2 + whole) // (whole * 2) if whole else None


def costs_cents_by_project(session: Session, user_id: int, project_ids: Optional[Iterable[int]] = None) -> Dict[int, int]:
    """Suma de los gastos de cada proyecto (cada renglón redondeado aparte,
    igual que en la hoja)"""
    query = select(ProjectCost).where(ProjectCost.user_id == user_id)
    if project_ids is not None:
        query = query.where(ProjectCost.project_id.in_(list(project_ids)))
    totals: Dict[int, int] = {}
    for cost in session.exec(query).all():
        totals[cost.project_id] = totals.get(cost.project_id, 0) + line_total_cents(cost.quantity, cost.unit_cost_cents)
    return totals


def finance_row(session: Session, user_id: int, project_id: int) -> Optional[ProjectFinance]:
    return session.exec(
        select(ProjectFinance).where(ProjectFinance.user_id == user_id, ProjectFinance.project_id == project_id)
    ).first()


def finance_response(project_id: int, row: Optional[ProjectFinance], total_seconds: int,
                     costs_cents: int = 0) -> ProjectFinanceResponse:
    """El costeo guardado (o vacío, sin fila) cruzado con el tiempo y los
    gastos del proyecto."""
    rate = row.hourly_rate_cents if row else None
    labor = labor_cents(total_seconds, rate)
    budget_cents = row.budget_cents if row else None
    budget_minutes = row.budget_minutes if row else None
    total_cost = (labor or 0) + costs_cents
    has_cost = labor is not None or costs_cents > 0
    return ProjectFinanceResponse(
        project_id=project_id,
        client_name=row.client_name if row else None,
        hourly_rate_cents=rate,
        currency=row.currency if row else "MXN",
        budget_cents=budget_cents,
        budget_minutes=budget_minutes,
        total_seconds=total_seconds,
        labor_cents=labor,
        # El presupuesto en dinero se consume con todo el costo: horas y gastos
        budget_money_pct=percent(total_cost, budget_cents) if has_cost else None,
        budget_time_pct=percent(total_seconds, budget_minutes * 60 if budget_minutes else None),
        # Una cotización: hay presupuesto y aún no se ha trabajado en él
        is_quote=bool(budget_cents or budget_minutes) and total_seconds == 0,
        costs_cents=costs_cents,
        total_cost_cents=total_cost,
        margin_cents=budget_cents - total_cost if budget_cents is not None else None,
    )


# ==================== Estimado contra real ====================

def estimate_counts(estimate_minutes: Optional[int], is_done: bool, seconds: int) -> bool:
    """Si una tarea entra en el desvío: con estimado y con tiempo, terminada o
    ya pasada de su estimado. Una abierta que va por debajo no cuenta todavía:
    su tiempo real no se conoce, y contarla diría "tardas 0.3×" de una tarea a
    medias. Una abierta pasada sí: al terminar solo puede desviarse más."""
    if not estimate_minutes or seconds <= 0:
        return False
    return is_done or seconds > estimate_minutes * 60


def _estimate_row(tasks: int, estimate_seconds: int, actual_seconds: int) -> dict:
    return {
        "tasks": tasks,
        "estimate_seconds": estimate_seconds,
        "actual_seconds": actual_seconds,
        # Cociente de sumas, no promedio de cocientes: una tarea de 5 minutos
        # estimada en 1 no domina la cifra
        "ratio_pct": percent(actual_seconds, estimate_seconds) if tasks >= ESTIMATE_MIN_TASKS else None,
    }


def estimate_deviation(tasks: Iterable[Task], seconds_by_task: Dict[int, int],
                       tags_by_task: Dict[int, List[int]], tags: Dict[int, Tag]) -> EstimateDeviation:
    """Real contra estimado: en total (cada tarea una vez), por etiqueta (una
    tarea con dos etiquetas cuenta en las dos) y sin etiqueta. Pura: recibe el
    tiempo de cada tarea y sus etiquetas ya leídos."""
    overall = [0, 0, 0]
    untagged = [0, 0, 0]
    by_tag: Dict[int, List[int]] = {}
    for t in tasks:
        actual = seconds_by_task.get(t.id, 0)
        if not estimate_counts(t.estimate_minutes, t.is_done, actual):
            continue
        estimate = t.estimate_minutes * 60
        task_tags = [tag_id for tag_id in tags_by_task.get(t.id, []) if tag_id in tags]
        for acc in [overall] + ([by_tag.setdefault(tag_id, [0, 0, 0]) for tag_id in task_tags] or [untagged]):
            acc[0] += 1
            acc[1] += estimate
            acc[2] += actual
    return EstimateDeviation(
        min_tasks=ESTIMATE_MIN_TASKS,
        overall=EstimateRow(**_estimate_row(*overall)),
        tags=sorted(
            (EstimateTagRow(tag_id=tag_id, name=tags[tag_id].name, color=tags[tag_id].color, **_estimate_row(*acc))
             for tag_id, acc in by_tag.items()),
            key=lambda row: (-row.tasks, row.name),
        ),
        untagged=EstimateRow(**_estimate_row(*untagged)),
    )


def estimates_for_tasks(session: Session, user_id: int, project_id: Optional[int] = None) -> EstimateDeviation:
    """El desvío de las tareas de un proyecto, o de todas las del usuario. El
    tiempo de cada tarea es el de su campo seconds (sesiones focus de la tarea,
    sea cual sea su proyecto), así que vale también en proyectos archivados."""
    query = select(Task).where(Task.user_id == user_id, Task.estimate_minutes.is_not(None))
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    tasks = session.exec(query).all()
    ids = [t.id for t in tasks]
    seconds: Dict[int, int] = {}
    tags_by_task: Dict[int, List[int]] = {}
    tags: Dict[int, Tag] = {}
    if ids:
        seconds = dict(session.exec(
            select(PomodoroSession.task_id, func.sum(PomodoroSession.duration_seconds))
            .where(PomodoroSession.user_id == user_id, PomodoroSession.task_id.in_(ids),
                   PomodoroSession.mode == "focus")
            .group_by(PomodoroSession.task_id)
        ).all())
        for task_id, tag in session.exec(
            select(TaskTag.task_id, Tag).join(Tag, Tag.id == TaskTag.tag_id)
            .where(TaskTag.user_id == user_id, Tag.user_id == user_id, TaskTag.task_id.in_(ids))
        ).all():
            tags_by_task.setdefault(task_id, []).append(tag.id)
            tags[tag.id] = tag
    return estimate_deviation(tasks, {k: v or 0 for k, v in seconds.items()}, tags_by_task, tags)
