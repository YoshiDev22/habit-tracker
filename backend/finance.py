"""
Finanzas personales (épica 37, docs/specs/finanzas.md): lo que no es una ruta.

- Lo de inicio, perezoso como las categorías de Costos: la cuenta "Efectivo" y
  las categorías, la primera vez que se entra.
- El periodo (mes o quincena, lo que contestó el usuario) y sus fechas, con
  backend/series.py.
- El resumen de un periodo: gasto e ingreso por categoría, lo que se movió en
  cada cuenta y los totales por moneda. Una transferencia nunca es gasto: así
  la compra con crédito cuenta una vez y el pago de la tarjeta, ninguna.
- generate_due(): los cobros de los fijos que ya llegaron, como en Costos.

Todo en centavos enteros; ninguna suma mezcla monedas.
"""
from datetime import date as date_type
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.models import FinAccount, FinCategory, FinRecurring, FinSettings, FinTransaction
from backend.schemas import (FinAccountTotal, FinCategoryTotal, FinCurrencyTotal, FinSummaryResponse)
from backend.series import adjacent_period, next_date, period_bounds

DEFAULT_ACCOUNTS = [("Efectivo", "cash", "banknote", "#16a085")]
DEFAULT_CATEGORIES = [
    ("Súper", "#27ae60", "expense", "shopping-basket"),
    ("Comer fuera", "#e67e22", "expense", "utensils"),
    ("Transporte", "#3498db", "expense", "bus"),
    ("Casa y servicios", "#8d6e63", "expense", "house"),
    ("Suscripciones", "#9b59b6", "expense", "tv"),
    ("Salud", "#e74c3c", "expense", "heart-pulse"),
    ("Personal", "#e84393", "expense", "shirt"),
    ("Ocio", "#f1c40f", "expense", "ticket"),
    ("Otros", "#95a5a6", "expense", "ellipsis"),
    ("Sueldo", "#00b894", "income", "briefcase"),
    ("Otros ingresos", "#1abc9c", "income", "hand-coins"),
]
# Cobros que se ponen al día de una vez (un fijo que empezó hace mucho)
MAX_CATCH_UP = 36


def ensure_finance_setup(session: Session, user_id: int) -> None:
    """La cuenta y las categorías de inicio, una sola vez cada una: sin ninguna,
    la cuenta nunca entró (la última no se puede borrar). Idempotente. La
    pantalla pide cuentas y resumen a la vez, así que dos peticiones siembran
    juntas: la restricción única por nombre frena la segunda, y cada siembra va
    en su propio commit para que el choque de una no se lleve la otra."""
    if session.exec(select(FinAccount.id).where(FinAccount.user_id == user_id)).first() is None:
        _seed(session, [FinAccount(user_id=user_id, name=name, kind=kind, icon=icon, color=color, order=order,
                                   is_default=order == 0)
                        for order, (name, kind, icon, color) in enumerate(DEFAULT_ACCOUNTS)])
    if session.exec(select(FinCategory.id).where(FinCategory.user_id == user_id)).first() is None:
        _seed(session, [FinCategory(user_id=user_id, name=name, color=color, kind=kind, icon=icon, order=order)
                        for order, (name, color, kind, icon) in enumerate(DEFAULT_CATEGORIES)])


def _seed(session: Session, rows: list) -> None:
    for row in rows:
        session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()   # otra petición sembró lo mismo a la vez


def settings_row(session: Session, user_id: int) -> Optional[FinSettings]:
    return session.exec(select(FinSettings).where(FinSettings.user_id == user_id)).first()


def user_period(session: Session, user_id: int) -> str:
    """month | biweekly. Sin respuesta todavía, el mes."""
    row = settings_row(session, user_id)
    return row.period if row and row.period else "month"


def account_balances(session: Session, user_id: int, today: date_type) -> Dict[int, int]:
    """El saldo de cada cuenta a hoy: su saldo inicial, más ingresos y
    transferencias que llegan, menos gastos y transferencias que salen. En una
    de crédito, negativo es lo que se debe. Lo de después de hoy no cuenta."""
    balances = dict(session.exec(select(FinAccount.id, FinAccount.opening_balance_cents)
                                 .where(FinAccount.user_id == user_id)).all())
    rows = session.exec(select(FinTransaction.kind, FinTransaction.account_id, FinTransaction.to_account_id,
                               func.sum(FinTransaction.amount_cents))
                        .where(FinTransaction.user_id == user_id, FinTransaction.tx_date <= today)
                        .group_by(FinTransaction.kind, FinTransaction.account_id, FinTransaction.to_account_id)).all()
    for kind, account_id, to_account_id, cents in rows:
        if kind == "income":
            balances[account_id] = balances.get(account_id, 0) + cents
        else:
            balances[account_id] = balances.get(account_id, 0) - cents
            if kind == "transfer" and to_account_id is not None:
                balances[to_account_id] = balances.get(to_account_id, 0) + cents
    return balances


