"""
Finanzas: préstamos (Finanzas 0.9, BACKLOG 52).

Un préstamo es una cuenta `kind = "loan"`: lo que se debe es su saldo inicial en
negativo (como la deuda inicial de una tarjeta), que nunca es gasto. Cada pago es
**un solo movimiento**: una transferencia de la cuenta que paga al préstamo, que
lleva en `interest_cents` lo que no baja la deuda (intereses, IVA, seguros). Así:

- La cuenta que paga baja el pago completo; la deuda, solo el capital
  (`account_balances()` resta los intereses de lo que le llega).
- Los intereses son gasto en "Intereses" (`interest_category_id`), y el capital
  también es gasto, en `category_id`, solo si lo comprado con el préstamo no estaba
  anotado (`loan_category_id` de la cuenta). Lo cuenta `summary()`: un mismo peso
  nunca cuenta dos veces.

La tabla de amortización (`fin_loan_rows`) es de referencia: propone el siguiente
pago y dice hasta cuándo. Sin ella, el interés se estima con la tasa.
"""
import math
from datetime import date as date_type, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from sqlmodel import Session, select
from sqlalchemy import func

from backend.finance import account_balances, _clamp, _shift
from backend.models import FinAccount, FinCategory, FinLoanRow, FinSettings, FinTransaction
from backend.schemas import FinLoanPayment, FinLoanResponse, FinLoanRowResponse

INTEREST_CATEGORY = ("Intereses", "#c0392b", "expense", "landmark")
# Una fila de la tabla cuenta como pagada con una mensualidad hecha desde un mes antes de su fecha
TABLE_LEAD_DAYS = 31


def interest_category(session: Session, user_id: int) -> Optional[FinCategory]:
    """La categoría de gasto "Intereses": la del usuario, o una nueva al final.
    None si ya tiene una de ingresos con ese nombre (el nombre es único)."""
    name, color, kind, icon = INTEREST_CATEGORY
    category = session.exec(select(FinCategory).where(FinCategory.user_id == user_id,
                                                      FinCategory.name == name)).first()
    if category is not None:
        return category if category.kind == kind else None
    last = session.exec(select(func.max(FinCategory.order)).where(FinCategory.user_id == user_id)).one()
    category = FinCategory(user_id=user_id, name=name, color=color, kind=kind, icon=icon, order=(last or 0) + 1)
    session.add(category)
    session.flush()
    return category


def monthly_interest(owed_cents: int, rate_bp: Optional[int]) -> Optional[int]:
    """El interés de un mes sobre lo que se debe: tasa anual ÷ 12, con .5 hacia arriba."""
    if not rate_bp or owed_cents <= 0:
        return None
    value = Decimal(owed_cents) * Decimal(rate_bp) / Decimal(10000 * 12)
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def months_left(owed_cents: int, payment_cents: Optional[int], rate_bp: Optional[int]) -> Optional[int]:
    """Cuántas mensualidades faltan con ese pago (amortización francesa con la tasa;
    sin tasa, lo que se debe ÷ el pago). None si el pago no alcanza ni el interés."""
    if not payment_cents or owed_cents <= 0:
        return None
    if not rate_bp:
        return math.ceil(owed_cents / payment_cents)
    rate = rate_bp / 10000 / 12
    if payment_cents <= owed_cents * rate:
        return None
    return math.ceil(-math.log(1 - rate * owed_cents / payment_cents) / math.log(1 + rate))


def next_due(due_day: Optional[int], today: date_type) -> Optional[date_type]:
    """El siguiente día de pago, hoy incluido (el que el mes no tiene cae en el último)."""
    if not due_day:
        return None
    day = _clamp(today.year, today.month, due_day)
    return day if day >= today else _clamp(*_shift(day, 1), due_day)


def loan_rows(session: Session, user_id: int, account_id: int) -> List[FinLoanRow]:
    return session.exec(select(FinLoanRow).where(FinLoanRow.user_id == user_id, FinLoanRow.account_id == account_id)
                        .order_by(FinLoanRow.number, FinLoanRow.due_date)).all()


def capital_note_hidden(session: Session, user_id: int) -> bool:
    row = session.exec(select(FinSettings).where(FinSettings.user_id == user_id)).first()
    return bool(row and row.capital_note_hidden)


def loan_response(session: Session, account: FinAccount, today: date_type) -> FinLoanResponse:
    """Lo que se debe, lo pagado (capital e intereses), los pagos y la tabla."""
    user_id = account.user_id
    owed = -account_balances(session, user_id, today).get(account.id, account.opening_balance_cents)
    txs = session.exec(select(FinTransaction).where(
        FinTransaction.user_id == user_id, FinTransaction.kind == "transfer",
        FinTransaction.to_account_id == account.id).order_by(FinTransaction.tx_date.desc(), FinTransaction.id.desc())).all()
    payments = [FinLoanPayment(id=tx.id, tx_date=tx.tx_date, account_id=tx.account_id, amount_cents=tx.amount_cents,
                               principal_cents=tx.amount_cents - (tx.interest_cents or 0),
                               interest_cents=tx.interest_cents or 0, principal_only=tx.principal_only)
                for tx in txs]
    regular = [p for p in payments if not p.principal_only]
    rows = loan_rows(session, user_id, account.id)
    response = FinLoanResponse(
        account_id=account.id, currency=account.currency, owed_cents=owed, opening_cents=-account.opening_balance_cents,
        paid_cents=sum(p.amount_cents for p in payments),
        paid_principal_cents=sum(p.principal_cents for p in payments),
        paid_interest_cents=sum(p.interest_cents for p in payments),
        regular_count=len(regular), capital_count=len(payments) - len(regular),
        last_payment=payments[0].tx_date if payments else None,
        payments=payments, capital_note_hidden=capital_note_hidden(session, user_id),
    )
    if rows:
        # Cada mensualidad hecha desde poco antes de la primera fila cubre una fila, en orden
        start = rows[0].due_date - timedelta(days=TABLE_LEAD_DAYS)
        covered = sum(1 for p in regular if p.tx_date >= start)
        response.rows = [FinLoanRowResponse(number=r.number, due_date=r.due_date, payment_cents=r.payment_cents,
                                            principal_cents=r.principal_cents, interest_cents=r.interest_cents,
                                            balance_cents=r.balance_cents, paid=i < covered)
                         for i, r in enumerate(rows)]
        response.ends_on = rows[-1].due_date
        if covered < len(rows) and owed > 0:
            row = rows[covered]
            response.next_payment_cents = row.payment_cents
            response.next_interest_cents = row.interest_cents
            response.next_due = row.due_date
            response.next_number = row.number
            response.from_table = True
        return response
    if owed > 0:
        response.next_payment_cents = account.loan_payment_cents
        response.next_interest_cents = monthly_interest(owed, account.interest_rate_bp)
        response.next_due = next_due(account.due_day, today)
        left = months_left(owed, account.loan_payment_cents, account.interest_rate_bp)
        if left and response.next_due:
            response.ends_on = _clamp(*_shift(response.next_due, left - 1), account.due_day or response.next_due.day)
    return response
