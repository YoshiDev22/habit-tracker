"""
Cálculos de dinero del plan maker (épica 24): mano de obra, gastos, costo y
margen. Los usan la ficha del proyecto (routers/projects.py) y la pestaña
Costos (routers/costs.py), así que las cifras son las mismas en las dos.

Todo en centavos enteros. Lo único decimal es la cantidad de un gasto (2.5 m),
que no es dinero: el total del renglón se redondea al centavo una sola vez.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, Optional

from sqlmodel import Session, select

from backend.models import ProjectCost, ProjectFinance
from backend.schemas import ProjectFinanceResponse


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