def account_currencies(session: Session, user_id: int) -> Dict[int, str]:
    return dict(session.exec(select(FinAccount.id, FinAccount.currency).where(FinAccount.user_id == user_id)).all())


def summary(session: Session, user_id: int, day: date_type) -> FinSummaryResponse:
    """El resumen del periodo que contiene `day`."""
    row = settings_row(session, user_id)
    period = row.period if row and row.period else "month"
    date_from, date_to = period_bounds(period, day)
    accounts = session.exec(select(FinAccount).where(FinAccount.user_id == user_id)
                            .order_by(FinAccount.order, FinAccount.id)).all()
    categories = {c.id: c for c in session.exec(select(FinCategory).where(FinCategory.user_id == user_id)).all()}
    rows = session.exec(select(FinTransaction).where(
        FinTransaction.user_id == user_id, FinTransaction.tx_date >= date_from, FinTransaction.tx_date <= date_to)).all()

    by_account = {a.id: FinAccountTotal(account_id=a.id, name=a.name, kind=a.kind, currency=a.currency)
                  for a in accounts}
    by_category: Dict[tuple, int] = {}
    totals: Dict[str, FinCurrencyTotal] = {}
    for tx in rows:
        account = by_account.get(tx.account_id)
        if account is None:
            continue
        if tx.kind == "transfer":
            account.transfer_out_cents += tx.amount_cents
            target = by_account.get(tx.to_account_id)
            if target is not None:
                target.transfer_in_cents += tx.amount_cents
            continue
        total = totals.setdefault(account.currency, FinCurrencyTotal(currency=account.currency))
        if tx.kind == "expense":
            account.expense_cents += tx.amount_cents
            total.expense_cents += tx.amount_cents
        else:
            account.income_cents += tx.amount_cents
            total.income_cents += tx.amount_cents
        key = (tx.category_id, account.currency)
        by_category[key] = by_category.get(key, 0) + tx.amount_cents

    for account in by_account.values():
        account.net_cents = (account.income_cents + account.transfer_in_cents
                             - account.expense_cents - account.transfer_out_cents)
    for total in totals.values():
        total.net_cents = total.income_cents - total.expense_cents
    active = {a.id for a in accounts if a.is_active}
    moved = [a for a in by_account.values()
             if a.account_id in active or a.expense_cents or a.income_cents or a.transfer_in_cents or a.transfer_out_cents]

    return FinSummaryResponse(
        period=period,
        period_asked=bool(row and row.period),
        date_from=date_from,
        date_to=date_to,
        prev_day=adjacent_period(period, day, -1)[0],
        next_day=adjacent_period(period, day, 1)[0],
        transactions=len(rows),
        needs_review=sum(1 for tx in rows if tx.needs_review),
        categories=sorted(
            (FinCategoryTotal(category_id=cid, name=categories[cid].name, color=categories[cid].color,
                              kind=categories[cid].kind, currency=currency, cents=cents)
             for (cid, currency), cents in by_category.items() if cid in categories),
            key=lambda c: (c.kind, c.currency, -c.cents, c.name),
        ),
        accounts=moved,
        totals=sorted(totals.values(), key=lambda t: t.currency),
    )


def generate_due(session: Session, user_id: int, today: date_type) -> List[FinTransaction]:
    """Convierte en movimientos los cobros de los fijos que ya llegaron (en la
    fecha local del usuario). Idempotente. Hace commit si generó algo."""
    created: List[FinTransaction] = []
    for rc in session.exec(select(FinRecurring).where(
            FinRecurring.user_id == user_id, FinRecurring.paused == False)).all():  # noqa: E712
        for _ in range(MAX_CATCH_UP):
            due = next_date(rc)
            if due is None or due > today:
                break
            # Ya hay un movimiento suyo en esa fecha: cuenta como ese cobro.
            # Generarlo chocaría con el índice único y el fijo se atascaría.
            if session.exec(select(FinTransaction.id).where(
                    FinTransaction.user_id == user_id, FinTransaction.recurring_id == rc.id,
                    FinTransaction.tx_date == due).limit(1)).first() is None:
                tx = FinTransaction(user_id=user_id, account_id=rc.account_id, kind=rc.kind,
                                    amount_cents=rc.amount_cents, tx_date=due, category_id=rc.category_id,
                                    concept=rc.concept, note=rc.note, source="recurring", recurring_id=rc.id)
                session.add(tx)
                created.append(tx)
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


def last_charge(session: Session, rc: FinRecurring) -> Optional[date_type]:
    """La fecha del último movimiento anotado por este fijo (None si ninguno)."""
    return session.exec(select(func.max(FinTransaction.tx_date)).where(
        FinTransaction.user_id == rc.user_id, FinTransaction.recurring_id == rc.id)).one()
