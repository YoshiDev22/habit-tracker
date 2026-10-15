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
from backend import announcement_rules
from backend.models import (AccountMessage, AdminAction, AiCall, AiGrant, Announcement, Board, Feedback, Habit,
                            PomodoroSession, ProjectCost, Report, SecurityEvent, Task, User, UserModule, utc_now_naive)
from backend.security_log import KINDS as SECURITY_KINDS, cleanup as cleanup_security_events, is_proxy_ip
from backend.report_ai import ai_usage as account_ai_usage, extra_today
from backend.modules import MODULES, PRIVATE as PRIVATE_MODULES, resolve as resolve_module

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


# "Ya tienes acceso …": con su contracción (al, a la)
MODULE_ACCESS = {"maker": "al plan Maker", "ai": "a la IA de los reportes"}


def send_message(session: Session, user_id: int, title: str, body: str = "") -> AccountMessage:
    """Un aviso del panel para una sola cuenta, en su campanita. No hace commit."""
    from backend.notices import add_notice
    message = AccountMessage(user_id=user_id, title=title[:announcement_rules.MAX_TITLE],
                             body=body[:announcement_rules.MAX_BODY])
    session.add(message)
    session.flush()
    add_notice(session, user_id, "message", str(message.id))
    return message


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
    """Los módulos de una cuenta, sin los privados (PRIVATE en backend/modules.py)."""
    return {name: resolve_module(name, getattr(rows.get(name), "enabled", None), getattr(rows.get(name), "allowed", None))
            for name in MODULES if name not in PRIVATE_MODULES}


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
            "active": user.is_active,
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
        "admin_note": f.admin_note, "user_note": f.user_note,
        "account": {"id": f.user_id, "email": mask_email(email)},
    } for f, email in rows]}


@router.get("/actions")
def actions(account_id: Optional[int] = None, session: Session = Depends(get_session)) -> dict:
    """La bitácora, la más nueva arriba (hasta 200); con account_id, solo esa cuenta."""
    query = select(AdminAction)
    if account_id is not None:
        query = query.where(AdminAction.account_id == account_id)
    rows = session.exec(query.order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(200)).all()
    # La cuenta, enmascarada; None si ya se borró (la bitácora sobrevive a la cuenta)
    ids = {a.account_id for a in rows if a.account_id is not None}
    emails = dict(session.exec(select(User.id, User.email).where(User.id.in_(ids))).all()) if ids else {}
    return {"actions": [{"id": a.id, "created_at": a.created_at, "admin": a.admin_email, "action": a.action,
                         "account_id": a.account_id,
                         "account": mask_email(emails[a.account_id]) if a.account_id in emails else None,
                         "before": a.before, "after": a.after} for a in rows]}


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
        if after["allowed"] and not before["allowed"]:
            send_message(session, user.id, f"Ya tienes acceso {MODULE_ACCESS.get(module, module)}",
                         "Enciéndelo en ⚙️ Configuración › Módulos.")
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
    what = "reportes de costos" if body.pool == "costs" else "reportes de tiempo y hábitos"
    send_message(session, user.id, f"Te dimos {body.extra} textos más de IA hoy",
                 f"Para {what}. Mañana vuelve tu límite normal.")
    session.commit()
    return {"pool": body.pool, "day": today.isoformat(), "extra": grant.extra}


class AccountActive(SQLModel):
    active: StrictBool


@router.put("/accounts/{user_id}/active")
def set_account_active(user_id: int, body: AccountActive, request: Request,
                       session: Session = Depends(get_session)) -> dict:
    """Desactivar (fuera al momento: sus sesiones dejan de valer en la siguiente
    petición y no puede entrar) o reactivar una cuenta. No borra nada."""
    user = _account(session, user_id)
    if user.is_active != body.active:
        record_action(session, _admin(request), "account", user.id, {"active": user.is_active}, {"active": body.active})
        user.is_active = body.active
        if not body.active:
            # Sus sesiones no vuelven al reactivarla: hay que entrar otra vez
            user.token_version = (user.token_version or 0) + 1
        session.add(user)
        session.commit()
    return {"id": user.id, "active": user.is_active}


