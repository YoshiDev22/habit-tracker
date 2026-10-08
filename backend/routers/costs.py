"""
Pestaña Costos (plan maker, épica 24 Fase 3): gastos de cada proyecto, sus
categorías y el resumen de costo y margen. Todo empieza con
require_module(..., "maker"): sin el plan encendido, 403.

Las rutas literales (/categories, /summary, /import, /recurring) van antes que
/{cost_id}. Gastos repartidos y recurrentes (1.24): backend/recurring_costs.py.
"""
from datetime import date as date_type
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.costing import cost_total_cents, costs_summary, estimates_for_tasks, line_total_cents
from backend.database import get_session
from backend.models import CostCategory, Project, ProjectCost, ProjectFinance, RecurringCost, User
from backend.recurring_costs import create_cost_rows, generate_due, next_date, reshare, skip_past
from backend.routers.auth import require_module
from backend.schemas import (
    CostCategoryCreate,
    CostCategoryListResponse,
    CostCategoryResponse,
    CostCategoryUpdate,
    CostSplitUpdate,
    CostsSummaryResponse,
    EstimateDeviation,
    ProjectCostCreate,
    ProjectCostFields,
    ProjectCostImport,
    ProjectCostListResponse,
    ProjectCostResponse,
    ProjectCostUpdate,
    RecurringCostFields,
    RecurringCostListResponse,
    RecurringCostResponse,
    RecurringCostUpdate,
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


def _split_info(session: Session, user_id: int, costs: List[ProjectCost]) -> Dict[int, List[Dict]]:
    """Con qué proyectos va cada gasto repartido: split_id -> [{project_id, name, bp}]"""
    ids = {c.split_id for c in costs if c.split_id is not None}
    if not ids:
        return {}
    rows = session.exec(
        select(ProjectCost, Project.name).join(Project, Project.id == ProjectCost.project_id)
        .where(ProjectCost.user_id == user_id, ProjectCost.split_id.in_(ids)).order_by(ProjectCost.id)
    ).all()
    info: Dict[int, List[Dict]] = {}
    for row, name in rows:
        info.setdefault(row.split_id, []).append({"project_id": row.project_id, "name": name, "bp": row.split_bp})
    return info


def _cost_response(cost: ProjectCost, info: Optional[Dict[int, List[Dict]]] = None) -> ProjectCostResponse:
    group = (info or {}).get(cost.split_id, []) if cost.split_id is not None else []
    return ProjectCostResponse(
        id=cost.id, project_id=cost.project_id, category_id=cost.category_id,
        cost_date=cost.cost_date, concept=cost.concept, quantity=cost.quantity,
        unit_cost_cents=cost.unit_cost_cents,
        total_cents=cost_total_cents(cost),
        note=cost.note,
        split_id=cost.split_id, split_bp=cost.split_bp,
        group_total_cents=line_total_cents(cost.quantity, cost.unit_cost_cents) if cost.split_id is not None else None,
        split_with=group, recurring_id=cost.recurring_id,
    )


def _one_response(session: Session, user_id: int, cost: ProjectCost) -> ProjectCostResponse:
    return _cost_response(cost, _split_info(session, user_id, [cost]))


def _group(session: Session, user_id: int, cost: ProjectCost) -> List[ProjectCost]:
    """Las filas del mismo gasto: todas las de su reparto, o solo ella."""
    if cost.split_id is None:
        return [cost]
    return session.exec(select(ProjectCost).where(
        ProjectCost.user_id == user_id, ProjectCost.split_id == cost.split_id).order_by(ProjectCost.id)).all()


def _today(session: Session, user: User) -> date_type:
    # Importado aquí: backend.reports importa los reportes, que importan costing
    from backend.reports import local_today
    return local_today(session, user)


def _check_allocations(session: Session, user_id: int, allocations) -> List[Dict]:
    """Proyectos del usuario, que no sean "Sin asignar" y de una sola moneda."""
    currencies = set()
    for a in allocations:
        _own_project(session, user_id, a.project_id)
        currencies.add(_project_currency(session, user_id, a.project_id))
    if len(currencies) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Solo se reparte entre proyectos de la misma moneda: la app no convierte entre monedas")
    return [{"project_id": a.project_id, "bp": a.bp} for a in allocations]


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
    recurring = session.exec(select(func.count()).select_from(RecurringCost).where(
        RecurringCost.user_id == user.id, RecurringCost.category_id == category.id)).one()
    if recurring:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{category.name}' la usa {recurring} {'gasto recurrente' if recurring == 1 else 'gastos recurrentes'}: cámbialos de categoría antes de borrarla"
        )
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
def get_costs_summary(date_from: Optional[date_type] = None, date_to: Optional[date_type] = None,
                      session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """
    Resumen de la pestaña Costos: cada proyecto activo (y los archivados con
    costeo o gastos) con horas, mano de obra, gastos, costo, presupuesto y
    margen; el gasto por categoría; y los totales por moneda. Nunca se suman
    monedas distintas. Con date_from/date_to, el tiempo y los gastos de ese
    rango (el reporte de costos y la entrada 29 del BACKLOG).
    """
    ensure_cost_categories(session, user.id)
    generate_due(session, user.id, _today(session, user))
    return costs_summary(session, user.id, date_from, date_to)


@router.get("/estimates", response_model=EstimateDeviation)
def get_costs_estimates(session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """
    Tus estimados (épica 24, Fase 4): cuánto se desvía el usuario de lo que
    estima, con las tareas de todos sus proyectos (archivados y "Sin asignar"
    incluidos). La misma función que la ficha, así que las cifras cuadran.
    """
    return estimates_for_tasks(session, user.id)


# ==================== Gastos ====================

@router.get("", response_model=ProjectCostListResponse)
def get_project_costs(project_id: int, session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Los gastos de un proyecto, del más reciente al más antiguo"""
    _own_project(session, user.id, project_id)
    generate_due(session, user.id, _today(session, user))
    costs = session.exec(
        select(ProjectCost).where(ProjectCost.user_id == user.id, ProjectCost.project_id == project_id)
        .order_by(ProjectCost.cost_date.desc(), ProjectCost.id.desc())
    ).all()
    info = _split_info(session, user.id, costs)
    items = [_cost_response(c, info) for c in costs]
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


# ==================== Recurrentes ====================

def _own_recurring(session: Session, user_id: int, recurring_id: int) -> RecurringCost:
    rc = session.exec(select(RecurringCost).where(
        RecurringCost.id == recurring_id, RecurringCost.user_id == user_id)).first()
    if not rc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gasto recurrente no encontrado")
    return rc


def _recurring_response(session: Session, user_id: int, rc: RecurringCost) -> RecurringCostResponse:
    names = {p.id: p.name for p in session.exec(select(Project).where(Project.user_id == user_id)).all()}
    allocations = [{"project_id": a["project_id"], "name": names.get(a["project_id"], "(proyecto borrado)"),
                    "bp": a["bp"]} for a in rc.allocations or []]
    first = (rc.allocations or [{}])[0].get("project_id")
    return RecurringCostResponse(
        id=rc.id, category_id=rc.category_id, concept=rc.concept, quantity=rc.quantity,
        unit_cost_cents=rc.unit_cost_cents, total_cents=line_total_cents(rc.quantity, rc.unit_cost_cents),
        note=rc.note, frequency=rc.frequency, start_date=rc.start_date, end_date=rc.end_date,
        paused=rc.paused, next_date=None if rc.paused else next_date(rc), generated=rc.generated,
        currency=_project_currency(session, user_id, first) if first else "MXN", allocations=allocations,
    )


def _check_dates(start: date_type, end: Optional[date_type]) -> None:
    if end is not None and end < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="La fecha de fin no puede ser anterior al primer cobro")


@router.get("/recurring", response_model=RecurringCostListResponse)
def list_recurring_costs(session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Los gastos recurrentes, con su siguiente cobro. Antes, genera los que ya llegaron."""
    generate_due(session, user.id, _today(session, user))
    rows = session.exec(select(RecurringCost).where(RecurringCost.user_id == user.id)
                        .order_by(RecurringCost.paused, RecurringCost.concept, RecurringCost.id)).all()
    return RecurringCostListResponse(recurring=[_recurring_response(session, user.id, rc) for rc in rows])


@router.post("/recurring", response_model=RecurringCostResponse, status_code=status.HTTP_201_CREATED)
def create_recurring_cost(body: RecurringCostFields, session: Session = Depends(get_session),
                          user: User = Depends(maker_user)):
    """Un gasto recurrente nuevo. Si su primer cobro ya pasó, se generan los que
    ya llegaron (hasta 36 de una vez)."""
    _own_category(session, user.id, body.category_id)
    concept = body.concept.strip()
    if not concept:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El concepto no puede estar vacío")
    _check_dates(body.start_date, body.end_date)
    rc = RecurringCost(
        user_id=user.id, category_id=body.category_id, concept=concept, quantity=body.quantity,
        unit_cost_cents=body.unit_cost_cents, note=(body.note or "").strip() or None, frequency=body.frequency,
        start_date=body.start_date, end_date=body.end_date,
        allocations=_check_allocations(session, user.id, body.allocations),
    )
    session.add(rc)
    session.commit()
    generate_due(session, user.id, _today(session, user))
    session.refresh(rc)
    return _recurring_response(session, user.id, rc)


@router.patch("/recurring/{recurring_id}", response_model=RecurringCostResponse)
def update_recurring_cost(recurring_id: int, body: RecurringCostUpdate, session: Session = Depends(get_session),
                          user: User = Depends(maker_user)):
    """Cambia un recurrente. Solo afecta a los cobros siguientes: los ya
    generados se quedan como fueron. El primer cobro y la frecuencia ya no se
    cambian una vez que hubo cobros (crea otro). Al reanudarlo, los cobros del
    tiempo en pausa no se generan."""
    rc = _own_recurring(session, user.id, recurring_id)
    changes = body.model_dump(exclude_unset=True)
    if rc.generated and (("start_date" in changes and changes["start_date"] != rc.start_date)
                         or ("frequency" in changes and changes["frequency"] != rc.frequency)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Ya hubo cobros: el primer cobro y la frecuencia no se cambian. Termínalo y crea otro.")
    for field in ("category_id", "concept", "quantity", "unit_cost_cents", "frequency", "start_date",
                  "paused", "allocations"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ese dato no puede quedar vacío")
    if changes.get("category_id") is not None:
        _own_category(session, user.id, changes["category_id"])
    if "concept" in changes:
        changes["concept"] = changes["concept"].strip()
        if not changes["concept"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El concepto no puede estar vacío")
    if "note" in changes:
        changes["note"] = (changes["note"] or "").strip() or None
    if "allocations" in changes:
        changes["allocations"] = _check_allocations(session, user.id, body.allocations)
    resuming = rc.paused and changes.get("paused") is False
    for field, value in changes.items():
        setattr(rc, field, value)
    _check_dates(rc.start_date, rc.end_date)
    if resuming:
        skip_past(rc, _today(session, user))
    session.add(rc)
    session.commit()
    generate_due(session, user.id, _today(session, user))
    session.refresh(rc)
    return _recurring_response(session, user.id, rc)


@router.delete("/recurring/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_cost(recurring_id: int, session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Deja de cobrarlo. Los gastos que ya generó se quedan (sin el 🔁)."""
    rc = _own_recurring(session, user.id, recurring_id)
    for cost in session.exec(select(ProjectCost).where(
            ProjectCost.user_id == user.id, ProjectCost.recurring_id == rc.id)).all():
        cost.recurring_id = None
        session.add(cost)
    session.delete(rc)
    session.commit()


@router.patch("/{cost_id}", response_model=ProjectCostResponse)
def update_project_cost(cost_id: int, body: ProjectCostUpdate, session: Session = Depends(get_session),
                        user: User = Depends(maker_user)):
    """Edita un gasto celda por celda. Si está repartido, el cambio es del gasto
    entero: todas sus partes, con los montos repartidos otra vez."""
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
    rows = _group(session, user.id, cost)
    for row in rows:
        for field, value in changes.items():
            setattr(row, field, value)
    if "quantity" in changes or "unit_cost_cents" in changes:
        reshare(rows)
    for row in rows:
        session.add(row)
    session.commit()
    session.refresh(cost)
    return _one_response(session, user.id, cost)


@router.put("/{cost_id}/split", response_model=ProjectCostResponse)
def split_project_cost(cost_id: int, body: CostSplitUpdate, session: Session = Depends(get_session),
                       user: User = Depends(maker_user)):
    """
    Reparte un gasto entre proyectos de la misma moneda (o cambia su reparto).
    Con un solo proyecto al 100 % deja de estar repartido y pasa a ese
    proyecto. Devuelve la parte del proyecto donde se editó, o la primera si
    ese proyecto ya no está en el reparto.
    """
    cost = _own_cost(session, user.id, cost_id)
    allocations = _check_allocations(session, user.id, body.allocations)
    rows = _group(session, user.id, cost)
    fields = dict(category_id=cost.category_id, cost_date=cost.cost_date, concept=cost.concept,
                  quantity=cost.quantity, unit_cost_cents=cost.unit_cost_cents, note=cost.note)
    recurring_id = cost.recurring_id
    for row in rows:
        session.delete(row)
    session.flush()
    new = create_cost_rows(session, user.id, fields, allocations, recurring_id=recurring_id)
    session.commit()
    keep = next((r for r in new if r.project_id == cost.project_id), new[0])
    session.refresh(keep)
    return _one_response(session, user.id, keep)


@router.delete("/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_cost(cost_id: int, session: Session = Depends(get_session), user: User = Depends(maker_user)):
    """Borra un gasto; si está repartido, el gasto entero (todas sus partes).
    Si salió de un recurrente, no vuelve a generarse."""
    for row in _group(session, user.id, _own_cost(session, user.id, cost_id)):
        session.delete(row)
    session.commit()
