"""
Finanzas: el plan de pagos de un mes (Finanzas 0.9).

Lo que hay que pagar y lo que entra, por fecha, para saber si alcanza: el pago de
cada tarjeta (el del banco, el calculado o, si su corte aún no llega, un estimado),
la mensualidad de cada préstamo, los fijos y los aproximados del presupuesto que el
usuario elige. Se calcula al pedirlo y **no guarda nada** salvo esas elecciones
(`fin_plan_choices`); nunca crea movimientos ni cambia el presupuesto.

Para que nada cuente dos veces:
- un fijo que se cobra a una tarjeta va dentro del pago de esa tarjeta, no suelto;
- un fijo anotado en un préstamo (un cargo) sube la deuda: no es dinero que sale;
- un renglón del presupuesto que es fijo sale una vez, como fijo.

El punto de partida es el saldo de hoy en efectivo y débito (sin apartados ni
inversiones); el del mes siguiente, ese saldo más lo que aún falta del mes en curso.
"""
from datetime import date as date_type, timedelta
from typing import Dict, Iterator, List, Optional, Tuple

from sqlmodel import Session, select

from backend.finance import (_clamp, _movements_between, _msi_at, account_balances, bank_statement, card_statement,
                             cut_on_or_after, due_after, settings_row, summary)
from backend.finance_loans import loan_rows
from backend.models import FinAccount, FinBudgetItem, FinPlanChoice, FinRecurring, FinTransaction
from backend.schemas import FinPlanEntry, FinPlanResponse, FinPlanStart
from backend.series import _last_day, occurrence, semimonthly_days

# Cuentas cuyo dinero está disponible para pagar (sin apartados: son dinero ya reservado)
CASH_KINDS = ("cash", "debit")
# Tope de cobros por recorrer de un fijo: un quincenal da dos al mes
MAX_OCCURRENCES = 400


def month_bounds(day: date_type) -> Tuple[date_type, date_type]:
    return day.replace(day=1), day.replace(day=_last_day(day.year, day.month))


def next_month(day: date_type) -> date_type:
    return month_bounds(day)[1] + timedelta(days=1)


def main_currency(accounts: List[FinAccount]) -> str:
    """La de la cuenta principal, o la de la primera activa (como finMainCurrency())."""
    active = [a for a in accounts if a.is_active]
    default = next((a for a in active if a.is_default), None) or (active[0] if active else None)
    return default.currency if default else "MXN"


def future_dates(rc: FinRecurring, after: date_type, until: date_type) -> Iterator[date_type]:
    """Los cobros de un fijo después de `after` y hasta `until` (los ya anotados no:
    generate_due() corrió antes, así que el siguiente es el número `generated`)."""
    if rc.paused:
        return
    days = semimonthly_days(rc)
    for n in range(rc.generated, rc.generated + MAX_OCCURRENCES):
        d = occurrence(rc.start_date, rc.frequency, n, days)
        if (rc.end_date is not None and d > rc.end_date) or d > until:
            return
        if d > after:
            yield d


def _card_entries(session: Session, account: FinAccount, recurring: List[FinRecurring],
                  today: date_type, date_from: date_type, date_to: date_type) -> List[FinPlanEntry]:
    """Los pagos de una tarjeta con fecha límite en el mes. Los cortes que aún no
    llegan se estiman en orden: lo que se debe hoy, más sus fijos hasta el corte,
    menos los MSI que se facturan después y lo que ya pide un corte anterior."""
    if not (account.statement_day and account.due_day):
        return []
    day = account.statement_day
    statement = card_statement(session, account, today)
    out: List[FinPlanEntry] = []

    def entry(cut, due, amount, pending, status, source, msi=0):
        if date_from <= due <= date_to and (amount or pending):
            out.append(FinPlanEntry(kind="card", direction="out", ref_id=account.id, name=account.name,
                                    currency=account.currency, tx_date=due, amount_cents=amount,
                                    pending_cents=pending, status=status, source=source, cut_date=cut,
                                    msi_cents=msi))

    if statement.upcoming:
        # El pago del corte anterior ya venció: lo que se abonó hasta su fecha límite
        prev_cut = statement.prev_cut
        prev_due = due_after(prev_cut, account.due_day)
        paid, _ = _movements_between(session, account, prev_cut, prev_due)
        bank = bank_statement(session, account, prev_cut)
        entry(prev_cut, prev_due, bank.pay_no_interest_cents if bank and not paid else paid, 0,
              "done" if paid else "past", "bank" if bank else "calculated")
        accounted, cut = 0, statement.last_cut
    else:
        pay, remaining = statement.pay_no_interest_cents, statement.remaining_cents
        status = "done" if pay and not remaining else "partial" if statement.paid_since_cut_cents else "pending"
        entry(statement.last_cut, statement.due_date, pay, remaining, status,
              "bank" if statement.from_bank else "calculated",
              sum(i.amount_cents for i in statement.installments))
        accounted, cut = remaining, statement.next_cut

    owed_today = -account_balances(session, account.user_id, today).get(account.id, account.opening_balance_cents)
    card_fixed = [rc for rc in recurring if rc.account_id == account.id and rc.kind == "expense"]
    for _ in range(4):
        due = due_after(cut, account.due_day)
        if due > date_to:
            break
        charges = sum(rc.amount_cents for rc in card_fixed for _d in future_dates(rc, today, cut))
        pending_msi, billed = _msi_at(session, account, cut, today)
        estimate = max(0, owed_today + charges - pending_msi - accounted)
        accounted += estimate
        entry(cut, due, estimate, estimate, "pending", "estimated", sum(i.amount_cents for i in billed))
        cut = cut_on_or_after(day, cut + timedelta(days=1))
    return out