@router.post("/accounts/{user_id}/keep")
def cancel_deletion(user_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    """Cancelar el borrado programado de una cuenta (como "Conservar mi cuenta")."""
    user = _account(session, user_id)
    if user.delete_after is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esa cuenta no tiene un borrado programado")
    record_action(session, _admin(request), "keep", user.id,
                  {"delete_after": user.delete_after.isoformat()}, {"delete_after": None})
    user.delete_after = None
    session.add(user)
    session.commit()
    return {"id": user.id, "delete_after": None}


# ---------- Seguridad (paso 8) ----------
# Las alertas: (tipo, por qué se agrupa, ventana, umbral, qué dice)
ALERTS = [
    ("login_failed", "ip", "hour", 20, "{n} contraseñas equivocadas desde {who} en una hora"),
    ("password_failed", "user", "day", 10, "{n} contraseñas equivocadas en Mi perfil de {who} en un día"),
    ("register", "ip", "day", 5, "{n} cuentas nuevas desde {who} en un día"),
    ("token_revoked", "user", "day", 20, "{n} tokens de sesiones cerradas de {who} en un día"),
    ("account_inactive", "user", "day", 5, "{n} intentos de una cuenta desactivada ({who}) en un día"),
    ("admin_denied", "ip", "day", 1, "{n} accesos rechazados al panel desde {who}"),
    ("admin_csrf", "ip", "day", 1, "{n} cambios rechazados en el panel (CSRF) desde {who}"),
]
PROXY_SHARE = 0.8      # si así de lo que trae IP llega de un proxy, la app no ve la IP real
PROXY_MIN_EVENTS = 10


@router.get("/security")
def security(days: int = Query(default=7, ge=1, le=30), session: Session = Depends(get_session)) -> dict:
    """Eventos de seguridad: por día y tipo, las IP con más eventos, las alertas y si
    la app parece ver la IP del proxy en vez de la del cliente."""
    cleanup_security_events(session)
    now = utc_now_naive()
    since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    rows = session.exec(select(SecurityEvent).where(SecurityEvent.hour >= since)).all()
    ids = {r.user_id for r in rows if r.user_id is not None}
    emails = dict(session.exec(select(User.id, User.email).where(User.id.in_(ids))).all()) if ids else {}

    def account(user_id):
        return mask_email(emails[user_id]) if user_id in emails else (None if user_id is None else f"#{user_id}")

    by_day = Counter()
    by_ip = defaultdict(Counter)
    for r in rows:
        by_day[(r.hour.date().isoformat(), r.kind)] += r.count
        if r.ip:
            by_ip[r.ip][r.kind] += r.count

    alerts = []
    for kind, group, window, threshold, text in ALERTS:
        buckets = Counter()
        for r in rows:
            if r.kind != kind:
                continue
            key = r.ip if group == "ip" else r.user_id
            if key in (None, ""):
                continue
            when = r.hour if window == "hour" else r.hour.replace(hour=0)
            buckets[(key, when)] += r.count
        for (key, when), n in buckets.items():
            if n >= threshold:
                who = key if group == "ip" else (account(key) or f"#{key}")
                alerts.append({"kind": kind, "count": n, "at": when, "ip": key if group == "ip" else None,
                               "account": None if group == "ip" else who,
                               "text": text.format(n=n, who=who)})
    alerts.sort(key=lambda a: a["at"], reverse=True)

    with_ip = [(r.ip, r.count) for r in rows if r.ip]
    total_ip = sum(n for _, n in with_ip)
    from_proxy = sum(n for ip, n in with_ip if is_proxy_ip(ip))
    return {
        "since": since.date().isoformat(),
        "kinds": SECURITY_KINDS,
        "days": [{"date": d, "kind": k, "count": n} for (d, k), n in sorted(by_day.items())],
        "top_ips": [{"ip": ip, "count": sum(c.values()), "kinds": dict(c)}
                    for ip, c in sorted(by_ip.items(), key=lambda item: -sum(item[1].values()))[:20]],
        "alerts": alerts[:50],
        "proxy_warning": total_ip >= PROXY_MIN_EVENTS and from_proxy / total_ip >= PROXY_SHARE,
    }


# ---------- Problemas reportados (paso 5) ----------
FEEDBACK_NOTE_MAX = 1000
FEEDBACK_USER_NOTE_MAX = 500


class FeedbackUpdate(SQLModel):
    status: Optional[str] = None
    admin_note: Optional[str] = PydanticField(default=None, max_length=FEEDBACK_NOTE_MAX)
    user_note: Optional[str] = PydanticField(default=None, max_length=FEEDBACK_USER_NOTE_MAX)


@router.put("/feedback/{feedback_id}")
def update_feedback(feedback_id: int, body: FeedbackUpdate, request: Request,
                    session: Session = Depends(get_session)) -> dict:
    """El estado de un problema (abierto, revisado, cerrado), la nota interna y la nota
    para quien lo reportó. Cerrarlo le avisa en su campanita, una sola vez, con la nota
    para él (la interna nunca sale del panel). Una nota vacía la borra."""
    if body.status is not None and body.status not in FEEDBACK_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"status debe ser uno de: {', '.join(FEEDBACK_STATUSES)}")
    feedback = session.get(Feedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe ese reporte")
    before = {"status": feedback.status, "admin_note": feedback.admin_note, "user_note": feedback.user_note}
    if body.status is not None:
        feedback.status = body.status
    for field in ("admin_note", "user_note"):
        value = getattr(body, field)
        if value is not None:
            setattr(feedback, field, value.strip() or None)
    after = {"status": feedback.status, "admin_note": feedback.admin_note, "user_note": feedback.user_note}
    if after != before:
        record_action(session, _admin(request), "feedback", feedback.user_id,
                      {"feedback_id": feedback.id, **before}, {"feedback_id": feedback.id, **after})
        if after["status"] == "closed" and before["status"] != "closed":
            from backend.notices import add_notice
            add_notice(session, feedback.user_id, "feedback_closed", str(feedback.id))
        session.add(feedback)
        session.commit()
    return {"id": feedback.id, **after}


# ---------- Avisos (paso 6) ----------
class AnnouncementCreate(SQLModel):
    title: str = PydanticField(max_length=announcement_rules.MAX_TITLE)
    body: str = PydanticField(default="", max_length=announcement_rules.MAX_BODY)
    hours: Optional[StrictInt] = PydanticField(default=None, ge=1, le=24 * 30)   # sin horas: hasta terminarlo


class MessageCreate(SQLModel):
    title: str = PydanticField(min_length=1, max_length=announcement_rules.MAX_TITLE)
    body: str = PydanticField(default="", max_length=announcement_rules.MAX_BODY)


def _current_announcements(session: Session, now):
    return session.exec(select(Announcement).where(
        (Announcement.ends_at == None) | (Announcement.ends_at > now))).all()  # noqa: E711


@router.get("/announcements")
def list_announcements(session: Session = Depends(get_session)) -> dict:
    """Los avisos para todas las cuentas, el más nuevo arriba (hasta 50), vigentes o no."""
    now = utc_now_naive()
    rows = session.exec(select(Announcement).order_by(Announcement.id.desc()).limit(50)).all()
    return {"max_current": announcement_rules.MAX_CURRENT, "announcements": [{
        "id": a.id, "title": a.title, "body": a.body, "created_at": a.created_at, "ends_at": a.ends_at,
        "current": a.ends_at is None or a.ends_at > now} for a in rows]}


@router.post("/announcements")
def publish_announcement(body: AnnouncementCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    """Publicar un aviso para todas las cuentas, con las reglas de announce.py: como
    mucho MAX_CURRENT vigentes (409) y una espera entre dos publicaciones (429)."""
    now = utc_now_naive()
    last = session.exec(select(func.max(Announcement.created_at))).one()
    problem = announcement_rules.check(body.title, body.body, len(_current_announcements(session, now)), last, now)
    if problem:
        code = status.HTTP_429_TOO_MANY_REQUESTS if "espera" in problem else (
            status.HTTP_409_CONFLICT if "vigentes" in problem else status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise HTTPException(status_code=code, detail=problem)
    ann = Announcement(title=body.title.strip(), body=" ".join(body.body.split()), created_at=now,
                       ends_at=now + timedelta(hours=body.hours) if body.hours else None)
    session.add(ann)
    session.flush()
    record_action(session, _admin(request), "announcement", None, None,
                  {"announcement_id": ann.id, "title": ann.title, "hours": body.hours})
    session.commit()
    return {"id": ann.id, "title": ann.title, "ends_at": ann.ends_at}


@router.post("/announcements/{announcement_id}/end")
def end_announcement(announcement_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    """Terminar un aviso ya: sale de todas las campanitas."""
    ann = session.get(Announcement, announcement_id)
    if ann is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe ese aviso")
    now = utc_now_naive()
    if ann.ends_at is not None and ann.ends_at <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese aviso ya terminó")
    record_action(session, _admin(request), "announcement_end", None,
                  {"announcement_id": ann.id, "title": ann.title}, {"announcement_id": ann.id, "ended": True})
    ann.ends_at = now
    session.add(ann)
    session.commit()
    return {"id": ann.id, "ends_at": ann.ends_at}


@router.post("/accounts/{user_id}/messages")
def message_account(user_id: int, body: MessageCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    """Un aviso solo para esta cuenta, en su campanita."""
    user = _account(session, user_id)
    if not body.title.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Falta el título")
    message = send_message(session, user.id, body.title.strip(), " ".join(body.body.split()))
    record_action(session, _admin(request), "message", user.id, None, {"message_id": message.id, "title": message.title})
    session.commit()
    return {"id": message.id, "title": message.title}
