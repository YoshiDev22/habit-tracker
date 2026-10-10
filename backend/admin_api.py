"""
La API del panel de administración (1.27, Fase 1: solo lectura). Solo la monta
backend/admin_main.py, detrás de require_admin; la app pública no la importa.

Gestión, no vigilancia: estas consultas CUENTAN filas de los datos de cada
cuenta, nunca leen sus campos (títulos, nombres, conceptos, notas, textos de
reportes). Lo único escrito por un usuario que sale de aquí son sus reportes de
problemas, que escribió para Yoshio. Los correos van enmascarados en las listas;
el completo, solo al pedir el de una cuenta.
"""
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field as PydanticField, StrictBool, StrictInt
from sqlalchemy import func
from sqlmodel import Session, SQLModel, select

from backend.database import get_session
from backend.ai import ai_config
from backend.models import (AdminAction, AiCall, AiGrant, Board, Feedback, Habit, PomodoroSession, ProjectCost,
                            Report, Task, User, UserModule, utc_now_naive)
from backend.report_ai import ai_usage as account_ai_usage, extra_today
from backend.modules import MODULES, resolve as resolve_module

router = APIRouter()

# Lo que se cuenta de cada cuenta: solo cuántas filas tiene en cada tabla
COUNTED = {"boards": Board, "tasks": Task, "habits": Habit, "sessions": PomodoroSession,
           "costs": ProjectCost, "reports": Report}
FEEDBACK_STATUSES = ("open", "reviewed", "closed")


def record_action(session: Session, admin: str, action: str, account_id: Optional[int],
                  before: Optional[Dict], after: Optional[Dict]) -> AdminAction:
    """Anota una acción en la bitácora, en la misma transacción que el cambio (no
    hace commit: si el cambio falla, tampoco queda anotado)."""
    row = AdminAction(admin_email=admin, action=action, account_id=account_id, before=before, after=after)
    session.add(row)
    return row


def mask_email(email: str) -> str:
    """y•••@gmail.com: la primera letra y el dominio."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def _counts_by_user(session: Session, model) -> Dict[int, int]:
    return dict(session.exec(select(model.user_id, func.count(model.id)).group_by(model.user_id)).all())


def _modules_by_user(session: Session) -> Dict[int, Dict]:
    rows = defaultdict(dict)
    for row in session.exec(select(UserModule)).all():
        rows[row.user_id][row.module] = row
    return rows


def _module_state(rows: Dict) -> Dict:
    return {name: resolve_module(name, getattr(rows.get(name), "enabled", None), getattr(rows.get(name), "allowed", None))
            for name in MODULES}


def _ai_by_user(session: Session, since) -> Dict[int, Dict]:
    """Llamadas a la IA desde `since`, por cuenta: buenas, fallidas y tokens."""
    out = defaultdict(lambda: {"ok": 0, "failed": 0, "tokens": 0})
    for user_id, ok, inp, outp in session.exec(select(AiCall.user_id, AiCall.ok, AiCall.input_tokens,
                                                      AiCall.output_tokens).where(AiCall.created_at >= since)).all():
        row = out[user_id]
        row["ok" if ok else "failed"] += 1
        row["tokens"] += (inp or 0) + (outp or 0)
    return out


@router.get("/summary")
def summary(session: Session = Depends(get_session)) -> dict:
    now = utc_now_naive()
    users = session.exec(select(User.created_at, User.last_seen_at, User.delete_after)).all()

    def since(days, column):
        return sum(1 for u in users if u[column] is not None and u[column] >= now - timedelta(days=days))

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ai_today = Counter(ok for ok in session.exec(select(AiCall.ok).where(AiCall.created_at >= today)).all())
    open_feedback = session.exec(select(func.count(Feedback.id)).where(Feedback.status == "open")).one()
    return {
        "accounts": len(users),
        "new_7d": since(7, 0), "new_30d": since(30, 0),
        "active_7d": since(7, 1), "active_30d": since(30, 1),
        "unknown_signup": sum(1 for u in users if u[0] is None),
        "scheduled_deletion": sum(1 for u in users if u[2] is not None),
        "feedback_open": open_feedback,
        "ai_today": {"ok": ai_today.get(True, 0), "failed": ai_today.get(False, 0)},
    }


@router.get("/accounts")
def accounts(session: Session = Depends(get_session)) -> dict:
    now = utc_now_naive()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    counts = {name: _counts_by_user(session, model) for name, model in COUNTED.items()}
    modules = _modules_by_user(session)
    ai_today, ai_month = _ai_by_user(session, today), _ai_by_user(session, month)
    rows = []
    for user in session.exec(select(User)).all():
        rows.append({
            "id": user.id,
            "email": mask_email(user.email),
            "created_at": user.created_at,
            "last_seen_at": user.last_seen_at,
            "delete_after": user.delete_after,
            "modules": _module_state(modules.get(user.id, {})),
            "counts": {name: counts[name].get(user.id, 0) for name in COUNTED},
            "ai": {"today": dict(ai_today.get(user.id, {"ok": 0, "failed": 0, "tokens": 0})),
                   "month": dict(ai_month.get(user.id, {"ok": 0, "failed": 0, "tokens": 0}))},
        })
    # Lo más reciente arriba; las que nunca se vieron, al final
    rows.sort(key=lambda r: (r["last_seen_at"] is None, -(r["last_seen_at"].timestamp() if r["last_seen_at"] else 0)))
    return {"accounts": rows}


@router.get("/accounts/{user_id}/email")
def account_email(user_id: int, session: Session = Depends(get_session)) -> dict:
    """El correo completo de una cuenta, solo cuando se pide (al tocarlo en el panel)."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe esa cuenta")
    return {"id": user.id, "email": user.email}


