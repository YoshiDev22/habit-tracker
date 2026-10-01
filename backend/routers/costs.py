"""
Pestaña Costos (plan maker, épica 24 Fase 3): gastos de cada proyecto, sus
categorías y el resumen de costo y margen. Todo empieza con
require_module(..., "maker"): sin el plan encendido, 403.

Las rutas literales (/categories, /summary, /import) van antes que /{cost_id}.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.costing import costs_cents_by_project, labor_cents, line_total_cents
from backend.database import get_session
from backend.models import CostCategory, PomodoroSession, Project, ProjectCost, ProjectFinance, User
from backend.routers.auth import require_module
from backend.schemas import (
    CostCategoryCreate,
    CostCategoryListResponse,
    CostCategoryResponse,
    CostCategoryUpdate,
    CostsCategorySummary,
    CostsCurrencyTotal,
    CostsProjectSummary,
    CostsSummaryResponse,
    ProjectCostCreate,
    ProjectCostFields,
    ProjectCostImport,
    ProjectCostListResponse,
    ProjectCostResponse,
    ProjectCostUpdate,
)

router = APIRouter(tags=["costs"])

# Las que recibe cada cuenta al entrar por primera vez; después son suyas
DEFAULT_COST_CATEGORIES = [
    ("Material", "#e67e22"),
    ("Licencia / software", "#3498db"),
    ("Servicio", "#27ae60"),
    ("IA", "#9b59b6"),
    ("Otro", "#95a5a6"),
]


def maker_user(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """El usuario del token, si tiene el plan maker encendido (si no, 403)"""
    require_module(session, current_user, "maker")
    return current_user


def ensure_cost_categories(session: Session, user_id: int) -> None:
    """Las cinco de inicio, una sola vez: sin ninguna, la cuenta nunca entró
    (la última no se puede borrar). Idempotente; la restricción única por
    nombre frena la doble siembra de dos peticiones a la vez."""
    exists = session.exec(select(CostCategory.id).where(CostCategory.user_id == user_id)).first()
    if exists is not None:
        return
    for order, (name, color) in enumerate(DEFAULT_COST_CATEGORIES):
        session.add(CostCategory(user_id=user_id, name=name, color=color, order=order))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()


def _own_category(session: Session, user_id: int, category_id: int) -> CostCategory:
    category = session.exec(
        select(CostCategory).where(CostCategory.id == category_id, CostCategory.user_id == user_id)
    ).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    return category


def _own_project(session: Session, user_id: int, project_id: int) -> Project:
    project = session.exec(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    ).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    if project.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{project.name}' junta las tareas sin proyecto y no lleva gastos"
        )
    return project


def _own_cost(session: Session, user_id: int, cost_id: int) -> ProjectCost:
    cost = session.exec(
        select(ProjectCost).where(ProjectCost.id == cost_id, ProjectCost.user_id == user_id)
    ).first()
    if not cost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto no encontrado")
    return cost


def _clean_category_name(session: Session, user_id: int, value: str, exclude_id: Optional[int] = None) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El nombre no puede estar vacío")
    query = select(CostCategory.id).where(CostCategory.user_id == user_id, CostCategory.name == name)
    if exclude_id is not None:
        query = query.where(CostCategory.id != exclude_id)
    if session.exec(query).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya tienes una categoría llamada '{name}'")
    return name


def _cost_counts(session: Session, user_id: int) -> Dict[int, int]:
    return dict(session.exec(
        select(ProjectCost.category_id, func.count())
        .where(ProjectCost.user_id == user_id)
        .group_by(ProjectCost.category_id)
    ).all())


def _category_response(category: CostCategory, counts: Dict[int, int]) -> CostCategoryResponse:
    return CostCategoryResponse(
        id=category.id, name=category.name, color=category.color, order=category.order,
        cost_count=counts.get(category.id, 0),
    )


def _cost_response(cost: ProjectCost) -> ProjectCostResponse:
    return ProjectCostResponse(
        id=cost.id, project_id=cost.project_id, category_id=cost.category_id,
        cost_date=cost.cost_date, concept=cost.concept, quantity=cost.quantity,
        unit_cost_cents=cost.unit_cost_cents,
        total_cents=line_total_cents(cost.quantity, cost.unit_cost_cents),
        note=cost.note,
    )


def _project_currency(session: Session, user_id: int, project_id: int) -> str:
    row = session.exec(
        select(ProjectFinance.currency).where(ProjectFinance.user_id == user_id, ProjectFinance.project_id == project_id)
    ).first()
    return row or "MXN"


def _new_cost(session: Session, user_id: int, project_id: int, fields: ProjectCostFields) -> ProjectCost:
    _own_category(session, user_id, fields.category_id)
    concept = fields.concept.strip()
    if not concept:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El concepto no puede estar vacío")
    return ProjectCost(
        user_id=user_id, project_id=project_id, category_id=fields.category_id,
        cost_date=fields.cost_date, concept=concept, quantity=fields.quantity,
        unit_cost_cents=fields.unit_cost_cents, note=(fields.note or "").strip() or None,
    )


# ==================== Categorías ====================

@router.get("/categories", response_model=CostCategoryListResponse)
def get_cost_categories(session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Categorías de gasto del usuario, en su orden. La primera vez, las cinco de inicio."""
    ensure_cost_categories(session, user.id)
    categories = session.exec(
        select(CostCategory).where(CostCategory.user_id == user.id).order_by(CostCategory.order, CostCategory.id)
    ).all()
    counts = _cost_counts(session, user.id)
    return CostCategoryListResponse(categories=[_category_response(c, counts) for c in categories])