def _loan_entry(session: Session, account: FinAccount, today: date_type,
                date_from: date_type, date_to: date_type) -> Optional[FinPlanEntry]:
    """La mensualidad del mes: hecha si ya hay un pago (no abono a capital) en el mes;
    si no, la de su fila de la tabla o la mensualidad que se anotó."""
    paid = session.exec(select(FinTransaction).where(
        FinTransaction.user_id == account.user_id, FinTransaction.kind == "transfer",
        FinTransaction.to_account_id == account.id, FinTransaction.principal_only == False,  # noqa: E712
        FinTransaction.tx_date >= date_from, FinTransaction.tx_date <= date_to)).all()
    due = _clamp(date_from.year, date_from.month, account.due_day) if account.due_day else None
    base = dict(kind="loan", direction="out", ref_id=account.id, name=account.name, currency=account.currency)
    if paid:
        return FinPlanEntry(**base, tx_date=max(tx.tx_date for tx in paid),
                            amount_cents=sum(tx.amount_cents for tx in paid), pending_cents=0, status="done")
    owed = -account_balances(session, account.user_id, today).get(account.id, account.opening_balance_cents)
    if owed <= 0:
        return None
    row = next((r for r in loan_rows(session, account.user_id, account.id)
                if date_from <= r.due_date <= date_to), None)
    amount = row.payment_cents if row else account.loan_payment_cents
    if not amount:
        return None
    return FinPlanEntry(**base, tx_date=row.due_date if row else due, amount_cents=amount,
                        pending_cents=amount, status="pending",
                        source="table" if row else "payment")


def _fixed_entries(session: Session, user_id: int, recurring: List[FinRecurring], accounts: Dict[int, FinAccount],
                   today: date_type, date_from: date_type, date_to: date_type) -> List[FinPlanEntry]:
    """Los fijos que salen de (o entran a) efectivo, débito o una inversión: los
    anotados del mes, hechos; los que vienen, pendientes."""
    out: List[FinPlanEntry] = []
    by_id = {rc.id: rc for rc in recurring}

    def loose(account_id):
        account = accounts.get(account_id)
        return account if account is not None and account.kind not in ("credit", "loan") else None

    for tx in session.exec(select(FinTransaction).where(
            FinTransaction.user_id == user_id, FinTransaction.recurring_id.is_not(None),
            FinTransaction.tx_date >= date_from, FinTransaction.tx_date <= min(date_to, today))).all():
        account = loose(tx.account_id)
        if account is None or tx.kind not in ("expense", "income"):
            continue
        rc = by_id.get(tx.recurring_id)
        out.append(FinPlanEntry(kind="fixed", direction="out" if tx.kind == "expense" else "in",
                                ref_id=tx.recurring_id, name=rc.concept if rc else tx.concept or "",
                                currency=account.currency, tx_date=tx.tx_date, amount_cents=tx.amount_cents,
                                pending_cents=0, status="done", account_name=account.name))
    for rc in recurring:
        account = loose(rc.account_id)
        if account is None or not account.is_active:
            continue
        for d in future_dates(rc, max(today, date_from - timedelta(days=1)), date_to):
            out.append(FinPlanEntry(kind="fixed", direction="out" if rc.kind == "expense" else "in", ref_id=rc.id,
                                    name=rc.concept, currency=account.currency, tx_date=d,
                                    amount_cents=rc.amount_cents, pending_cents=rc.amount_cents, status="pending",
                                    account_name=account.name))
    return out


