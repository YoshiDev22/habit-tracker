"""
Finanzas: el rendimiento de una cuenta (docs/specs/finanzas-apartados-rendimientos.md).

El diario, sin plazo: la tasa de `fin_yield_rates` sobre el saldo de cada día,
desde el último rendimiento anotado hasta ayer (el banco paga el día cuando
termina). Lo ganado se suma al saldo de los días siguientes, como lo pagan. No
se guarda: se estima, y el usuario lo anota (un ingreso con source = "yield")
con esa cifra o con la del banco.

Dinero en centavos; los días se suman en Decimal y se redondea una vez, al
final, con .5 hacia arriba (sumar redondeos diarios acumularía error).
"""
from datetime import date as date_type, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlmodel import Session, select

from backend.finance import account_balances
from backend.models import FinAccount, FinCategory, FinTransaction, FinYieldRate

YIELD_SOURCE = "yield"
YIELD_CATEGORY = ("Rendimientos", "#2ecc71", "income", "trending-up")
YIELD_CONCEPT = "Rendimientos"
DAY_BASES = (365, 360)


def account_rates(session: Session, user_id: int, account_id: int) -> List[FinYieldRate]:
    return session.exec(select(FinYieldRate).where(FinYieldRate.user_id == user_id,
                                                   FinYieldRate.account_id == account_id)
                        .order_by(FinYieldRate.from_date)).all()


def rates_by_account(session: Session, user_id: int) -> Dict[int, List[FinYieldRate]]:
    out: Dict[int, List[FinYieldRate]] = {}
    for rate in session.exec(select(FinYieldRate).where(FinYieldRate.user_id == user_id)
                             .order_by(FinYieldRate.from_date)).all():
        out.setdefault(rate.account_id, []).append(rate)
    return out


def rate_on(rates: List[FinYieldRate], day: date_type) -> Optional[FinYieldRate]:
    """La tasa que vale ese día: la última que empezó en él o antes."""
    current = None
    for rate in rates:
        if rate.from_date > day:
            break
        current = rate
    return current


def last_yield_date(session: Session, user_id: int, account_id: int) -> Optional[date_type]:
    return session.exec(select(func.max(FinTransaction.tx_date)).where(
        FinTransaction.user_id == user_id, FinTransaction.account_id == account_id,
        FinTransaction.source == YIELD_SOURCE)).one()


def _daily_moves(session: Session, user_id: int, account: FinAccount, start: date_type,
                 end: date_type) -> Dict[date_type, int]:
    """Lo que entra (+) y sale (−) de la cuenta cada día del rango."""
    moves: Dict[date_type, int] = {}
    query = select(FinTransaction).where(
        FinTransaction.user_id == user_id, FinTransaction.tx_date >= start, FinTransaction.tx_date <= end,
        or_(FinTransaction.account_id == account.id, FinTransaction.to_account_id == account.id))
    if account.opening_date is not None:
        query = query.where(FinTransaction.tx_date >= account.opening_date)
    for tx in session.exec(query).all():
        delta = 0
        if tx.account_id == account.id:
            delta += tx.amount_cents if tx.kind == "income" else -tx.amount_cents
        if tx.kind == "transfer" and tx.to_account_id == account.id:
            delta += tx.amount_cents
        moves[tx.tx_date] = moves.get(tx.tx_date, 0) + delta
    return moves


def yield_estimate(session: Session, user_id: int, account: FinAccount, today: date_type,
                   rates: Optional[List[FinYieldRate]] = None) -> Optional[dict]:
    """El rendimiento sin anotar de una cuenta con tasa: desde cuándo (`since`),
    hasta cuándo (`through`, ayer) y cuánto (`estimate_cents`). None sin tasa."""
    rates = account_rates(session, user_id, account.id) if rates is None else rates
    if not rates:
        return None
    starts = [rates[0].from_date]
    if account.opening_date is not None:
        starts.append(account.opening_date)
    # Lo anotado un día cubre hasta el anterior (el banco paga cada día al terminar):
    # ese mismo día aún no está cubierto
    last = last_yield_date(session, user_id, account.id)
    if last is not None:
        starts.append(last)
    since = max(starts)
    through = today - timedelta(days=1)
    result = {"since": since, "through": through, "estimate_cents": 0}
    if through < since:
        return result
    balance = Decimal(account_balances(session, user_id, since - timedelta(days=1)).get(
        account.id, account.opening_balance_cents))
    moves = _daily_moves(session, user_id, account, since, through)
    earned = Decimal(0)
    day = since
    while day <= through:
        balance += moves.get(day, 0)
        rate = rate_on(rates, day)
        if rate is not None and rate.rate_bp > 0:
            base = balance + earned
            if rate.cap_cents is not None:
                base = min(base, Decimal(rate.cap_cents))
            if base > 0:
                earned += base * rate.rate_bp / Decimal(10_000) / rate.day_basis
        day += timedelta(days=1)
    result["estimate_cents"] = int(earned.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return result


def yield_category(session: Session, user_id: int) -> Optional[FinCategory]:
    """La categoría de ingreso "Rendimientos": la del usuario, o una nueva al
    final. None si ya tiene una de gastos con ese nombre (el nombre es único)."""
    name, color, kind, icon = YIELD_CATEGORY
    category = session.exec(select(FinCategory).where(FinCategory.user_id == user_id,
                                                      FinCategory.name == name)).first()
    if category is not None:
        return category if category.kind == kind else None
    last = session.exec(select(func.max(FinCategory.order)).where(FinCategory.user_id == user_id)).one()
    category = FinCategory(user_id=user_id, name=name, color=color, kind=kind, icon=icon, order=(last or 0) + 1)
    session.add(category)
    session.flush()
    return category
