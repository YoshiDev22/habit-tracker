"""
/api/finance/budget: el presupuesto mensual de Finanzas (épica 37, fase C).

Es solo el plan: el ingreso que se espera y lo que se piensa gastar, en grupos con
su parte del ingreso. Nada de aquí crea movimientos; un renglón enlazado a un fijo
(`recurring_id`) solo dice que ese gasto ya se anota solo. Todo tras finance_user,
como el resto de Finanzas.
"""
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import FinBudgetGroup, FinBudgetItem, User
from backend.routers.finance import (_clean_name, _conflict, _not_found, _own_category, _own_recurring,
                                     _unprocessable, finance_user)
from backend.schemas import (FIN_BUDGET_MAX_GROUPS, FIN_BUDGET_MAX_ITEMS, FIN_BUDGET_TEMPLATES,
                             FinBudgetGroupFields, FinBudgetGroupResponse, FinBudgetGroupUpdate, FinBudgetItemFields,
                             FinBudgetItemResponse, FinBudgetItemUpdate, FinBudgetResponse, FinBudgetTemplate)

router = APIRouter()


def _own_group(session: Session, user_id: int, group_id: int) -> FinBudgetGroup:
    group = session.exec(select(FinBudgetGroup).where(FinBudgetGroup.id == group_id,
                                                      FinBudgetGroup.user_id == user_id)).first()
    if not group:
        raise _not_found("Grupo del presupuesto")
    return group


def _own_item(session: Session, user_id: int, item_id: int) -> FinBudgetItem:
    item = session.exec(select(FinBudgetItem).where(FinBudgetItem.id == item_id,
                                                    FinBudgetItem.user_id == user_id)).first()
    if not item:
        raise _not_found("Línea del presupuesto")
    return item


def _count(session: Session, model, user_id: int) -> int:
    return session.exec(select(func.count()).select_from(model).where(model.user_id == user_id)).one()


def _next_order(session: Session, model, user_id: int) -> int:
    top = session.exec(select(func.max(model.order)).where(model.user_id == user_id)).one()
    return 0 if top is None else top + 1


def _budget(session: Session, user_id: int) -> FinBudgetResponse:
    groups = session.exec(select(FinBudgetGroup).where(FinBudgetGroup.user_id == user_id)
                          .order_by(FinBudgetGroup.order, FinBudgetGroup.id)).all()
    items = session.exec(select(FinBudgetItem).where(FinBudgetItem.user_id == user_id)
                         .order_by(FinBudgetItem.order, FinBudgetItem.id)).all()
    return FinBudgetResponse(
        groups=[FinBudgetGroupResponse(id=g.id, name=g.name, percent_bp=g.percent_bp, order=g.order) for g in groups],
        items=[_item_response(i) for i in items])


def _item_response(item: FinBudgetItem) -> FinBudgetItemResponse:
    return FinBudgetItemResponse(id=item.id, kind=item.kind, group_id=item.group_id, name=item.name,
                                 amount_cents=item.amount_cents, note=item.note, category_id=item.category_id,
                                 recurring_id=item.recurring_id, order=item.order)


def _check_links(session: Session, user_id: int, item: FinBudgetItem) -> None:
    """Un gasto va en un grupo y un ingreso, sin grupo; la categoría y el fijo, del
    mismo tipo; un fijo, en un solo renglón."""
    if item.kind == "expense":
        if item.group_id is None:
            raise _unprocessable("Un gasto del presupuesto va en un grupo")
        _own_group(session, user_id, item.group_id)
    elif item.group_id is not None:
        raise _unprocessable("Un ingreso del presupuesto no va en un grupo")
    if item.category_id is not None:
        category = _own_category(session, user_id, item.category_id)
        if category.kind != item.kind:
            raise _unprocessable(f"'{category.name}' es de {'ingresos' if category.kind == 'income' else 'gastos'}")
    if item.recurring_id is not None:
        rc = _own_recurring(session, user_id, item.recurring_id)
        if rc.kind != item.kind:
            raise _unprocessable(f"'{rc.concept}' es un fijo de {'ingreso' if rc.kind == 'income' else 'gasto'}")
        other = session.exec(select(FinBudgetItem.id).where(
            FinBudgetItem.user_id == user_id, FinBudgetItem.recurring_id == rc.id,
            FinBudgetItem.id != (item.id or 0))).first()
        if other:
            raise _conflict(f"'{rc.concept}' ya está en el presupuesto")