def _estimate_entries(session: Session, user_id: int, currency: str, month: date_type, current: bool,
                      today: date_type) -> List[FinPlanEntry]:
    """Los aproximados del presupuesto (sus gastos sin fijo), con lo que el usuario
    eligió para ese mes. Los ingresos no: el que llega con fecha es un fijo, y el
    ingreso del presupuesto suele ser ese mismo sueldo. En el mes en curso, lo que falta es el monto menos lo que ya
    lleva su categoría (si tiene)."""
    items = session.exec(select(FinBudgetItem).where(FinBudgetItem.user_id == user_id, FinBudgetItem.kind == "expense",
                                                     FinBudgetItem.recurring_id.is_(None))
                         .order_by(FinBudgetItem.order, FinBudgetItem.id)).all()
    if not items:
        return []
    choices = {c.item_id: c for c in session.exec(select(FinPlanChoice).where(
        FinPlanChoice.user_id == user_id, FinPlanChoice.month == month)).all()}
    spent: Dict[tuple, int] = {}
    if current:
        for c in summary(session, user_id, today, bounds=month_bounds(month)).categories:
            if c.currency == currency:
                spent[(c.category_id, c.kind)] = c.cents
    out = []
    for item in items:
        choice = choices.get(item.id)
        included = bool(choice and choice.included)
        amount = choice.amount_cents if choice and choice.amount_cents is not None else item.amount_cents
        done = spent.get((item.category_id, item.kind), 0) if item.category_id else 0
        left = max(0, amount - done)
        out.append(FinPlanEntry(kind="estimate", direction="out" if item.kind == "expense" else "in", ref_id=item.id,
                                name=item.name, currency=currency, amount_cents=amount,
                                pending_cents=left if included else 0,
                                status="done" if included and amount and not left else "pending",
                                included=included, budget_cents=item.amount_cents, spent_cents=done))
    return out


def _sort_key(e: FinPlanEntry):
    # Por fecha (los aproximados al final); el mismo día, primero lo que entra
    return (e.tx_date is None, e.tx_date or date_type.max, e.direction != "in", e.name)


def month_entries(session: Session, user_id: int, accounts: List[FinAccount], currency: str,
                  month: date_type, today: date_type) -> List[FinPlanEntry]:
    date_from, date_to = month_bounds(month)
    current = date_from <= today <= date_to
    by_id = {a.id: a for a in accounts}
    recurring = session.exec(select(FinRecurring).where(FinRecurring.user_id == user_id)).all()
    entries: List[FinPlanEntry] = []
    for account in accounts:
        if not account.is_active:
            continue
        if account.kind == "credit":
            entries += _card_entries(session, account, recurring, today, date_from, date_to)
        elif account.kind == "loan":
            loan = _loan_entry(session, account, today, date_from, date_to)
            if loan:
                entries.append(loan)
    entries += _fixed_entries(session, user_id, recurring, by_id, today, date_from, date_to)
    entries += _estimate_entries(session, user_id, currency, date_from, current, today)
    return sorted(entries, key=_sort_key)


def _signed_pending(entries: List[FinPlanEntry]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in entries:
        out[e.currency] = out.get(e.currency, 0) + (e.pending_cents if e.direction == "in" else -e.pending_cents)
    return out


def plan(session: Session, user_id: int, month: date_type, today: date_type) -> FinPlanResponse:
    """El plan del mes de `month` (el de hoy o el siguiente)."""
    accounts = session.exec(select(FinAccount).where(FinAccount.user_id == user_id)
                            .order_by(FinAccount.order, FinAccount.id)).all()
    currency = main_currency(accounts)
    balances = account_balances(session, user_id, today)
    start: Dict[str, int] = {}
    for a in accounts:
        if a.is_active and a.kind in CASH_KINDS and a.parent_id is None:
            start[a.currency] = start.get(a.currency, 0) + balances.get(a.id, a.opening_balance_cents)
    date_from, date_to = month_bounds(month)
    current = date_from <= today <= date_to
    if not current:
        # Lo que quedaría al empezar: hoy, más lo que aún falta del mes en curso
        for cur, cents in _signed_pending(month_entries(session, user_id, accounts, currency,
                                                        today.replace(day=1), today)).items():
            start[cur] = start.get(cur, 0) + cents
    row = settings_row(session, user_id)
    return FinPlanResponse(
        month=date_from, date_from=date_from, date_to=date_to, today=today, current=current,
        period=row.period if row and row.period else "month", currency=currency,
        start=[FinPlanStart(currency=c, cents=v) for c, v in sorted(start.items())],
        entries=month_entries(session, user_id, accounts, currency, date_from, today),
    )
