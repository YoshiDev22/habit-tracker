"""
Finanzas personales (épica 37, fase 1: el módulo y el registro a mano). Todo
empieza con require_module(..., "finance"): sin el módulo encendido, 403.

Cuentas, categorías, movimientos, fijos, el periodo ("¿Cada cuándo cobras?") y
el resumen. Lo que no es una ruta vive en backend/finance.py. Las rutas
literales van antes que las /{id}.
"""
from datetime import date as date_type
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.database import get_session
from backend.finance import (account_balances, account_currencies, first_transaction_date, history_before_opening, card_statement, cut_on_or_after,
                             installment_bills, splits_by_transaction, ensure_finance_setup, generate_due, last_charge, settings_row,
                             summary, user_period)
from backend.models import (FinAccount, FinCategory, FinInstallment, FinRecurring, FinSettings, FinSplit,
                            FinTransaction, User, utc_now_naive)
from backend.routers.auth import require_module
from backend.schemas import (
    FinInstallmentCreate, FinInstallmentListResponse, FinInstallmentResponse, FinSplitFields,
    FinStatementResponse, FinConsentResponse, FinCategoryOrder,
    FinAccountCreate,
    FinAccountListResponse,
    FinAccountResponse,
    FinAccountUpdate,
    FinCategoryCreate,
    FinCategoryListResponse,
    FinCategoryResponse,
    FinCategoryUpdate,
    FinRecurringFields,
    FinRecurringListResponse,
    FinRecurringResponse,
    FinRecurringUpdate,
    FinSettingsResponse,
    FinSettingsUpdate,
    FinSummaryResponse,
    FinTransactionFields,
    FinTransactionImport,
    FinTransactionListResponse,
    FinTransactionResponse,
    FinTransactionUpdate,
)
from backend.series import SEMIMONTHLY_DAYS, next_date, period_bounds, skip_past

router = APIRouter(tags=["finance"])

# Un listado por fechas abarca como mucho un año (la vista previa de pegar)
# Un rango de la pantalla ("Siempre", un año, uno elegido): hasta diez años
MAX_SUMMARY_DAYS = 3660


CONSENT_MISSING = "Antes de usar Finanzas, acepta cómo se tratan tus datos."


def finance_module_user(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """El usuario del token, si tiene Finanzas encendido (si no, 403)"""
    require_module(session, current_user, "finance")
    return current_user


def finance_user(session: Session = Depends(get_session), user: User = Depends(finance_module_user)) -> User:
    """Además, que haya dado su consentimiento: son datos financieros, y sin él
    no se guarda ni se enseña nada (403)"""
    row = settings_row(session, user.id)
    if row is None or row.consent_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CONSENT_MISSING)
    return user


def _today(session: Session, user: User) -> date_type:
    # Importado aquí: backend.reports importa los reportes, que importan costing
    from backend.reports import local_today
    return local_today(session, user)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} no encontrada")


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _own_account(session: Session, user_id: int, account_id: int) -> FinAccount:
    account = session.exec(select(FinAccount).where(FinAccount.id == account_id, FinAccount.user_id == user_id)).first()
    if not account:
        raise _not_found("Cuenta")
    return account


def _own_category(session: Session, user_id: int, category_id: int) -> FinCategory:
    category = session.exec(
        select(FinCategory).where(FinCategory.id == category_id, FinCategory.user_id == user_id)).first()
    if not category:
        raise _not_found("Categoría")
    return category


def _own_transaction(session: Session, user_id: int, tx_id: int) -> FinTransaction:
    tx = session.exec(select(FinTransaction).where(FinTransaction.id == tx_id, FinTransaction.user_id == user_id)).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movimiento no encontrado")
    return tx


def _own_recurring(session: Session, user_id: int, recurring_id: int) -> FinRecurring:
    rc = session.exec(select(FinRecurring).where(FinRecurring.id == recurring_id, FinRecurring.user_id == user_id)).first()
    if not rc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fijo no encontrado")
    return rc


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise _unprocessable("El nombre no puede estar vacío")
    return name


def _clean_concept(value: str) -> str:
    concept = (value or "").strip()
    if not concept:
        raise _unprocessable("El concepto no puede estar vacío")
    return concept


