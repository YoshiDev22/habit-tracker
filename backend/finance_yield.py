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
from backend.models import FinAccount, FinCategory, FinTerm, FinTransaction, FinYieldRate

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
    """El día del último rendimiento diario anotado. Los de un plazo fijo llevan
    external_id y no cuentan: son otro rendimiento."""
    return session.exec(select(func.max(FinTransaction.tx_date)).where(
        FinTransaction.user_id == user_id, FinTransaction.account_id == account_id,
        FinTransaction.source == YIELD_SOURCE, FinTransaction.kind == "income",
        FinTransaction.external_id == None)).one()  # noqa: E711


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


# ==================== A plazo fijo ====================

# Vencimientos que se ponen al día de una vez (un plazo que se reinvierte desde hace mucho)
MAX_TERM_CATCH_UP = 120


def term_maturity(term: FinTerm) -> date_type:
    return term.start_date + timedelta(days=term.days)


def term_interest(principal_cents: int, rate_bp: int, days: int, day_basis: int) -> int:
    """Rendimiento simple del plazo, con .5 hacia arriba."""
    value = Decimal(principal_cents) * rate_bp * days / (Decimal(10_000) * day_basis)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def mature_terms(session: Session, user_id: int, today: date_type) -> List[FinTransaction]:
    """Anota los plazos que vencieron hasta hoy (sin commit; lo hace quien
    llama): el rendimiento como ingreso en su cuenta y, según el plazo, la
    transferencia de regreso o el plazo nuevo. El external_id frena que dos
    peticiones a la vez lo anoten dos veces (la segunda choca con el índice)."""
    created: List[FinTransaction] = []
    pending = session.exec(select(FinTerm).where(FinTerm.user_id == user_id, FinTerm.matured == False)  # noqa: E712
                           .order_by(FinTerm.id)).all()
    category = None
    for _ in range(MAX_TERM_CATCH_UP):
        due = [t for t in pending if not t.matured and term_maturity(t) <= today]
        if not due:
            break
        for term in due:
            if category is None:
                category = income_category(session, user_id)
            maturity = term_maturity(term)
            interest = term_interest(term.principal_cents, term.rate_bp, term.days, term.day_basis)
            if interest > 0 and category is not None:
                tx = FinTransaction(user_id=user_id, account_id=term.account_id, kind="income", amount_cents=interest,
                                    tx_date=maturity, category_id=category.id,
                                    concept=f"Rendimiento: {term.concept}"[:200], source=YIELD_SOURCE,
                                    external_id=f"term-{term.id}")
                session.add(tx)
                created.append(tx)
            total = term.principal_cents + interest
            if term.on_maturity == "return" and term.return_account_id is not None:
                back = FinTransaction(user_id=user_id, account_id=term.account_id, kind="transfer", amount_cents=total,
                                      tx_date=maturity, to_account_id=term.return_account_id,
                                      concept=f"Vencimiento: {term.concept}"[:200], source=YIELD_SOURCE,
                                      external_id=f"term-{term.id}-return")
                session.add(back)
                created.append(back)
            elif term.on_maturity == "renew":
                renewed = FinTerm(user_id=user_id, account_id=term.account_id, concept=term.concept,
                                  principal_cents=total, start_date=maturity, days=term.days, rate_bp=term.rate_bp,
                                  day_basis=term.day_basis, on_maturity="renew")
                session.add(renewed)
                session.flush()
                pending.append(renewed)
            term.matured = True
            session.add(term)
    return created


def income_category(session: Session, user_id: int) -> Optional[FinCategory]:
    """Dónde va un rendimiento: "Rendimientos" o, si ese nombre ya es de una
    categoría de gastos, la primera de ingresos."""
    return yield_category(session, user_id) or session.exec(select(FinCategory).where(
        FinCategory.user_id == user_id, FinCategory.kind == "income").order_by(FinCategory.order)).first()


def open_terms_by_account(session: Session, user_id: int) -> Dict[int, List[FinTerm]]:
    out: Dict[int, List[FinTerm]] = {}
    for term in session.exec(select(FinTerm).where(FinTerm.user_id == user_id, FinTerm.matured == False)).all():  # noqa: E712
        out.setdefault(term.account_id, []).append(term)
    return out


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
