"""
Reportes guardados (épica 30, Fase 4). El botón "Generar reporte" de la pestaña
Reportes llama a POST; el timer usa scripts/generate_reports.py con la misma
lógica (backend/reports.py). Todo filtra por el usuario de la sesión.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.auth import get_current_user
from backend.database import get_session
from backend.dates import resolve_client_today
from backend.models import Report, User
from backend.reports import generate_report, is_period_start
from backend.schemas import ReportCreate, ReportListResponse, ReportResponse, ReportSummary

router = APIRouter(tags=["reports"])


def _summary_fields(report: Report) -> dict:
    return dict(id=report.id, kind=report.kind, period_start=report.period_start,
                period_end=report.period_end, through=report.through,
                total_seconds=(report.metrics or {}).get("total_seconds", 0),
                trigger=report.trigger, text_source=report.text_source, created_at=report.created_at)


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
    report = generate_report(session, current_user, body.kind, body.period_start, today)
    return _full(report)


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: int, session: Session = Depends(get_session),
               current_user: User = Depends(get_current_user)):
    report = session.exec(select(Report).where(Report.id == report_id, Report.user_id == current_user.id)).first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")
    return _full(report)