def _clean_note(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


def _unique_name(session: Session, model, user_id: int, name: str, exclude_id: Optional[int], what: str) -> None:
    query = select(model.id).where(model.user_id == user_id, model.name == name)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if session.exec(query).first() is not None:
        raise _conflict(f"Ya tienes una {what} llamada '{name}'")


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# ==================== Movimientos: las reglas ====================

def _check_transaction(session: Session, user_id: int, kind: str, account_id: int,
                       category_id: Optional[int], to_account_id: Optional[int], has_splits: bool = False) -> None:
    """Un gasto o un ingreso lleva categoría de su tipo (o partes, cada una con
    la suya) y ninguna cuenta de destino; una transferencia, otra cuenta propia
    de la misma moneda y ninguna categoría. La app no convierte entre monedas."""
    account = _own_account(session, user_id, account_id)
    if kind == "transfer":
        if category_id is not None or has_splits:
            raise _unprocessable("Una transferencia no lleva categoría")
        if to_account_id is None:
            raise _unprocessable("Elige la cuenta a la que va la transferencia")
        target = _own_account(session, user_id, to_account_id)
        if target.id == account.id:
            raise _unprocessable("Una transferencia va a otra cuenta")
        if target.currency != account.currency:
            raise _conflict("Solo se transfiere entre cuentas de la misma moneda: la app no convierte entre monedas")
        return
    if to_account_id is not None:
        raise _unprocessable("Solo una transferencia lleva cuenta de destino")
    if has_splits:
        if category_id is not None:
            raise _unprocessable("Un movimiento dividido lleva la categoría en cada parte")
        return
    if category_id is None:
        raise _unprocessable("Elige una categoría")
    category = _own_category(session, user_id, category_id)
    if category.kind != kind:
        raise _unprocessable(f"'{category.name}' es una categoría de {'ingresos' if category.kind == 'income' else 'gastos'}")


def _check_splits(session: Session, user_id: int, kind: str, amount_cents: int,
                  splits: Optional[List[FinSplitFields]]) -> List[FinSplitFields]:
    """Las partes de un movimiento dividido: al menos dos, cada una con una
    categoría propia de su tipo y sin repetir, y que sumen exacto el monto."""
    if not splits:
        return []
    if kind == "transfer":
        raise _unprocessable("Una transferencia no se divide en categorías")
    if len(splits) < 2:
        raise _unprocessable("Para dividir hacen falta al menos dos partes")
    seen = set()
    for part in splits:
        category = _own_category(session, user_id, part.category_id)
        if category.kind != kind:
            raise _unprocessable(f"'{category.name}' es una categoría de {'ingresos' if category.kind == 'income' else 'gastos'}")
        if category.id in seen:
            raise _unprocessable(f"'{category.name}' está dos veces: júntalas en una parte")
        seen.add(category.id)
    total = sum(part.amount_cents for part in splits)
    if total != amount_cents:
        raise _unprocessable(f"Las partes suman {total / 100:,.2f} y el movimiento es de {amount_cents / 100:,.2f}")
    return splits


def _save_splits(session: Session, user_id: int, tx: FinTransaction, splits: List[FinSplitFields]) -> None:
    """Reemplaza las partes de `tx` (necesita su id: después de un flush)."""
    for old in session.exec(select(FinSplit).where(FinSplit.user_id == user_id, FinSplit.transaction_id == tx.id)).all():
        session.delete(old)
    for order, part in enumerate(splits):
        session.add(FinSplit(user_id=user_id, transaction_id=tx.id, category_id=part.category_id,
                             amount_cents=part.amount_cents, order=order))


def _new_transaction(session: Session, user_id: int, body: FinTransactionFields, source: str):
    """El movimiento (sin guardar) y sus partes ya revisadas."""
    splits = _check_splits(session, user_id, body.kind, body.amount_cents, body.splits)
    _check_transaction(session, user_id, body.kind, body.account_id, body.category_id, body.to_account_id,
                       has_splits=bool(splits))
    tx = FinTransaction(
        user_id=user_id, account_id=body.account_id, kind=body.kind, amount_cents=body.amount_cents,
        tx_date=body.tx_date, category_id=body.category_id, to_account_id=body.to_account_id,
        concept=_clean_concept(body.concept), note=_clean_note(body.note), source=source,
    )
    return tx, splits


def _tx_response(tx: FinTransaction, currencies: Dict[int, str], splits: Optional[List[FinSplit]] = None,
                 installment_id: Optional[int] = None) -> FinTransactionResponse:
    return FinTransactionResponse(
        id=tx.id, kind=tx.kind, account_id=tx.account_id, to_account_id=tx.to_account_id,
        category_id=tx.category_id, amount_cents=tx.amount_cents, currency=currencies.get(tx.account_id, "MXN"),
        tx_date=tx.tx_date, concept=tx.concept, note=tx.note, source=tx.source,
        recurring_id=tx.recurring_id, needs_review=tx.needs_review,
        splits=[FinSplitFields(category_id=p.category_id, amount_cents=p.amount_cents) for p in splits or []],
        installment_id=installment_id,
    )


def _installments_by_transaction(session: Session, user_id: int, tx_ids: List[int]) -> Dict[int, int]:
    if not tx_ids:
        return {}
    return dict(session.exec(select(FinInstallment.transaction_id, FinInstallment.id).where(
        FinInstallment.user_id == user_id, FinInstallment.transaction_id.in_(tx_ids))).all())


def _one_response(session: Session, user_id: int, tx: FinTransaction) -> FinTransactionResponse:
    return _tx_response(tx, account_currencies(session, user_id),
                        splits_by_transaction(session, user_id, [tx.id]).get(tx.id),
                        _installments_by_transaction(session, user_id, [tx.id]).get(tx.id))


def _range(session: Session, user: User, day: Optional[date_type], date_from: Optional[date_type],
           date_to: Optional[date_type], max_days: int = MAX_SUMMARY_DAYS):
    """Las fechas de un listado: las pedidas, o el periodo que contiene `day` (hoy si no viene)."""
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise _unprocessable("Pide date_from y date_to juntos")
        if date_to < date_from:
            raise _unprocessable("date_to no puede ser anterior a date_from")
        if (date_to - date_from).days >= max_days:
            raise _unprocessable(f"Pide como mucho {max_days} días")
        return date_from, date_to
    return period_bounds(user_period(session, user.id), day or _today(session, user))


# ==================== Consentimiento ====================

@router.get("/consent", response_model=FinConsentResponse)
def get_finance_consent(session: Session = Depends(get_session), user: User = Depends(finance_module_user)):
    """Si ya aceptó (y cuándo): la página lo pregunta antes de pedir nada más."""
    row = settings_row(session, user.id)
    return FinConsentResponse(consent_at=row.consent_at if row else None)


@router.post("/consent", response_model=FinConsentResponse)
def give_finance_consent(session: Session = Depends(get_session), user: User = Depends(finance_module_user)):
    """Acepta. Volver a aceptar conserva la primera fecha."""
    row = settings_row(session, user.id) or FinSettings(user_id=user.id)
    if row.consent_at is None:
        row.consent_at = utc_now_naive()
        session.add(row)
        session.commit()
    return FinConsentResponse(consent_at=row.consent_at)


# ==================== Periodo ====================

@router.get("/settings", response_model=FinSettingsResponse)
def get_finance_settings(session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """El periodo que eligió ("¿Cada cuándo cobras?"); null si aún no contesta."""
    row = settings_row(session, user.id)
    return FinSettingsResponse(period=row.period if row else None)


@router.put("/settings", response_model=FinSettingsResponse)
def put_finance_settings(body: FinSettingsUpdate, session: Session = Depends(get_session),
                         user: User = Depends(finance_user)):
    row = settings_row(session, user.id) or FinSettings(user_id=user.id)
    row.period = body.period
    session.add(row)
    session.commit()
    return FinSettingsResponse(period=row.period)


# ==================== Resumen ====================

@router.get("/summary", response_model=FinSummaryResponse)
def get_finance_summary(day: Optional[date_type] = None, date_from: Optional[date_type] = None,
                        date_to: Optional[date_type] = None, all: bool = False,
                        session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """El periodo que contiene `day` (hoy, si no viene): gasto e ingreso por
    categoría, lo que se movió en cada cuenta y los totales por moneda, más
    un día del periodo anterior y del siguiente para moverse con ‹ ›. Con
    date_from y date_to, esas fechas (hasta diez años); con all, desde el
    primer movimiento hasta hoy ("Siempre")."""
    ensure_finance_setup(session, user.id)
    today = _today(session, user)
    generate_due(session, user.id, today)
    bounds = None
    if all:
        bounds = (min(first_transaction_date(session, user.id) or today, today), today)
    elif date_from is not None or date_to is not None:
        bounds = _range(session, user, None, date_from, date_to, MAX_SUMMARY_DAYS)
    return summary(session, user.id, day or today, bounds)


# ==================== Cuentas ====================

def _account_counts(session: Session, user_id: int) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for column in (FinTransaction.account_id, FinTransaction.to_account_id):
        for account_id, n in session.exec(select(column, func.count()).where(
                FinTransaction.user_id == user_id, column.is_not(None)).group_by(column)).all():
            counts[account_id] = counts.get(account_id, 0) + n
    return counts


def _account_response(account: FinAccount, counts: Dict[int, int], balances: Dict[int, int],
                      before: Optional[Dict[int, tuple]] = None) -> FinAccountResponse:
    balance = balances.get(account.id, account.opening_balance_cents)
    credit = account.kind == "credit"
    before_count, before_in, before_out = (before or {}).get(account.id, (0, 0, 0))
    return FinAccountResponse(
        opening_date=account.opening_date, before_count=before_count, before_in_cents=before_in,
        before_out_cents=before_out,
        id=account.id, name=account.name, kind=account.kind, currency=account.currency, last4=account.last4,
        is_default=account.is_default, is_active=account.is_active, order=account.order,
        tx_count=counts.get(account.id, 0), icon=account.icon, color=account.color,
        opening_balance_cents=account.opening_balance_cents, credit_limit_cents=account.credit_limit_cents,
        statement_day=account.statement_day, due_day=account.due_day, balance_cents=balance,
        available_cents=account.credit_limit_cents + balance if credit and account.credit_limit_cents is not None else None,
    )


def _opening_date(value: Optional[date_type], today: date_type) -> Optional[date_type]:
    """El día de un saldo inicial: no puede ser futuro."""
    if value is not None and value > today:
        raise _unprocessable("El día del saldo no puede ser futuro")
    return value


def _credit_only(account: FinAccount) -> None:
    """Límite, corte y pago son de una tarjeta de crédito: en otra, se vacían."""
    if account.kind != "credit":
        account.credit_limit_cents = account.statement_day = account.due_day = None


def _make_default(session: Session, user_id: int, account: FinAccount) -> None:
    for other in session.exec(select(FinAccount).where(
            FinAccount.user_id == user_id, FinAccount.is_default == True, FinAccount.id != account.id)).all():  # noqa: E712
        other.is_default = False
        session.add(other)
    account.is_default = True


@router.get("/accounts", response_model=FinAccountListResponse)
def list_accounts(session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Las cuentas, en su orden (las archivadas también: la pantalla las aparta)."""
    ensure_finance_setup(session, user.id)
    accounts = session.exec(select(FinAccount).where(FinAccount.user_id == user.id)
                            .order_by(FinAccount.order, FinAccount.id)).all()
    counts = _account_counts(session, user.id)
    balances = account_balances(session, user.id, _today(session, user))
    before = history_before_opening(session, user.id)
    return FinAccountListResponse(accounts=[_account_response(a, counts, balances, before) for a in accounts])


@router.post("/accounts", response_model=FinAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(body: FinAccountCreate, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    ensure_finance_setup(session, user.id)
    name = _clean_name(body.name)
    _unique_name(session, FinAccount, user.id, name, None, "cuenta")
    last = session.exec(select(func.max(FinAccount.order)).where(FinAccount.user_id == user.id)).one()
    today = _today(session, user)
    opening_date = _opening_date(body.opening_date, today)
    if opening_date is None and body.opening_balance_cents:
        opening_date = today   # un saldo es "a hoy" si no dice otra cosa
    account = FinAccount(user_id=user.id, name=name, kind=body.kind, currency=body.currency, last4=body.last4,
                         order=(last or 0) + 1, icon=body.icon, color=body.color,
                         opening_balance_cents=body.opening_balance_cents, opening_date=opening_date,
                         credit_limit_cents=body.credit_limit_cents,
                         statement_day=body.statement_day, due_day=body.due_day)
    _credit_only(account)
    if body.is_default:
        _make_default(session, user.id, account)
    session.add(account)
    session.commit()
    session.refresh(account)
    return _account_response(account, {}, {})


@router.patch("/accounts/{account_id}", response_model=FinAccountResponse)
def update_account(account_id: int, body: FinAccountUpdate, session: Session = Depends(get_session),
                   user: User = Depends(finance_user)):
    """Renombrar, cambiar tipo, últimos 4 dígitos u orden; elegirla como la de
    por defecto; archivarla. La moneda solo cambia sin movimientos ni fijos."""
    account = _own_account(session, user.id, account_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "kind", "currency", "is_default", "is_active", "order", "opening_balance_cents"):
        if field in changes and changes[field] is None:
            raise _unprocessable("Ese dato no puede quedar vacío")
    counts = _account_counts(session, user.id)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"])
        _unique_name(session, FinAccount, user.id, changes["name"], account.id, "cuenta")
    if "currency" in changes and changes["currency"] != account.currency:
        used = counts.get(account.id, 0) + _recurring_count(session, user.id, account_id=account.id)
        if used:
            raise _conflict(f"'{account.name}' ya tiene movimientos: su moneda no cambia (la app no convierte entre monedas)")
    if changes.get("is_default") is False and account.is_default:
        raise _conflict("Elige otra cuenta como la de por defecto")
    if changes.get("is_active") is False:
        if account.is_default:
            raise _conflict(f"'{account.name}' es tu cuenta por defecto: elige otra antes de archivarla")
        if _recurring_count(session, user.id, account_id=account.id, active_only=True):
            raise _conflict(f"'{account.name}' la usa un fijo: cámbialo de cuenta o páusalo antes de archivarla")
    if changes.get("is_default") and not changes.get("is_active", account.is_active):
        raise _conflict("Una cuenta archivada no puede ser la de por defecto")
    if changes.pop("is_default", None):
        _make_default(session, user.id, account)
    if "opening_date" in changes:
        _opening_date(changes["opening_date"], _today(session, user))
    for field, value in changes.items():
        setattr(account, field, value)
    _credit_only(account)
    session.add(account)
    session.commit()
    session.refresh(account)
    return _account_response(account, counts, account_balances(session, user.id, _today(session, user)),
                             history_before_opening(session, user.id))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Borra una cuenta sin movimientos ni fijos. Con alguno, 409: se archiva."""
    account = _own_account(session, user.id, account_id)
    count = _account_counts(session, user.id).get(account.id, 0)
    if count:
        raise _conflict(f"'{account.name}' tiene {_plural(count, 'movimiento', 'movimientos')}: archívala en vez de borrarla")
    recurring = _recurring_count(session, user.id, account_id=account.id)
    if recurring:
        raise _conflict(f"'{account.name}' la usa{'n' if recurring > 1 else ''} {_plural(recurring, 'fijo', 'fijos')}: cámbialos de cuenta antes de borrarla")
    if session.exec(select(FinInstallment.id).where(FinInstallment.user_id == user.id,
                                                    FinInstallment.account_id == account.id)).first():
        raise _conflict(f"'{account.name}' tiene compras a meses: archívala en vez de borrarla")
    if account.is_default:
        raise _conflict(f"'{account.name}' es tu cuenta por defecto: elige otra antes de borrarla")
    session.delete(account)
    session.commit()


# ==================== Categorías ====================

def _category_counts(session: Session, user_id: int) -> Dict[int, int]:
    """Movimientos por categoría, contando las partes de los divididos."""
    counts = dict(session.exec(
        select(FinTransaction.category_id, func.count())
        .where(FinTransaction.user_id == user_id, FinTransaction.category_id.is_not(None))
        .group_by(FinTransaction.category_id)
    ).all())
    for category_id, count in session.exec(select(FinSplit.category_id, func.count())
                                           .where(FinSplit.user_id == user_id).group_by(FinSplit.category_id)).all():
        counts[category_id] = counts.get(category_id, 0) + count
    return counts


def _recurring_count(session: Session, user_id: int, account_id: Optional[int] = None,
                     category_id: Optional[int] = None, active_only: bool = False) -> int:
    query = select(func.count()).select_from(FinRecurring).where(FinRecurring.user_id == user_id)
    if account_id is not None:
        query = query.where(FinRecurring.account_id == account_id)
    if category_id is not None:
        query = query.where(FinRecurring.category_id == category_id)
    if active_only:
        query = query.where(FinRecurring.paused == False)  # noqa: E712
    return session.exec(query).one()


def _category_response(category: FinCategory, counts: Dict[int, int]) -> FinCategoryResponse:
    return FinCategoryResponse(id=category.id, name=category.name, color=category.color, kind=category.kind,
                               order=category.order, tx_count=counts.get(category.id, 0), icon=category.icon)


@router.get("/categories", response_model=FinCategoryListResponse)
def list_categories(session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Las categorías de gasto y de ingreso, en su orden. La primera vez, las de inicio."""
    ensure_finance_setup(session, user.id)
    categories = session.exec(select(FinCategory).where(FinCategory.user_id == user.id)
                              .order_by(FinCategory.order, FinCategory.id)).all()
    counts = _category_counts(session, user.id)
    return FinCategoryListResponse(categories=[_category_response(c, counts) for c in categories])


@router.post("/categories", response_model=FinCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(body: FinCategoryCreate, session: Session = Depends(get_session),
                    user: User = Depends(finance_user)):
    ensure_finance_setup(session, user.id)
    name = _clean_name(body.name)
    _unique_name(session, FinCategory, user.id, name, None, "categoría")
    last = session.exec(select(func.max(FinCategory.order)).where(FinCategory.user_id == user.id)).one()
    category = FinCategory(user_id=user.id, name=name, color=body.color, kind=body.kind, icon=body.icon,
                           order=(last or 0) + 1)
    session.add(category)
    session.commit()
    session.refresh(category)
    return _category_response(category, {})


@router.put("/categories/order", response_model=FinCategoryListResponse)
def order_categories(body: FinCategoryOrder, session: Session = Depends(get_session),
                     user: User = Depends(finance_user)):
    """El orden nuevo de las categorías de un tipo: todas sus ids, sin repetir
    (si falta o sobra alguna, 422; una de otra cuenta, 404)."""
    mine = {c.id: c for c in session.exec(select(FinCategory).where(FinCategory.user_id == user.id,
                                                                    FinCategory.kind == body.kind)).all()}
    if any(i not in mine for i in body.ids):
        raise _not_found("Categoría")
    if len(set(body.ids)) != len(body.ids) or set(body.ids) != set(mine):
        raise _unprocessable("Manda todas las categorías de ese tipo, una vez cada una")
    for order, category_id in enumerate(body.ids):
        mine[category_id].order = order
        session.add(mine[category_id])
    session.commit()
    return list_categories(session=session, user=user)


@router.patch("/categories/{category_id}", response_model=FinCategoryResponse)
def update_category(category_id: int, body: FinCategoryUpdate, session: Session = Depends(get_session),
                    user: User = Depends(finance_user)):
    """Renombrar, recolorear u ordenar. Sus movimientos la siguen: van por id."""
    category = _own_category(session, user.id, category_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise _unprocessable("El nombre no puede quedar vacío")
        category.name = _clean_name(changes["name"])
        _unique_name(session, FinCategory, user.id, category.name, category.id, "categoría")
    if "color" in changes:
        category.color = changes["color"]
    if "icon" in changes:
        category.icon = changes["icon"]
    if changes.get("order") is not None:
        category.order = changes["order"]
    session.add(category)
    session.commit()
    session.refresh(category)
    return _category_response(category, _category_counts(session, user.id))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Borra una categoría sin movimientos ni fijos (con alguno, 409: primero se
    pasan a otra). La última de su tipo tampoco se borra."""
    category = _own_category(session, user.id, category_id)
    recurring = _recurring_count(session, user.id, category_id=category.id)
    if recurring:
        raise _conflict(f"'{category.name}' la usa{'n' if recurring > 1 else ''} {_plural(recurring, 'fijo', 'fijos')}: cámbialos de categoría antes de borrarla")
    count = _category_counts(session, user.id).get(category.id, 0)
    if count:
        raise _conflict(f"'{category.name}' tiene {_plural(count, 'movimiento', 'movimientos')}: cámbialos de categoría antes de borrarla")
    same_kind = session.exec(select(func.count()).select_from(FinCategory).where(
        FinCategory.user_id == user.id, FinCategory.kind == category.kind)).one()
    if same_kind <= 1:
        raise _conflict(f"Necesitas al menos una categoría de {'ingresos' if category.kind == 'income' else 'gastos'}")
    session.delete(category)
    session.commit()


# ==================== Fijos ====================

def _recurring_response(session: Session, rc: FinRecurring, currencies: Dict[int, str]) -> FinRecurringResponse:
    return FinRecurringResponse(
        id=rc.id, kind=rc.kind, account_id=rc.account_id, category_id=rc.category_id, concept=rc.concept,
        amount_cents=rc.amount_cents, currency=currencies.get(rc.account_id, "MXN"), note=rc.note,
        frequency=rc.frequency, first_day=rc.first_day, second_day=rc.second_day, start_date=rc.start_date,
        end_date=rc.end_date, paused=rc.paused, generated=rc.generated,
        next_date=None if rc.paused else next_date(rc), last_charge=last_charge(session, rc),
    )


def _pay_days(frequency: str, first: Optional[int], second: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    """Los dos días de una quincenal, el menor primero; (None, None) si es otra
    frecuencia o son el 15 y el último (los de siempre)."""
    if frequency != "semimonthly" or (first is None and second is None):
        return None, None
    if first is None or second is None:
        raise _unprocessable("Una quincena lleva sus dos días de pago")
    if first == second:
        raise _unprocessable("Los dos días de pago de la quincena tienen que ser distintos")
    days = tuple(sorted((first, second)))
    return (None, None) if days == SEMIMONTHLY_DAYS else days


def _check_recurring(session: Session, user_id: int, kind: str, account_id: int, category_id: int) -> None:
    _check_transaction(session, user_id, kind, account_id, category_id, None)


def _check_dates(start: date_type, end: Optional[date_type]) -> None:
    if end is not None and end < start:
        raise _unprocessable("La fecha de fin no puede ser anterior al primer cobro")


@router.get("/recurring", response_model=FinRecurringListResponse)
def list_recurring(session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Los fijos, con su siguiente cobro. Antes, genera los que ya llegaron."""
    generate_due(session, user.id, _today(session, user))
    rows = session.exec(select(FinRecurring).where(FinRecurring.user_id == user.id)
                        .order_by(FinRecurring.paused, FinRecurring.concept, FinRecurring.id)).all()
    currencies = account_currencies(session, user.id)
    return FinRecurringListResponse(recurring=[_recurring_response(session, rc, currencies) for rc in rows])


@router.post("/recurring", response_model=FinRecurringResponse, status_code=status.HTTP_201_CREATED)
def create_recurring(body: FinRecurringFields, session: Session = Depends(get_session),
                     user: User = Depends(finance_user)):
    """Un fijo nuevo. Si su primer cobro ya pasó, se generan los que ya llegaron
    (hasta 36 de una vez)."""
    _check_recurring(session, user.id, body.kind, body.account_id, body.category_id)
    _check_dates(body.start_date, body.end_date)
    first_day, second_day = _pay_days(body.frequency, body.first_day, body.second_day)
    rc = FinRecurring(user_id=user.id, account_id=body.account_id, category_id=body.category_id, kind=body.kind,
                      concept=_clean_concept(body.concept), amount_cents=body.amount_cents,
                      note=_clean_note(body.note), frequency=body.frequency, first_day=first_day,
                      second_day=second_day, start_date=body.start_date, end_date=body.end_date)
    session.add(rc)
    session.commit()
    generate_due(session, user.id, _today(session, user))
    session.refresh(rc)
    return _recurring_response(session, rc, account_currencies(session, user.id))


@router.patch("/recurring/{recurring_id}", response_model=FinRecurringResponse)
def update_recurring(recurring_id: int, body: FinRecurringUpdate, session: Session = Depends(get_session),
                     user: User = Depends(finance_user)):
    """Cambia un fijo: solo afecta a los cobros siguientes. Con cobros ya
    anotados, start_date es "el siguiente cobro": la serie vuelve a contar desde
    ahí y tiene que ir después del último anotado. Al reanudarlo, los cobros
    del tiempo en pausa no se generan."""
    rc = _own_recurring(session, user.id, recurring_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("account_id", "category_id", "concept", "amount_cents", "frequency", "start_date", "paused"):
        if field in changes and changes[field] is None:
            raise _unprocessable("Ese dato no puede quedar vacío")
    frequency = changes.get("frequency", rc.frequency)
    if "first_day" in changes or "second_day" in changes or "frequency" in changes:
        days = _pay_days(frequency, changes.get("first_day", rc.first_day), changes.get("second_day", rc.second_day))
        changes["first_day"], changes["second_day"] = days
    reanchor = rc.generated and (("start_date" in changes and changes["start_date"] != rc.start_date)
                                 or frequency != rc.frequency
                                 or changes.get("first_day", rc.first_day) != rc.first_day
                                 or changes.get("second_day", rc.second_day) != rc.second_day)
    if reanchor:
        last = last_charge(session, rc)
        new_next = changes.get("start_date") or next_date(rc) or rc.start_date
        if last is not None and new_next <= last:
            raise _conflict(f"El siguiente cobro tiene que ser después del último ya anotado ({last.isoformat()})")
        changes["start_date"] = new_next
    if "account_id" in changes or "category_id" in changes:
        _check_recurring(session, user.id, rc.kind, changes.get("account_id", rc.account_id),
                         changes.get("category_id", rc.category_id))
    if "concept" in changes:
        changes["concept"] = _clean_concept(changes["concept"])
    if "note" in changes:
        changes["note"] = _clean_note(changes["note"])
    resuming = rc.paused and changes.get("paused") is False
    for field, value in changes.items():
        setattr(rc, field, value)
    if reanchor:
        rc.generated = 0   # la serie cuenta desde el nuevo siguiente cobro
    _check_dates(rc.start_date, rc.end_date)
    if resuming:
        skip_past(rc, _today(session, user))
    session.add(rc)
    session.commit()
    generate_due(session, user.id, _today(session, user))
    session.refresh(rc)
    return _recurring_response(session, rc, account_currencies(session, user.id))


@router.delete("/recurring/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring(recurring_id: int, delete_transactions: bool = False, session: Session = Depends(get_session),
                     user: User = Depends(finance_user)):
    """Deja de cobrarlo. Los movimientos que ya anotó se quedan (sin el 🔁),
    salvo con delete_transactions=true (para rehacer uno creado mal)."""
    rc = _own_recurring(session, user.id, recurring_id)
    for tx in session.exec(select(FinTransaction).where(
            FinTransaction.user_id == user.id, FinTransaction.recurring_id == rc.id)).all():
        if delete_transactions:
            session.delete(tx)
        else:
            tx.recurring_id = None
            session.add(tx)
    session.delete(rc)
    session.commit()


# ==================== Movimientos ====================

@router.get("/transactions", response_model=FinTransactionListResponse)
def list_transactions(day: Optional[date_type] = None, date_from: Optional[date_type] = None,
                      date_to: Optional[date_type] = None, account_id: Optional[int] = None,
                      category_id: Optional[int] = None, session: Session = Depends(get_session),
                      user: User = Depends(finance_user)):
    """Los movimientos del periodo que contiene `day` (hoy, si no viene), o de
    date_from a date_to (hasta 366 días), del más reciente al más antiguo."""
    generate_due(session, user.id, _today(session, user))
    start, end = _range(session, user, day, date_from, date_to)
    query = select(FinTransaction).where(
        FinTransaction.user_id == user.id, FinTransaction.tx_date >= start, FinTransaction.tx_date <= end)
    if account_id is not None:
        query = query.where(or_(FinTransaction.account_id == account_id, FinTransaction.to_account_id == account_id))
    if category_id is not None:
        in_parts = select(FinSplit.transaction_id).where(FinSplit.user_id == user.id, FinSplit.category_id == category_id)
        query = query.where(or_(FinTransaction.category_id == category_id, FinTransaction.id.in_(in_parts)))
    rows = session.exec(query.order_by(FinTransaction.tx_date.desc(), FinTransaction.id.desc())).all()
    currencies = account_currencies(session, user.id)
    ids = [tx.id for tx in rows]
    splits = splits_by_transaction(session, user.id, ids)
    installments = _installments_by_transaction(session, user.id, ids)
    return FinTransactionListResponse(date_from=start, date_to=end, transactions=[
        _tx_response(tx, currencies, splits.get(tx.id), installments.get(tx.id)) for tx in rows])


@router.post("/transactions", response_model=FinTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(body: FinTransactionFields, session: Session = Depends(get_session),
                       user: User = Depends(finance_user)):
    """Un movimiento escrito a mano (la alta rápida), con partes si se dividió."""
    tx, splits = _new_transaction(session, user.id, body, "manual")
    session.add(tx)
    session.flush()
    _save_splits(session, user.id, tx, splits)
    session.commit()
    session.refresh(tx)
    return _one_response(session, user.id, tx)


@router.post("/transactions/import", response_model=FinTransactionListResponse, status_code=status.HTTP_201_CREATED)
def import_transactions(body: FinTransactionImport, session: Session = Depends(get_session),
                        user: User = Depends(finance_user)):
    """Varios de una vez (el estado de cuenta pegado), ya revisados en la vista
    previa. Si uno no vale, no entra ninguno."""
    pairs = [_new_transaction(session, user.id, row, "import") for row in body.rows]
    for tx, _ in pairs:
        session.add(tx)
    session.flush()
    for tx, splits in pairs:
        _save_splits(session, user.id, tx, splits)
    session.commit()
    new = [tx for tx, _ in pairs]
    for tx in new:
        session.refresh(tx)
    currencies = account_currencies(session, user.id)
    dates = [tx.tx_date for tx in new]
    return FinTransactionListResponse(date_from=min(dates), date_to=max(dates),
                                      transactions=[_tx_response(tx, currencies) for tx in new])


@router.patch("/transactions/{tx_id}", response_model=FinTransactionResponse)
def update_transaction(tx_id: int, body: FinTransactionUpdate, session: Session = Depends(get_session),
                       user: User = Depends(finance_user)):
    """Edita un movimiento. Las reglas se comprueban sobre cómo queda: cambiar
    un gasto a transferencia pide quitar la categoría y poner la cuenta de destino."""
    tx = _own_transaction(session, user.id, tx_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("kind", "account_id", "amount_cents", "tx_date", "concept", "needs_review"):
        if field in changes and changes[field] is None:
            raise _unprocessable("Ese dato no puede quedar vacío")
    if "concept" in changes:
        changes["concept"] = _clean_concept(changes["concept"])
    if "note" in changes:
        changes["note"] = _clean_note(changes["note"])
    # Las partes: una lista las reemplaza, null las quita; sin mandarlas, las de
    # antes tienen que seguir cuadrando con el monto y el tipo que queden
    replace_splits = "splits" in changes
    new_splits = changes.pop("splits", None)
    if not replace_splits:
        existing = splits_by_transaction(session, user.id, [tx.id]).get(tx.id, [])
        new_splits = [FinSplitFields(category_id=p.category_id, amount_cents=p.amount_cents) for p in existing]
        replace_splits = bool(existing)
    else:
        new_splits = [FinSplitFields(**p) if isinstance(p, dict) else p for p in (new_splits or [])]
    kind = changes.get("kind", tx.kind)
    splits = _check_splits(session, user.id, kind, changes.get("amount_cents", tx.amount_cents), new_splits)
    if splits:
        changes["category_id"] = None
    merged = {field: changes.get(field, getattr(tx, field))
              for field in ("kind", "account_id", "category_id", "to_account_id")}
    _check_transaction(session, user.id, **merged, has_splits=bool(splits))
    for field, value in changes.items():
        setattr(tx, field, value)
    session.add(tx)
    if replace_splits:
        _save_splits(session, user.id, tx, splits)
    session.commit()
    session.refresh(tx)
    return _one_response(session, user.id, tx)


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(tx_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Borra un movimiento, con sus partes y su plan de meses. Si salió de un
    fijo, ese cobro no vuelve a generarse."""
    tx = _own_transaction(session, user.id, tx_id)
    for row in session.exec(select(FinSplit).where(FinSplit.user_id == user.id, FinSplit.transaction_id == tx.id)).all():
        session.delete(row)
    for row in session.exec(select(FinInstallment).where(
            FinInstallment.user_id == user.id, FinInstallment.transaction_id == tx.id)).all():
        session.delete(row)
    session.delete(tx)
    session.commit()


# ==================== Tarjetas: estado de cuenta y meses sin intereses ====================

def _credit_card(session: Session, user_id: int, account_id: int) -> FinAccount:
    account = _own_account(session, user_id, account_id)
    if account.kind != "credit":
        raise _unprocessable(f"'{account.name}' no es una tarjeta de crédito")
    return account


@router.get("/accounts/{account_id}/statement", response_model=FinStatementResponse)
def account_statement(account_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """El estado de cuenta calculado de una tarjeta: último corte, cuánto pagar
    para no generar intereses (sin las mensualidades de MSI que faltan) y lo
    abonado desde el corte. Pide día de corte y de pago (409 sin ellos)."""
    account = _credit_card(session, user.id, account_id)
    if not account.statement_day or not account.due_day:
        raise _conflict(f"Pon el día de corte y el de pago de '{account.name}' para calcular su pago")
    generate_due(session, user.id, _today(session, user))
    return card_statement(session, account, _today(session, user))


def _installment_response(inst: FinInstallment, account: FinAccount, today: date_type) -> FinInstallmentResponse:
    bills = installment_bills(inst, account.statement_day)
    done = [cents for cut, cents in bills if cut <= today]
    upcoming = [cut for cut, _ in bills if cut > today]
    return FinInstallmentResponse(
        id=inst.id, account_id=inst.account_id, transaction_id=inst.transaction_id, concept=inst.concept,
        total_cents=inst.total_cents, currency=account.currency, months=inst.months,
        purchase_date=inst.purchase_date, first_statement=inst.first_statement, monthly_cents=bills[0][1],
        billed=len(done), remaining_cents=inst.total_cents - sum(done),
        next_statement=upcoming[0] if upcoming else None,
    )


@router.get("/installments", response_model=FinInstallmentListResponse)
def list_installments(account_id: Optional[int] = None, session: Session = Depends(get_session),
                      user: User = Depends(finance_user)):
    """Las compras a meses, de la más reciente a la más antigua."""
    query = select(FinInstallment).where(FinInstallment.user_id == user.id)
    if account_id is not None:
        query = query.where(FinInstallment.account_id == account_id)
    rows = session.exec(query.order_by(FinInstallment.purchase_date.desc(), FinInstallment.id.desc())).all()
    accounts = {a.id: a for a in session.exec(select(FinAccount).where(FinAccount.user_id == user.id)).all()}
    today = _today(session, user)
    return FinInstallmentListResponse(installments=[_installment_response(i, accounts[i.account_id], today)
                                                    for i in rows if i.account_id in accounts])


@router.post("/installments", response_model=FinInstallmentResponse, status_code=status.HTTP_201_CREATED)
def create_installment(body: FinInstallmentCreate, session: Session = Depends(get_session),
                       user: User = Depends(finance_user)):
    """Una compra a meses. Con transaction_id, la compra ya anotada (un gasto en
    una tarjeta de crédito) da la cuenta, la fecha, el monto y el concepto; una
    compra tiene un solo plan (409). El primer corte, si no viene, es el primero
    desde la compra."""
    if body.transaction_id is not None:
        tx = _own_transaction(session, user.id, body.transaction_id)
        if tx.kind != "expense":
            raise _unprocessable("Solo una compra (un gasto) va a meses")
        account = _credit_card(session, user.id, tx.account_id)
        if session.exec(select(FinInstallment.id).where(FinInstallment.user_id == user.id,
                                                        FinInstallment.transaction_id == tx.id)).first():
            raise _conflict("Esa compra ya está a meses")
        concept, total, purchase = tx.concept, tx.amount_cents, tx.tx_date
        if body.months < 2:
            raise _unprocessable("Una compra a meses va de 2 meses en adelante")
    else:
        if body.account_id is None or body.total_cents is None or body.purchase_date is None or not body.concept:
            raise _unprocessable("Sin la compra anotada, pide cuenta, concepto, total y fecha de compra")
        account = _credit_card(session, user.id, body.account_id)
        concept, total, purchase = _clean_concept(body.concept), body.total_cents, body.purchase_date
    if total < body.months:
        raise _unprocessable("El total no alcanza para tantos meses")
    first = body.first_statement
    if first is None:
        if not account.statement_day:
            raise _conflict(f"Pon el día de corte de '{account.name}' (o el primer corte de la compra)")
        first = cut_on_or_after(account.statement_day, purchase)
    if first < purchase:
        raise _unprocessable("El primer corte no puede ser antes de la compra")
    inst = FinInstallment(user_id=user.id, account_id=account.id, transaction_id=body.transaction_id,
                          concept=concept, total_cents=total, months=body.months, purchase_date=purchase,
                          first_statement=first)
    session.add(inst)
    session.commit()
    session.refresh(inst)
    return _installment_response(inst, account, _today(session, user))


@router.delete("/installments/{installment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_installment(installment_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Quita el plan de meses; la compra se queda (para rehacer uno creado mal)."""
    inst = session.exec(select(FinInstallment).where(FinInstallment.id == installment_id,
                                                     FinInstallment.user_id == user.id)).first()
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra a meses no encontrada")
    session.delete(inst)
    session.commit()