@router.post("/categories", response_model=CostCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_cost_category(body: CostCategoryCreate, session: Session = Depends(get_session),
                         user: User = Depends(maker_user)):
    """Una categoría nueva, al final"""
    ensure_cost_categories(session, user.id)
    last = session.exec(select(func.max(CostCategory.order)).where(CostCategory.user_id == user.id)).one()
    category = CostCategory(
        user_id=user.id, name=_clean_category_name(session, user.id, body.name),
        color=body.color, order=(last or 0) + 1,
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return _category_response(category, {})


@router.patch("/categories/{category_id}", response_model=CostCategoryResponse)
def update_cost_category(category_id: int, body: CostCategoryUpdate, session: Session = Depends(get_session),
                         user: User = Depends(maker_user)):
    """Renombrar, recolorear u ordenar. Sus gastos la siguen: van por id."""
    category = _own_category(session, user.id, category_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        category.name = _clean_category_name(session, user.id, changes["name"], exclude_id=category.id)
    if "color" in changes:
        category.color = changes["color"]
    if changes.get("order") is not None:
        category.order = changes["order"]
    session.add(category)
    session.commit()
    session.refresh(category)
    return _category_response(category, _cost_counts(session, user.id))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cost_category(category_id: int, session: Session = Depends(get_session),
                         user: User = Depends(maker_user)):
    """Borra una categoría sin gastos. Con gastos, 409: primero se pasan a otra
    (así ningún gasto queda sin categoría). La última tampoco se borra."""
    category = _own_category(session, user.id, category_id)
    count = _cost_counts(session, user.id).get(category.id, 0)
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{category.name}' tiene {count} {'gasto' if count == 1 else 'gastos'}: cámbialos de categoría antes de borrarla"
        )
    total = session.exec(select(func.count()).select_from(CostCategory).where(CostCategory.user_id == user.id)).one()
    if total <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Necesitas al menos una categoría")
    session.delete(category)
    session.commit()


# ==================== Resumen ====================

@router.get("/summary", response_model=CostsSummaryResponse)
def get_costs_summary(session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """
    Resumen de la pestaña Costos: cada proyecto activo (y los archivados con
    costeo o gastos) con horas, mano de obra, gastos, costo, presupuesto y
    margen; el gasto por categoría; y los totales por moneda. Nunca se suman
    monedas distintas.
    """
    ensure_cost_categories(session, user.id)
    projects = session.exec(
        select(Project).where(Project.user_id == user.id, Project.is_system == False)  # noqa: E712
        .order_by(Project.order, Project.id)
    ).all()
    finances = {f.project_id: f for f in session.exec(select(ProjectFinance).where(ProjectFinance.user_id == user.id)).all()}
    costs = session.exec(select(ProjectCost).where(ProjectCost.user_id == user.id)).all()
    seconds = dict(session.exec(
        select(PomodoroSession.project_id, func.sum(PomodoroSession.duration_seconds))
        .where(PomodoroSession.user_id == user.id, PomodoroSession.mode == "focus")
        .group_by(PomodoroSession.project_id)
    ).all())
    costs_by_project = costs_cents_by_project(session, user.id)

    rows: List[CostsProjectSummary] = []
    currency_of: Dict[int, str] = {}
    for p in projects:
        finance = finances.get(p.id)
        costs_cents = costs_by_project.get(p.id, 0)
        if not p.is_active and finance is None and not costs_cents:
            continue
        currency = finance.currency if finance else "MXN"
        currency_of[p.id] = currency
        total_seconds = seconds.get(p.id, 0) or 0
        rate = finance.hourly_rate_cents if finance else None
        labor = labor_cents(total_seconds, rate)
        total_cost = (labor or 0) + costs_cents
        budget = finance.budget_cents if finance else None
        budget_minutes = finance.budget_minutes if finance else None
        rows.append(CostsProjectSummary(
            project_id=p.id, name=p.name, color=p.color, is_active=p.is_active, currency=currency,
            total_seconds=total_seconds, hourly_rate_cents=rate, labor_cents=labor,
            costs_cents=costs_cents, total_cost_cents=total_cost, budget_cents=budget,
            margin_cents=budget - total_cost if budget is not None else None,
            is_quote=bool(budget or budget_minutes) and total_seconds == 0,
        ))

    categories = {c.id: c for c in session.exec(select(CostCategory).where(CostCategory.user_id == user.id)).all()}
    by_category: Dict[tuple, int] = {}
    for cost in costs:
        if cost.project_id not in currency_of:
            continue
        key = (cost.category_id, currency_of[cost.project_id])
        by_category[key] = by_category.get(key, 0) + line_total_cents(cost.quantity, cost.unit_cost_cents)
    category_rows = sorted(
        (CostsCategorySummary(category_id=cid, name=categories[cid].name, color=categories[cid].color,
                              currency=currency, cents=cents)
         for (cid, currency), cents in by_category.items() if cid in categories),
        key=lambda c: (c.currency, -c.cents, c.name),
    )

    totals: Dict[str, CostsCurrencyTotal] = {}
    for row in rows:
        t = totals.setdefault(row.currency, CostsCurrencyTotal(
            currency=row.currency, labor_cents=0, costs_cents=0, total_cost_cents=0, budget_cents=0))
        t.labor_cents += row.labor_cents or 0
        t.costs_cents += row.costs_cents
        t.total_cost_cents += row.total_cost_cents
        t.budget_cents += row.budget_cents or 0
    return CostsSummaryResponse(projects=rows, categories=category_rows,
                                totals=sorted(totals.values(), key=lambda t: t.currency))


# ==================== Gastos ====================

@router.get("", response_model=ProjectCostListResponse)
def get_project_costs(project_id: int, session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Los gastos de un proyecto, del más reciente al más antiguo"""
    _own_project(session, user.id, project_id)
    costs = session.exec(
        select(ProjectCost).where(ProjectCost.user_id == user.id, ProjectCost.project_id == project_id)
        .order_by(ProjectCost.cost_date.desc(), ProjectCost.id.desc())
    ).all()
    items = [_cost_response(c) for c in costs]
    return ProjectCostListResponse(costs=items, total_cents=sum(c.total_cents for c in items),
                                   currency=_project_currency(session, user.id, project_id))


@router.post("", response_model=ProjectCostResponse, status_code=status.HTTP_201_CREATED)
def create_project_cost(body: ProjectCostCreate, session: Session = Depends(get_session),
                        user: User = Depends(maker_user)):
    """Un gasto nuevo (la fila nueva de la hoja)"""
    _own_project(session, user.id, body.project_id)
    cost = _new_cost(session, user.id, body.project_id, body)
    session.add(cost)
    session.commit()
    session.refresh(cost)
    return _cost_response(cost)


@router.post("/import", response_model=ProjectCostListResponse, status_code=status.HTTP_201_CREATED)
def import_project_costs(body: ProjectCostImport, session: Session = Depends(get_session),
                         user: User = Depends(maker_user)):
    """Varios gastos de una vez (pegados de Excel o Sheets, o de un CSV), ya
    revisados en la vista previa. Si uno no vale, no entra ninguno."""
    _own_project(session, user.id, body.project_id)
    new = [_new_cost(session, user.id, body.project_id, row) for row in body.rows]
    for cost in new:
        session.add(cost)
    session.commit()
    for cost in new:
        session.refresh(cost)
    items = [_cost_response(c) for c in new]
    return ProjectCostListResponse(costs=items, total_cents=sum(c.total_cents for c in items),
                                   currency=_project_currency(session, user.id, body.project_id))


@router.patch("/{cost_id}", response_model=ProjectCostResponse)
def update_project_cost(cost_id: int, body: ProjectCostUpdate, session: Session = Depends(get_session),
                        user: User = Depends(maker_user)):
    """Edita un gasto celda por celda"""
    cost = _own_cost(session, user.id, cost_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("category_id") is not None:
        _own_category(session, user.id, changes["category_id"])
    if "concept" in changes:
        concept = (changes["concept"] or "").strip()
        if not concept:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El concepto no puede estar vacío")
        changes["concept"] = concept
    if "note" in changes:
        changes["note"] = (changes["note"] or "").strip() or None
    for field in ("category_id", "cost_date", "quantity", "unit_cost_cents"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ese dato no puede quedar vacío")
    for field, value in changes.items():
        setattr(cost, field, value)
    session.add(cost)
    session.commit()
    session.refresh(cost)
    return _cost_response(cost)


@router.delete("/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_cost(cost_id: int, session: Session = Depends(get_session), user: User = Depends(maker_user)):
    session.delete(_own_cost(session, user.id, cost_id))
    session.commit()