@router.get("/ai")
def ai_usage(days: int = Query(default=30, ge=1, le=90), session: Session = Depends(get_session)) -> dict:
    """Llamadas a la IA por día y por contador, y los errores más comunes."""
    since = utc_now_naive().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    by_day = defaultdict(lambda: {"ok": 0, "failed": 0, "tokens": 0})
    errors = Counter()
    for created, purpose, ok, error, inp, outp in session.exec(
            select(AiCall.created_at, AiCall.purpose, AiCall.ok, AiCall.error, AiCall.input_tokens,
                   AiCall.output_tokens).where(AiCall.created_at >= since)).all():
        row = by_day[(created.date().isoformat(), purpose)]
        row["ok" if ok else "failed"] += 1
        row["tokens"] += (inp or 0) + (outp or 0)
        if not ok and error:
            errors[error[:120]] += 1
    return {
        "since": since.date().isoformat(),
        "days": [{"date": d, "purpose": p, **v} for (d, p), v in sorted(by_day.items())],
        "errors": [{"error": e, "count": n} for e, n in errors.most_common(10)],
    }


@router.get("/feedback")
def feedback(status_filter: Optional[str] = Query(default=None, alias="status"),
             session: Session = Depends(get_session)) -> dict:
    """Los problemas reportados, el más nuevo arriba (hasta 200)."""
    if status_filter is not None and status_filter not in FEEDBACK_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"status debe ser uno de: {', '.join(FEEDBACK_STATUSES)}")
    query = select(Feedback, User.email).join(User, User.id == Feedback.user_id)
    if status_filter:
        query = query.where(Feedback.status == status_filter)
    rows = session.exec(query.order_by(Feedback.created_at.desc(), Feedback.id.desc()).limit(200)).all()
    return {"feedback": [{
        "id": f.id, "created_at": f.created_at, "status": f.status, "text": f.text, "details": f.details,
        "admin_note": f.admin_note, "account": {"id": f.user_id, "email": mask_email(email)},
    } for f, email in rows]}


