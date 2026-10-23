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
from datetime import date as date_type, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import calendar

from backend.models import (FinAccount, FinCategory, FinInstallment, FinRecurring, FinSettings, FinSplit,
                            FinStatement, FinTransaction)
from backend.schemas import (FinAccountTotal, FinCategoryTotal, FinCurrencyTotal, FinStatementInstallment,
                             FinStatementResponse, FinSummaryResponse)
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


def _after_opening():
    """Que el movimiento cuente en el saldo de la cuenta unida: es del día de su
    saldo inicial o después (el saldo es al empezar ese día), o la cuenta no
    tiene ese día."""
    return or_(FinAccount.opening_date == None, FinTransaction.tx_date >= FinAccount.opening_date)  # noqa: E711


def account_balances(session: Session, user_id: int, today: date_type) -> Dict[int, int]:
    """El saldo de cada cuenta a hoy (o al día que se pida): su saldo inicial,
    más ingresos y transferencias que llegan, menos gastos y transferencias que
    salen. En una de crédito, negativo es lo que se debe. Lo de después no cuenta,
    ni lo de antes del día del saldo inicial (es historial)."""
    balances = dict(session.exec(select(FinAccount.id, FinAccount.opening_balance_cents)
                                 .where(FinAccount.user_id == user_id)).all())
    # Lo que sale o entra por la cuenta del movimiento, con el día de esa cuenta
    rows = session.exec(select(FinTransaction.kind, FinTransaction.account_id, func.sum(FinTransaction.amount_cents))
                        .join(FinAccount, FinAccount.id == FinTransaction.account_id)
                        .where(FinTransaction.user_id == user_id, FinTransaction.tx_date <= today, _after_opening())
                        .group_by(FinTransaction.kind, FinTransaction.account_id)).all()
    for kind, account_id, cents in rows:
        balances[account_id] = balances.get(account_id, 0) + (cents if kind == "income" else -cents)
    # Lo que llega por transferencia, con el día de la cuenta que recibe
    arrivals = session.exec(select(FinTransaction.to_account_id, func.sum(FinTransaction.amount_cents))
                            .join(FinAccount, FinAccount.id == FinTransaction.to_account_id)
                            .where(FinTransaction.user_id == user_id, FinTransaction.kind == "transfer",
                                   FinTransaction.tx_date <= today, _after_opening())
                            .group_by(FinTransaction.to_account_id)).all()
    for account_id, cents in arrivals:
        balances[account_id] = balances.get(account_id, 0) + cents
    return balances


def history_before_opening(session: Session, user_id: int) -> Dict[int, tuple]:
    """Por cuenta con día de saldo inicial: (cuántos, lo que entró, lo que salió)
    antes de ese día. Son historial: no mueven el saldo."""
    accounts = {a.id: a.opening_date for a in session.exec(select(FinAccount).where(
        FinAccount.user_id == user_id, FinAccount.opening_date != None)).all()}  # noqa: E711
    if not accounts:
        return {}
    out: Dict[int, list] = {}
    for tx in session.exec(select(FinTransaction).where(
            FinTransaction.user_id == user_id,
            or_(FinTransaction.account_id.in_(accounts), FinTransaction.to_account_id.in_(accounts)))).all():
        if tx.account_id in accounts and tx.tx_date < accounts[tx.account_id]:
            row = out.setdefault(tx.account_id, [0, 0, 0])
            row[0] += 1
            row[1 if tx.kind == "income" else 2] += tx.amount_cents
        if tx.kind == "transfer" and tx.to_account_id in accounts and tx.tx_date < accounts[tx.to_account_id]:
            row = out.setdefault(tx.to_account_id, [0, 0, 0])
            row[0] += 1
            row[1] += tx.amount_cents
    return {k: tuple(v) for k, v in out.items()}


# ==================== Tarjetas de crédito: cortes y MSI ====================

def _clamp(year: int, month: int, day: int) -> date_type:
    """El día `day` de ese mes, o el último si el mes es más corto."""
    return date_type(year, month, min(day, calendar.monthrange(year, month)[1]))


def _shift(day: date_type, months: int) -> tuple:
    index = day.year * 12 + day.month - 1 + months
    return index // 12, index % 12 + 1


def shift_cut(cut: date_type, months: int, statement_day: int) -> date_type:
    """El corte `months` meses antes (negativo) o después de `cut`."""
    return _clamp(*_shift(cut, months), statement_day)


def cut_on_or_before(statement_day: int, day: date_type) -> date_type:
    """El corte más reciente en o antes de `day`."""
    cut = _clamp(day.year, day.month, statement_day)
    return cut if cut <= day else _clamp(*_shift(day, -1), statement_day)


