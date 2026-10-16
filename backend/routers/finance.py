"""
Finanzas personales (épica 37, fase 1: el módulo y el registro a mano). Todo
empieza con require_module(..., "finance"): sin el módulo encendido, 403.

Cuentas, categorías, movimientos, fijos, el periodo ("¿Cada cuándo cobras?") y
el resumen. Lo que no es una ruta vive en backend/finance.py. Las rutas
literales van antes que las /{id}.
"""
from datetime import date as date_type
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.database import get_session
from backend.finance import (account_currencies, ensure_finance_setup, generate_due, last_charge, settings_row,
                             summary, user_period)
from backend.models import FinAccount, FinCategory, FinRecurring, FinSettings, FinTransaction, User
from backend.routers.auth import require_module
from backend.schemas import (
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
MAX_RANGE_DAYS = 366


def finance_user(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """El usuario del token, si tiene Finanzas encendido (si no, 403)"""
    require_module(session, current_user, "finance")
    return current_user


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
                       category_id: Optional[int], to_account_id: Optional[int]) -> None:
    """Un gasto o un ingreso lleva categoría de su tipo y ninguna cuenta de
    destino; una transferencia, otra cuenta propia de la misma moneda y ninguna
    categoría. La app no convierte entre monedas."""
    account = _own_account(session, user_id, account_id)
    if kind == "transfer":
        if category_id is not None:
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
    if category_id is None:
        raise _unprocessable("Elige una categoría")
    category = _own_category(session, user_id, category_id)
    if category.kind != kind:
        raise _unprocessable(f"'{category.name}' es una categoría de {'ingresos' if category.kind == 'income' else 'gastos'}")


def _new_transaction(session: Session, user_id: int, body: FinTransactionFields, source: str) -> FinTransaction:
    _check_transaction(session, user_id, body.kind, body.account_id, body.category_id, body.to_account_id)
    return FinTransaction(
        user_id=user_id, account_id=body.account_id, kind=body.kind, amount_cents=body.amount_cents,
        tx_date=body.tx_date, category_id=body.category_id, to_account_id=body.to_account_id,
        concept=_clean_concept(body.concept), note=_clean_note(body.note), source=source,
    )


def _tx_response(tx: FinTransaction, currencies: Dict[int, str]) -> FinTransactionResponse:
    return FinTransactionResponse(
        id=tx.id, kind=tx.kind, account_id=tx.account_id, to_account_id=tx.to_account_id,
        category_id=tx.category_id, amount_cents=tx.amount_cents, currency=currencies.get(tx.account_id, "MXN"),
        tx_date=tx.tx_date, concept=tx.concept, note=tx.note, source=tx.source,
        recurring_id=tx.recurring_id, needs_review=tx.needs_review,
    )


def _range(session: Session, user: User, day: Optional[date_type], date_from: Optional[date_type],
           date_to: Optional[date_type]):
    """Las fechas de un listado: las pedidas, o el periodo que contiene `day` (hoy si no viene)."""
    if date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise _unprocessable("Pide date_from y date_to juntos")
        if date_to < date_from:
            raise _unprocessable("date_to no puede ser anterior a date_from")
        if (date_to - date_from).days >= MAX_RANGE_DAYS:
            raise _unprocessable(f"Pide como mucho {MAX_RANGE_DAYS} días")
        return date_from, date_to
    return period_bounds(user_period(session, user.id), day or _today(session, user))


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
def get_finance_summary(day: Optional[date_type] = None, session: Session = Depends(get_session),
                        user: User = Depends(finance_user)):
    """El periodo que contiene `day` (hoy, si no viene): gasto e ingreso por
    categoría, lo que se movió en cada cuenta y los totales por moneda, más
    un día del periodo anterior y del siguiente para moverse con ‹ ›."""
    ensure_finance_setup(session, user.id)
    generate_due(session, user.id, _today(session, user))
    return summary(session, user.id, day or _today(session, user))


# ==================== Cuentas ====================

def _account_counts(session: Session, user_id: int) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for column in (FinTransaction.account_id, FinTransaction.to_account_id):
        for account_id, n in session.exec(select(column, func.count()).where(
                FinTransaction.user_id == user_id, column.is_not(None)).group_by(column)).all():
            counts[account_id] = counts.get(account_id, 0) + n
    return counts


def _account_response(account: FinAccount, counts: Dict[int, int]) -> FinAccountResponse:
    return FinAccountResponse(
        id=account.id, name=account.name, kind=account.kind, currency=account.currency, last4=account.last4,
        is_default=account.is_default, is_active=account.is_active, order=account.order,
        tx_count=counts.get(account.id, 0),
    )


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
    return FinAccountListResponse(accounts=[_account_response(a, counts) for a in accounts])


@router.post("/accounts", response_model=FinAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(body: FinAccountCreate, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    ensure_finance_setup(session, user.id)
    name = _clean_name(body.name)
    _unique_name(session, FinAccount, user.id, name, None, "cuenta")
    last = session.exec(select(func.max(FinAccount.order)).where(FinAccount.user_id == user.id)).one()
    account = FinAccount(user_id=user.id, name=name, kind=body.kind, currency=body.currency, last4=body.last4,
                         order=(last or 0) + 1)
    if body.is_default:
        _make_default(session, user.id, account)
    session.add(account)
    session.commit()
    session.refresh(account)
    return _account_response(account, {})


@router.patch("/accounts/{account_id}", response_model=FinAccountResponse)
def update_account(account_id: int, body: FinAccountUpdate, session: Session = Depends(get_session),
                   user: User = Depends(finance_user)):
    """Renombrar, cambiar tipo, últimos 4 dígitos u orden; elegirla como la de
    por defecto; archivarla. La moneda solo cambia sin movimientos ni fijos."""
    account = _own_account(session, user.id, account_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "kind", "currency", "is_default", "is_active", "order"):
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
    for field, value in changes.items():
        setattr(account, field, value)
    session.add(account)
    session.commit()
    session.refresh(account)
    return _account_response(account, counts)


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
    if account.is_default:
        raise _conflict(f"'{account.name}' es tu cuenta por defecto: elige otra antes de borrarla")
    session.delete(account)
    session.commit()


# ==================== Categorías ====================

def _category_counts(session: Session, user_id: int) -> Dict[int, int]:
    return dict(session.exec(
        select(FinTransaction.category_id, func.count())
        .where(FinTransaction.user_id == user_id, FinTransaction.category_id.is_not(None))
        .group_by(FinTransaction.category_id)
    ).all())


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
                               order=category.order, tx_count=counts.get(category.id, 0))


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
    category = FinCategory(user_id=user.id, name=name, color=body.color, kind=body.kind, order=(last or 0) + 1)
    session.add(category)
    session.commit()
    session.refresh(category)
    return _category_response(category, {})


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
        query = query.where(FinTransaction.category_id == category_id)
    rows = session.exec(query.order_by(FinTransaction.tx_date.desc(), FinTransaction.id.desc())).all()
    currencies = account_currencies(session, user.id)
    return FinTransactionListResponse(date_from=start, date_to=end,
                                      transactions=[_tx_response(tx, currencies) for tx in rows])


@router.post("/transactions", response_model=FinTransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(body: FinTransactionFields, session: Session = Depends(get_session),
                       user: User = Depends(finance_user)):
    """Un movimiento escrito a mano (la alta rápida)."""
    tx = _new_transaction(session, user.id, body, "manual")
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return _tx_response(tx, account_currencies(session, user.id))


@router.post("/transactions/import", response_model=FinTransactionListResponse, status_code=status.HTTP_201_CREATED)
def import_transactions(body: FinTransactionImport, session: Session = Depends(get_session),
                        user: User = Depends(finance_user)):
    """Varios de una vez (el estado de cuenta pegado), ya revisados en la vista
    previa. Si uno no vale, no entra ninguno."""
    new = [_new_transaction(session, user.id, row, "import") for row in body.rows]
    for tx in new:
        session.add(tx)
    session.commit()
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
    merged = {field: changes.get(field, getattr(tx, field))
              for field in ("kind", "account_id", "category_id", "to_account_id")}
    _check_transaction(session, user.id, **merged)
    for field, value in changes.items():
        setattr(tx, field, value)
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return _tx_response(tx, account_currencies(session, user.id))


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(tx_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Borra un movimiento. Si salió de un fijo, ese cobro no vuelve a generarse."""
    session.delete(_own_transaction(session, user.id, tx_id))
    session.commit()