@router.get("/actions")
def actions(account_id: Optional[int] = None, session: Session = Depends(get_session)) -> dict:
    """La bitácora, la más nueva arriba (hasta 200); con account_id, solo esa cuenta."""
    query = select(AdminAction)
    if account_id is not None:
        query = query.where(AdminAction.account_id == account_id)
    rows = session.exec(query.order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(200)).all()
    return {"actions": [{"id": a.id, "created_at": a.created_at, "admin": a.admin_email, "action": a.action,
                         "account_id": a.account_id, "before": a.before, "after": a.after} for a in rows]}


# ---------- Acciones (Fase 2) ----------
# Cada una pide el administrador (lo pone admin_main en request.state) y deja su
# fila en la bitácora en la misma transacción.

def _admin(request: Request) -> str:
    return request.state.admin


def _account(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe esa cuenta")
    return user


class ModuleAccess(SQLModel):
    allowed: StrictBool


# Los módulos que se dan y se quitan: los que no son de todos por defecto
GRANTABLE = tuple(name for name, default in MODULES.items() if not default["allowed"])


@router.put("/accounts/{user_id}/modules/{module}")
def set_module_access(user_id: int, module: str, body: ModuleAccess, request: Request,
                      session: Session = Depends(get_session)) -> dict:
    """Dar o quitar el acceso a un módulo (Maker, IA). Quitarlo lo apaga sin olvidar
    lo que el usuario había elegido, como scripts/grant_module.py (que se queda para
    emergencias)."""
    if module not in MODULES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe ese módulo")
    if module not in GRANTABLE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese módulo es de todas las cuentas")
    user = _account(session, user_id)
    row = session.exec(select(UserModule).where(UserModule.user_id == user.id, UserModule.module == module)).first()
    before = resolve_module(module, getattr(row, "enabled", None), getattr(row, "allowed", None))
    if row is None:
        row = UserModule(user_id=user.id, module=module)
    row.allowed = body.allowed
    session.add(row)
    after = resolve_module(module, row.enabled, row.allowed)
    if before != after:
        record_action(session, _admin(request), "module", user.id, {module: before}, {module: after})
    session.commit()
    return {"module": module, **after}


AI_POOLS = ("report", "costs")
AI_GRANT_MAX = 50   # por cuenta, contador y día: un tope para que un error de dedo no sea 5000


class AiGrantCreate(SQLModel):
    pool: str
    extra: StrictInt = PydanticField(ge=1, le=AI_GRANT_MAX)


@router.get("/accounts/{user_id}/ai")
def account_ai(user_id: int, session: Session = Depends(get_session)) -> dict:
    """Uso de la IA de hoy de una cuenta, por contador, con lo extra que se le dio."""
    user = _account(session, user_id)
    config = ai_config()
    return {"configured": config is not None,
            "pools": {pool: {**account_ai_usage(session, user.id, pool, config),
                             "extra_today": extra_today(session, user.id, pool)} for pool in AI_POOLS}}


@router.post("/accounts/{user_id}/ai-grants")
def grant_ai(user_id: int, body: AiGrantCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    """Textos de IA extra solo por hoy (día UTC) en un contador. Dar más el mismo día
    suma, hasta AI_GRANT_MAX en total."""
    if body.pool not in AI_POOLS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"pool debe ser uno de: {', '.join(AI_POOLS)}")
    user = _account(session, user_id)
    today = utc_now_naive().date()
    grant = session.exec(select(AiGrant).where(AiGrant.user_id == user.id, AiGrant.pool == body.pool,
                                               AiGrant.day == today)).first()
    before = grant.extra if grant else 0
    if before + body.extra > AI_GRANT_MAX:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Hoy ya tiene {before} extra: como mucho {AI_GRANT_MAX} al día")
    if grant is None:
        grant = AiGrant(user_id=user.id, pool=body.pool, day=today, extra=0)
    grant.extra = before + body.extra
    session.add(grant)
    record_action(session, _admin(request), "ai_grant", user.id,
                  {"pool": body.pool, "day": today.isoformat(), "extra": before},
                  {"pool": body.pool, "day": today.isoformat(), "extra": grant.extra})
    session.commit()
    return {"pool": body.pool, "day": today.isoformat(), "extra": grant.extra}