def cut_on_or_after(statement_day: int, day: date_type) -> date_type:
    """El primer corte en o después de `day` (el que factura una compra de ese día)."""
    cut = _clamp(day.year, day.month, statement_day)
    return cut if cut >= day else _clamp(*_shift(day, 1), statement_day)


def due_after(cut: date_type, due_day: int) -> date_type:
    """La fecha límite de pago de un corte: el primer día de pago después de él."""
    due = _clamp(cut.year, cut.month, due_day)
    return due if due > cut else _clamp(*_shift(cut, 1), due_day)


def installment_parts(total_cents: int, months: int) -> List[int]:
    """El total en partes que suman exacto: los centavos que sobran, uno a cada
    una de las últimas (como los estados de cuenta: 6 × 270.53 y el resto al final)."""
    base, extra = divmod(total_cents, months)
    return [base + (1 if i >= months - extra else 0) for i in range(months)]


def installment_bills(inst: FinInstallment, statement_day: Optional[int]) -> List[tuple]:
    """(fecha del corte, centavos) de cada mensualidad, en orden."""
    day = statement_day or inst.first_statement.day
    return [(_clamp(*_shift(inst.first_statement, k), day), cents)
            for k, cents in enumerate(installment_parts(inst.total_cents, inst.months))]


def _balance_until(session: Session, account: FinAccount, until: date_type) -> int:
    return account_balances(session, account.user_id, until).get(account.id, account.opening_balance_cents)


def _msi_at(session: Session, account: FinAccount, cut: date_type, known_by: date_type) -> tuple:
    """(lo que de los planes de meses aún no se factura después de `cut`, las
    mensualidades que factura `cut`). Solo los planes con compra hasta `known_by`."""
    pending = 0
    billed: List[FinStatementInstallment] = []
    for inst in session.exec(select(FinInstallment).where(
            FinInstallment.user_id == account.user_id, FinInstallment.account_id == account.id)).all():
        if inst.purchase_date > known_by:
            continue
        for k, (bill, cents) in enumerate(installment_bills(inst, account.statement_day)):
            if bill > cut:
                pending += cents
            elif bill == cut:
                billed.append(FinStatementInstallment(id=inst.id, concept=inst.concept, part=k + 1,
                                                      months=inst.months, amount_cents=cents))
    return pending, sorted(billed, key=lambda i: i.concept)


def _movements_between(session: Session, account: FinAccount, after: date_type, until: date_type) -> tuple:
    """(abonos, cargos) de la tarjeta después de `after` y hasta `until`."""
    paid = charges = 0
    for tx in session.exec(select(FinTransaction).where(
            FinTransaction.user_id == account.user_id, FinTransaction.tx_date > after, FinTransaction.tx_date <= until,
            or_(FinTransaction.account_id == account.id, FinTransaction.to_account_id == account.id))).all():
        if tx.kind == "transfer" and tx.to_account_id == account.id:
            paid += tx.amount_cents
        elif tx.kind == "income" and tx.account_id == account.id:
            paid += tx.amount_cents
        elif tx.kind in ("expense", "transfer") and tx.account_id == account.id:
            charges += tx.amount_cents
    return paid, charges


