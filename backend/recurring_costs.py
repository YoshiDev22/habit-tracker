"""
Gastos repartidos y recurrentes del plan Maker (1.24).

Repartido: un gasto entre varios proyectos de la misma moneda es una fila de
project_costs por proyecto, con los mismos datos del gasto, el mismo split_id
(el id de la primera fila), su porcentaje en puntos base (split_bp) y su parte
en centavos (share_cents), repartida con split_shares() para que las partes
sumen exacto el total. Así el resumen, la ficha y los reportes no cambian: cada
proyecto suma su fila. Editar una parte edita el gasto entero.

Recurrente: RecurringCost guarda el gasto y cada cuándo se cobra (cada mes o
cada año, en el día de start_date). generate_due() convierte los cobros que ya
llegaron en gastos reales (con recurring_id), al entrar a Costos, al generar un
reporte de costos y con el timer diario. `generated` cuenta los cobros hechos:
un gasto generado que se borra no vuelve, y cambiar el recurrente solo afecta a
los siguientes. El índice único (recurring_id, cost_date, project_id) frena que
dos peticiones a la vez generen el mismo cobro.
"""
import calendar
from datetime import date as date_type
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.costing import BP_TOTAL, line_total_cents, split_shares
from backend.models import Project, ProjectCost, RecurringCost

FREQUENCIES = ("monthly", "yearly")
# Cobros que se ponen al día de una vez (un recurrente que empezó hace mucho)
MAX_CATCH_UP = 36


def occurrence(start: date_type, frequency: str, n: int) -> date_type:
    """El cobro número n (0 = el primero): mismo día del mes, o el último si el
    mes es más corto; cada año, el mismo día (el 29 de febrero, el 28 si no hay)."""
    months = n * (12 if frequency == "yearly" else 1)
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date_type(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def next_date(rc: RecurringCost) -> Optional[date_type]:
    """El siguiente cobro por generar, o None si ya terminó."""
    d = occurrence(rc.start_date, rc.frequency, rc.generated)
    return None if rc.end_date is not None and d > rc.end_date else d


def proportional_bps(bps: List[int]) -> List[int]:
    """Reescala a 10000 puntos base (si un proyecto del reparto ya no existe)."""
    total = sum(bps)
    return split_shares(BP_TOTAL, bps, base=total) if total else []


def create_cost_rows(session: Session, user_id: int, fields: Dict, allocations: List[Dict],
                     recurring_id: Optional[int] = None) -> List[ProjectCost]:
    """Las filas de un gasto: una si va a un solo proyecto, una por proyecto si
    va repartido. `fields` trae category_id, cost_date, concept, quantity,
    unit_cost_cents y note. No hace commit (sí flush, para el split_id)."""
    rows = [ProjectCost(user_id=user_id, project_id=a["project_id"], recurring_id=recurring_id, **fields)
            for a in allocations]
    if len(rows) > 1:
        total = line_total_cents(fields["quantity"], fields["unit_cost_cents"])
        shares = split_shares(total, [a["bp"] for a in allocations])
        for row, a, share in zip(rows, allocations, shares):
            row.split_bp, row.share_cents = a["bp"], share
    for row in rows:
        session.add(row)
    session.flush()
    if len(rows) > 1:
        for row in rows:
            row.split_id = rows[0].id
            session.add(row)
    return rows


def reshare(rows: List[ProjectCost]) -> None:
    """Vuelve a repartir el total de un gasto entre sus filas (tras cambiar el
    monto o la cantidad), con los mismos porcentajes."""
    if len(rows) < 2:
        return
    total = line_total_cents(rows[0].quantity, rows[0].unit_cost_cents)
    for row, share in zip(rows, split_shares(total, [r.split_bp for r in rows])):
        row.share_cents = share


def valid_allocations(session: Session, user_id: int, allocations: List[Dict]) -> List[Dict]:
    """Las del recurrente cuyos proyectos siguen existiendo, reescaladas si falta alguno."""
    ids = {p.id for p in session.exec(select(Project).where(
        Project.user_id == user_id, Project.is_system == False)).all()}  # noqa: E712
    alive = [a for a in allocations if a["project_id"] in ids]
    if len(alive) == len(allocations):
        return alive
    return [{"project_id": a["project_id"], "bp": bp}
            for a, bp in zip(alive, proportional_bps([a["bp"] for a in alive]))]


def generate_due(session: Session, user_id: int, today: date_type) -> List[ProjectCost]:
    """Convierte en gastos los cobros de los recurrentes que ya llegaron (en la
    fecha local del usuario). Idempotente. Hace commit si generó algo."""
    created: List[ProjectCost] = []
    recurring = session.exec(select(RecurringCost).where(
        RecurringCost.user_id == user_id, RecurringCost.paused == False)).all()  # noqa: E712
    for rc in recurring:
        allocations = valid_allocations(session, user_id, rc.allocations or [])
        if not allocations:
            # Sus proyectos ya no existen: se pausa en vez de fallar cada día
            rc.paused = True
            session.add(rc)
            continue
        for _ in range(MAX_CATCH_UP):
            due = next_date(rc)
            if due is None or due > today:
                break
            # Ya hay un gasto suyo en esa fecha (p. ej. el que se volvió recurrente):
            # cuenta como ese cobro. Generarlo chocaría con el índice único y el
            # recurrente se quedaría atascado sin avanzar.
            if session.exec(select(ProjectCost.id).where(
                    ProjectCost.user_id == user_id, ProjectCost.recurring_id == rc.id,
                    ProjectCost.cost_date == due).limit(1)).first() is not None:
                rc.generated += 1
                session.add(rc)
                continue
            fields = dict(category_id=rc.category_id, cost_date=due, concept=rc.concept,
                          quantity=rc.quantity, unit_cost_cents=rc.unit_cost_cents, note=rc.note)
            created += create_cost_rows(session, user_id, fields, allocations, recurring_id=rc.id)
            rc.generated += 1
            session.add(rc)
    if created or session.dirty:
        try:
            session.commit()
        except IntegrityError:
            # Otra petición generó lo mismo a la vez: lo suyo ya quedó guardado
            session.rollback()
            return []
    return created


def last_charge(session: Session, rc: RecurringCost) -> Optional[date_type]:
    """La fecha del último gasto anotado por este recurrente (None si ninguno)."""
    return session.exec(select(func.max(ProjectCost.cost_date)).where(
        ProjectCost.user_id == rc.user_id, ProjectCost.recurring_id == rc.id)).one()


def skip_past(rc: RecurringCost, today: date_type) -> None:
    """Al reanudar uno pausado: los cobros del tiempo en pausa no se generan."""
    for _ in range(10000):
        due = next_date(rc)
        if due is None or due >= today:
            return
        rc.generated += 1