def _clean_note(value: Optional[str]) -> Optional[str]:
    note = (value or "").strip()
    return note or None


@router.get("", response_model=FinBudgetResponse)
def get_budget(session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Los grupos y los renglones, en su orden."""
    return _budget(session, user.id)


# ---------- Grupos ----------

@router.post("/groups", response_model=FinBudgetGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(body: FinBudgetGroupFields, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    if _count(session, FinBudgetGroup, user.id) >= FIN_BUDGET_MAX_GROUPS:
        raise _conflict(f"Hasta {FIN_BUDGET_MAX_GROUPS} grupos en el presupuesto")
    group = FinBudgetGroup(user_id=user.id, name=_clean_name(body.name), percent_bp=body.percent_bp,
                           order=_next_order(session, FinBudgetGroup, user.id))
    session.add(group)
    session.commit()
    session.refresh(group)
    return FinBudgetGroupResponse(id=group.id, name=group.name, percent_bp=group.percent_bp, order=group.order)


@router.post("/template", response_model=FinBudgetResponse, status_code=status.HTTP_201_CREATED)
def apply_template(body: FinBudgetTemplate, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Crea los grupos de una referencia, después de los que ya haya."""
    groups = FIN_BUDGET_TEMPLATES[body.template]
    if _count(session, FinBudgetGroup, user.id) + len(groups) > FIN_BUDGET_MAX_GROUPS:
        raise _conflict(f"Hasta {FIN_BUDGET_MAX_GROUPS} grupos en el presupuesto")
    order = _next_order(session, FinBudgetGroup, user.id)
    for k, (name, percent) in enumerate(groups):
        session.add(FinBudgetGroup(user_id=user.id, name=name, percent_bp=percent, order=order + k))
    session.commit()
    return _budget(session, user.id)


@router.patch("/groups/{group_id}", response_model=FinBudgetGroupResponse)
def update_group(group_id: int, body: FinBudgetGroupUpdate, session: Session = Depends(get_session),
                 user: User = Depends(finance_user)):
    group = _own_group(session, user.id, group_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"])
    for field, value in changes.items():
        setattr(group, field, value)
    session.add(group)
    session.commit()
    session.refresh(group)
    return FinBudgetGroupResponse(id=group.id, name=group.name, percent_bp=group.percent_bp, order=group.order)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Borra el grupo con sus renglones. Los fijos enlazados se quedan: siguen cobrándose."""
    group = _own_group(session, user.id, group_id)
    for item in session.exec(select(FinBudgetItem).where(FinBudgetItem.user_id == user.id,
                                                         FinBudgetItem.group_id == group.id)).all():
        session.delete(item)
    session.delete(group)
    session.commit()


# ---------- Renglones ----------

@router.post("/items", response_model=FinBudgetItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(body: FinBudgetItemFields, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    if _count(session, FinBudgetItem, user.id) >= FIN_BUDGET_MAX_ITEMS:
        raise _conflict(f"Hasta {FIN_BUDGET_MAX_ITEMS} renglones en el presupuesto")
    item = FinBudgetItem(user_id=user.id, kind=body.kind, group_id=body.group_id, name=_clean_name(body.name),
                         amount_cents=body.amount_cents, note=_clean_note(body.note), category_id=body.category_id,
                         recurring_id=body.recurring_id, order=_next_order(session, FinBudgetItem, user.id))
    _check_links(session, user.id, item)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_response(item)


@router.patch("/items/{item_id}", response_model=FinBudgetItemResponse)
def update_item(item_id: int, body: FinBudgetItemUpdate, session: Session = Depends(get_session),
                user: User = Depends(finance_user)):
    item = _own_item(session, user.id, item_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "amount_cents", "order", "group_id"):
        if field in changes and changes[field] is None:
            del changes[field]
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"])
    if "note" in changes:
        changes["note"] = _clean_note(changes["note"])
    for field, value in changes.items():
        setattr(item, field, value)
    _check_links(session, user.id, item)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_response(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: Session = Depends(get_session), user: User = Depends(finance_user)):
    """Quita el renglón; su fijo, si tenía, sigue cobrándose."""
    session.delete(_own_item(session, user.id, item_id))
    session.commit()