def card_statement(session: Session, account: FinAccount, today: date_type) -> FinStatementResponse:
    """El estado de cuenta calculado de una tarjeta con día de corte y de pago.
    Pagar para no generar intereses = lo que se debía al último corte, menos las
    mensualidades de MSI que aún no se facturan (la compra entró completa), menos
    lo que ya se abonó desde el corte.

    Si el pago de ese corte ya venció, enseña el PRÓXIMO corte con lo que lleva
    acumulado hasta hoy (`upcoming`). Una tarjeta dada de alta después del corte,
    con el pago aún por venir, enseña ese corte: su deuda de entonces se toma de la
    inicial (lo que se debía al darla de alta), y el banco la corrige."""
    day, opening = account.statement_day, account.opening_date
    last_cut = cut_on_or_before(day, today)
    due = due_after(last_cut, account.due_day)
    if today > due:
        cut = cut_on_or_after(day, today + timedelta(days=1))
        debt = max(0, -_balance_until(session, account, today))
        pending, billed = _msi_at(session, account, cut, today)
        since = last_cut if opening is None else max(last_cut, opening - timedelta(days=1))
        _, charges = _movements_between(session, account, since, today)
        pay = max(0, debt - pending)
        return FinStatementResponse(
            account_id=account.id, currency=account.currency, statement_day=day, due_day=account.due_day,
            last_cut=cut, prev_cut=last_cut, due_date=due_after(cut, account.due_day),
            next_cut=cut_on_or_after(day, cut + timedelta(days=1)), debt_at_cut_cents=debt,
            msi_pending_cents=pending, pay_no_interest_cents=pay, paid_since_cut_cents=0, remaining_cents=pay,
            cycle_charges_cents=charges, installments=billed, upcoming=True, estimated_cents=pay,
        )
    prev_cut = cut_on_or_before(day, last_cut - timedelta(days=1))
    next_cut = cut_on_or_after(day, last_cut + timedelta(days=1))
    debt = max(0, -_balance_until(session, account, last_cut))
    # Dada de alta después del corte: los meses que le quedan a su deuda (planes
    # anotados después) salen de la deuda inicial, aunque se anotaran hoy
    known_by = today if opening is not None and opening > last_cut else last_cut
    pending, billed = _msi_at(session, account, last_cut, known_by)
    paid, charges = _movements_between(session, account, last_cut, today)
    estimated = max(0, debt - pending)
    # Si el usuario escribió lo que pide su estado de cuenta, eso manda en este corte
    bank = bank_statement(session, account, last_cut)
    pay = bank.pay_no_interest_cents if bank else estimated
    return FinStatementResponse(
        account_id=account.id, currency=account.currency, statement_day=day, due_day=account.due_day,
        last_cut=last_cut, prev_cut=prev_cut, due_date=due, next_cut=next_cut, debt_at_cut_cents=debt,
        msi_pending_cents=pending, pay_no_interest_cents=pay, paid_since_cut_cents=paid,
        remaining_cents=max(0, pay - paid), cycle_charges_cents=charges, installments=billed,
        from_bank=bank is not None, estimated_cents=estimated,
    )


def bank_statement(session: Session, account: FinAccount, cut: date_type) -> Optional[FinStatement]:
    """Lo que el usuario escribió del estado de cuenta de ese corte, si lo hizo."""
    return session.exec(select(FinStatement).where(FinStatement.user_id == account.user_id,
                                                   FinStatement.account_id == account.id,
                                                   FinStatement.cut_date == cut)).first()


def splits_by_transaction(session: Session, user_id: int, tx_ids: List[int]) -> Dict[int, List[FinSplit]]:
    """Las partes de esos movimientos, en su orden."""
    if not tx_ids:
        return {}
    out: Dict[int, List[FinSplit]] = {}
    for split in session.exec(select(FinSplit).where(FinSplit.user_id == user_id, FinSplit.transaction_id.in_(tx_ids))
                              .order_by(FinSplit.order, FinSplit.id)).all():
        out.setdefault(split.transaction_id, []).append(split)
    return out


def account_currencies(session: Session, user_id: int) -> Dict[int, str]:
    return dict(session.exec(select(FinAccount.id, FinAccount.currency).where(FinAccount.user_id == user_id)).all())


def first_transaction_date(session: Session, user_id: int) -> Optional[date_type]:
    return session.exec(select(func.min(FinTransaction.tx_date)).where(FinTransaction.user_id == user_id)).one()


def summary(session: Session, user_id: int, day: date_type,
            bounds: Optional[tuple] = None) -> FinSummaryResponse:
    """El resumen del periodo que contiene `day`, o de las fechas `bounds`
    (desde, hasta) que pidió la pantalla: un día, una semana, un año, un rango."""
    row = settings_row(session, user_id)
    period = row.period if row and row.period else "month"
    date_from, date_to = bounds or period_bounds(period, day)
    accounts = session.exec(select(FinAccount).where(FinAccount.user_id == user_id)
                            .order_by(FinAccount.order, FinAccount.id)).all()
    categories = {c.id: c for c in session.exec(select(FinCategory).where(FinCategory.user_id == user_id)).all()}
    rows = session.exec(select(FinTransaction).where(
        FinTransaction.user_id == user_id, FinTransaction.tx_date >= date_from, FinTransaction.tx_date <= date_to)).all()

    splits = splits_by_transaction(session, user_id, [tx.id for tx in rows])
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
        # Un movimiento dividido cuenta cada parte en su categoría
        for category_id, cents in ([(s.category_id, s.amount_cents) for s in splits[tx.id]] if tx.id in splits
                                   else [(tx.category_id, tx.amount_cents)]):
            key = (category_id, account.currency)
            by_category[key] = by_category.get(key, 0) + cents

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
    fecha local del usuario) y los vencimientos de los plazos fijos.
    Idempotente. Hace commit si generó algo."""
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
    # Los plazos fijos que vencieron (importado aquí: finance_yield importa este módulo)
    from backend.finance_yield import mature_terms
    created += mature_terms(session, user_id, today)
    if created or session.dirty or session.new:
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
