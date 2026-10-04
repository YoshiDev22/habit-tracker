"""
Reportes guardados (épica 30, Fase 4). El botón "Generar reporte" de la pestaña
Reportes llama a POST; el timer usa scripts/generate_reports.py con la misma
lógica (backend/reports.py). Todo filtra por el usuario de la sesión.
"""
from typing import Optional
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.ai import AiError, ai_config
from backend.auth import get_current_user
from backend.database import get_session
from backend.dates import resolve_client_today
from backend.metrics import compute_metrics
from backend.models import Report, User, utc_now_naive
from backend.report_ai import ai_preview, calls_today, write_with_ai
from backend.reports import previous_summary, generate_report, is_period_start, period_bounds, previous_period
from backend.routers.auth import require_module, user_modules
from backend.schemas import ReportCreate, ReportListResponse, ReportResponse, ReportSummary

router = APIRouter(tags=["reports"])


def _summary_fields(report: Report) -> dict:
    return dict(id=report.id, kind=report.kind, period_start=report.period_start,
                period_end=report.period_end, through=report.through,
                total_seconds=(report.metrics or {}).get("total_seconds", 0),
                trigger=report.trigger, text_source=report.text_source, text_model=report.text_model,
                text_note=report.text_note, created_at=report.created_at)


def _full(report: Report) -> ReportResponse:
    return ReportResponse(**_summary_fields(report), metrics=report.metrics, text=report.text)


@router.get("", response_model=ReportListResponse)
def list_reports(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    """Los reportes guardados, del periodo más reciente al más viejo (sin cifras)."""
    reports = session.exec(
        select(Report).where(Report.user_id == current_user.id)
        .order_by(Report.period_start.desc(), Report.kind)
    ).all()
    return ReportListResponse(reports=[ReportSummary(**_summary_fields(r)) for r in reports])


@router.post("", response_model=ReportResponse)
def create_report(body: ReportCreate, session: Session = Depends(get_session),
                  current_user: User = Depends(get_current_user)):
    """
    Genera el reporte de una semana (desde su lunes) o un mes (desde su día 1).
    Si ya había uno de ese periodo, lo reemplaza. Un periodo en curso se
    calcula hasta hoy; uno que aún no empieza no se puede generar.
    """
    today = resolve_client_today(body.today)
    if not is_period_start(body.kind, body.period_start):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="La semana empieza en lunes y el mes en el día 1")
    if body.period_start > today:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Ese periodo todavía no empieza")
    report = generate_report(session, current_user, body.kind, body.period_start, today, use_ai=body.use_ai)
    return _full(report)


@router.get("/ai-preview")
def preview_ai(today: Optional[date_type] = None, session: Session = Depends(get_session),
               current_user: User = Depends(get_current_user)) -> dict:
    """
    "Ver qué se envía": las instrucciones y el JSON exacto que recibiría el
    proveedor, con las cifras del último reporte guardado (o de esta semana si
    no hay), más el proveedor, el modelo y cuántas llamadas van hoy. Para las
    cuentas con acceso al módulo, aunque aún no lo enciendan.
    """
    if not user_modules(session, current_user.id)["ai"]["allowed"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tu cuenta todavía no tiene acceso a este módulo.")
    latest = session.exec(select(Report).where(Report.user_id == current_user.id)
                          .order_by(Report.created_at.desc())).first()
    if latest is not None:
        kind, metrics, label = latest.kind, latest.metrics, f"{latest.kind} {latest.period_start.isoformat()}"
    else:
        local_today = resolve_client_today(today)
        start, end = period_bounds("week", local_today)
        metrics = compute_metrics(session, current_user, start, end, local_today)
        prev_start, prev_end = previous_period("week", start)
        metrics["previous"] = previous_summary(compute_metrics(session, current_user, prev_start, prev_end, local_today))
        kind, label = "week", f"week {start.isoformat()}"
    config = ai_config()
    return {
        "configured": config is not None,
        "provider": config.provider if config else None,
        "model": config.model if config else None,
        "daily_limit": config.daily_limit if config else None,
        "used_today": calls_today(session, current_user.id),
        "training_warning": bool(config and config.uses_training_free_tier),
        "sample": label,
        **ai_preview(kind, metrics),
    }


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: int, session: Session = Depends(get_session),
               current_user: User = Depends(get_current_user)):
    report = session.exec(select(Report).where(Report.id == report_id, Report.user_id == current_user.id)).first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")
    return _full(report)


@router.post("/{report_id}/rewrite", response_model=ReportResponse)
def rewrite_with_ai(report_id: int, session: Session = Depends(get_session),
                    current_user: User = Depends(get_current_user)):
    """
    "Reescribir con IA": el texto de un reporte guardado, de nuevo y con la IA,
    sobre las mismas cifras (no las recalcula). Si la IA falla, el reporte se
    queda como estaba y el error dice por qué.
    """
    report = session.exec(select(Report).where(Report.id == report_id, Report.user_id == current_user.id)).first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")
    require_module(session, current_user, "ai")
    config = ai_config()
    if config is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="La IA no está configurada en este servidor")
    try:
        text, model = write_with_ai(session, current_user, report.kind, report.metrics, config)
    except AiError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None
    report.text = text
    report.text_source, report.text_model, report.text_note = "ai", model, None
    # El texto es nuevo: la hora que enseña el reporte es la de esta escritura
    report.created_at = utc_now_naive()
    report.trigger = "manual"
    session.add(report)
    session.commit()
    session.refresh(report)
    return _full(report)
