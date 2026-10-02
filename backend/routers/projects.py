from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.database import get_session
from backend.models import User, Project, ProjectCost, ProjectFinance, Task, PomodoroSession, Tag, TaskTag
from backend.schemas import (
    OverviewMonth,
    OverviewTag,
    OverviewTask,
    ProjectFinanceResponse,
    ProjectFinanceUpdate,
    ProjectOverview,
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
    ProjectSummary,
    ProjectSummaryListResponse,
)
from backend.auth import get_current_user
from backend.boards import ensure_user_setup, unassigned_project_id
from backend.costing import costs_cents_by_project, estimates_for_tasks, finance_response, finance_row
from backend.routers.auth import require_module, user_modules

router = APIRouter(tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def get_projects(
    include_inactive: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los proyectos del usuario.
    Por defecto solo devuelve los no archivados (is_active=True).
    """
    ensure_user_setup(session, current_user.id)

    query = select(Project).where(Project.user_id == current_user.id)

    if not include_inactive:
        query = query.where(Project.is_active == True)

    projects = session.exec(query.order_by(Project.order, Project.id)).all()

    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects)
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Crea un nuevo proyecto para el usuario.
    El nombre debe ser único por usuario. Si ya existe (activo o
    archivado), devuelve 409 en vez de reactivarlo automáticamente.
    """
    existing = session.exec(
        select(Project).where(
            Project.user_id == current_user.id,
            Project.name == project_in.name
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un proyecto con el nombre '{project_in.name}' para este usuario"
        )

    new_project = Project(
        user_id=current_user.id,
        name=project_in.name,
        description=project_in.description,
        color=project_in.color,
        icon=project_in.icon,
        order=project_in.order or 0,
        is_active=True,
    )
    session.add(new_project)
    session.commit()
    session.refresh(new_project)

    return ProjectResponse.model_validate(new_project)


@router.get("/summary", response_model=ProjectSummaryListResponse)
def get_projects_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Resumen por proyecto: progreso de tareas y tiempo dedicado (suma de
    PomodoroSession con mode='focus').
    """
    projects = session.exec(
        select(Project).where(
            Project.user_id == current_user.id,
            Project.is_active == True
        ).order_by(Project.order, Project.id)
    ).all()

    tasks = session.exec(
        select(Task).where(Task.user_id == current_user.id)
    ).all()

    pomodoro_sessions = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.user_id == current_user.id,
            PomodoroSession.mode == "focus"
        )
    ).all()

    tasks_by_project: Dict[int, list] = {}
    for t in tasks:
        tasks_by_project.setdefault(t.project_id, []).append(t)

    seconds_by_project: Dict[int, int] = {}
    sessions_by_project: Dict[int, int] = {}
    # Desglose dentro de cada proyecto: {project_id: {task_id: segundos}}. Las
    # sesiones sin tarea se acumulan aparte para que el desglose y el resto
    # sumen siempre el total del proyecto.
    seconds_by_task: Dict[int, Dict[int, int]] = {}
    seconds_no_task: Dict[int, int] = {}
    for s in pomodoro_sessions:
        if s.project_id is None:
            continue
        seconds_by_project[s.project_id] = seconds_by_project.get(s.project_id, 0) + s.duration_seconds
        sessions_by_project[s.project_id] = sessions_by_project.get(s.project_id, 0) + 1

        if s.task_id is None:
            seconds_no_task[s.project_id] = seconds_no_task.get(s.project_id, 0) + s.duration_seconds
        else:
            per_task = seconds_by_task.setdefault(s.project_id, {})
            per_task[s.task_id] = per_task.get(s.task_id, 0) + s.duration_seconds

    summaries = []
    for p in projects:
        project_tasks = tasks_by_project.get(p.id, [])
        summaries.append(ProjectSummary(
            project_id=p.id,
            name=p.name,
            color=p.color,
            task_total=len(project_tasks),
            task_done=sum(1 for t in project_tasks if t.is_done),
            total_seconds=seconds_by_project.get(p.id, 0),
            session_count=sessions_by_project.get(p.id, 0),
            seconds_by_task={
                str(task_id): seconds
                for task_id, seconds in seconds_by_task.get(p.id, {}).items()
            },
            seconds_no_task=seconds_no_task.get(p.id, 0),
        ))

    return ProjectSummaryListResponse(summaries=summaries, total=len(summaries))


def _own_project(session: Session, user_id: int, project_id: int) -> Project:
    project = session.exec(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    ).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
    return project


def _focus_seconds(session: Session, user_id: int, project_id: int) -> int:
    """Tiempo de enfoque del proyecto: el mismo criterio que /summary"""
    return sum(s.duration_seconds for s in session.exec(
        select(PomodoroSession).where(
            PomodoroSession.user_id == user_id,
            PomodoroSession.project_id == project_id,
            PomodoroSession.mode == "focus",
        )
    ).all())


def _project_finance(session: Session, user_id: int, project_id: int) -> ProjectFinanceResponse:
    """El costeo de un proyecto con su tiempo y sus gastos (backend/costing.py)"""
    return finance_response(
        project_id, finance_row(session, user_id, project_id),
        _focus_seconds(session, user_id, project_id),
        costs_cents_by_project(session, user_id, [project_id]).get(project_id, 0),
    )


@router.get("/{project_id}/finance", response_model=ProjectFinanceResponse)
def get_project_finance(
    project_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Costeo del proyecto (plan maker): 403 sin el módulo encendido."""
    require_module(session, current_user, "maker")
    _own_project(session, current_user.id, project_id)
    return _project_finance(session, current_user.id, project_id)


@router.put("/{project_id}/finance", response_model=ProjectFinanceResponse)
def update_project_finance(
    project_id: int,
    body: ProjectFinanceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Guarda el costeo del proyecto (plan maker). Parcial: solo cambia lo que se
    manda, y null borra ese dato. "Sin asignar" no se costea (409): no es un
    proyecto de verdad, solo junta lo que no tiene uno.
    """
    require_module(session, current_user, "maker")
    project = _own_project(session, current_user.id, project_id)
    if project.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{project.name}' junta las tareas sin proyecto y no lleva costeo"
        )

    changes = body.model_dump(exclude_unset=True)
    if "client_name" in changes and changes["client_name"] is not None:
        changes["client_name"] = changes["client_name"].strip() or None
    if changes.get("currency", "MXN") is None:
        changes["currency"] = "MXN"     # la moneda no queda vacía: vuelve a la de por defecto

    def apply(row: ProjectFinance):
        for field, value in changes.items():
            setattr(row, field, value)
        session.add(row)
        session.commit()

    row = finance_row(session, current_user.id, project_id)
    try:
        apply(row or ProjectFinance(user_id=current_user.id, project_id=project_id))
    except IntegrityError:
        # Otra petición creó la fila a la vez (uq_project_finance_project)
        session.rollback()
        apply(finance_row(session, current_user.id, project_id))

    return _project_finance(session, current_user.id, project_id)


@router.get("/{project_id}/overview", response_model=ProjectOverview)
def get_project_overview(
    project_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Ficha del proyecto: tiempo de enfoque total, por tarea, por etiqueta y por
    mes, y tareas hechas contra totales. Mismo criterio que /summary (solo
    sesiones focus con este project_id), así que el total cuadra con la Lista
    y con Reportes. También para archivados y para "Sin asignar".
    """
    project = session.exec(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    ).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    tasks = session.exec(
        select(Task).where(Task.user_id == current_user.id, Task.project_id == project_id)
    ).all()
    focus = session.exec(
        select(PomodoroSession).where(
            PomodoroSession.user_id == current_user.id,
            PomodoroSession.project_id == project_id,
            PomodoroSession.mode == "focus",
        )
    ).all()

    task_ids = [t.id for t in tasks]
    tags_by_task: Dict[int, list] = {}
    tag_info: Dict[int, Tag] = {}
    if task_ids:
        for task_id, tag in session.exec(
            select(TaskTag.task_id, Tag)
            .join(Tag, Tag.id == TaskTag.tag_id)
            .where(TaskTag.user_id == current_user.id, TaskTag.task_id.in_(task_ids))
        ).all():
            tags_by_task.setdefault(task_id, []).append(tag.id)
            tag_info[tag.id] = tag

    seconds_by_task: Dict[int, int] = {}
    seconds_by_tag: Dict[int, int] = {}
    seconds_by_month: Dict[str, int] = {}
    no_task = untagged = 0
    for s in focus:
        seconds = s.duration_seconds
        month = s.session_date.strftime("%Y-%m")
        seconds_by_month[month] = seconds_by_month.get(month, 0) + seconds
        if s.task_id is None:
            no_task += seconds
        else:
            seconds_by_task[s.task_id] = seconds_by_task.get(s.task_id, 0) + seconds
        task_tags = tags_by_task.get(s.task_id, []) if s.task_id is not None else []
        if not task_tags:
            untagged += seconds
        for tag_id in task_tags:
            seconds_by_tag[tag_id] = seconds_by_tag.get(tag_id, 0) + seconds

    dates = [s.session_date for s in focus]
    total_seconds = sum(s.duration_seconds for s in focus)
    finance = estimates = None
    maker_on = user_modules(session, current_user.id)["maker"]["enabled"]
    if maker_on:
        # El desvío es del usuario, no dinero: vale también en "Sin asignar"
        estimates = estimates_for_tasks(session, current_user.id, project_id)
    if maker_on and not project.is_system:
        finance = finance_response(
            project_id, finance_row(session, current_user.id, project_id), total_seconds,
            costs_cents_by_project(session, current_user.id, [project_id]).get(project_id, 0),
        )
    return ProjectOverview(
        project=ProjectResponse.model_validate(project),
        total_seconds=total_seconds,
        session_count=len(focus),
        task_total=len(tasks),
        task_done=sum(1 for t in tasks if t.is_done),
        tasks=sorted(
            (OverviewTask(id=t.id, title=t.title, is_done=t.is_done, seconds=seconds_by_task.get(t.id, 0),
                          estimate_minutes=t.estimate_minutes)
             for t in tasks),
            key=lambda t: (-t.seconds, t.id),
        ),
        seconds_no_task=no_task,
        tags=sorted(
            (OverviewTag(tag_id=tag_id, name=tag_info[tag_id].name, color=tag_info[tag_id].color, seconds=seconds)
             for tag_id, seconds in seconds_by_tag.items()),
            key=lambda t: (-t.seconds, t.name),
        ),
        untagged_seconds=untagged,
        months=[OverviewMonth(month=m, seconds=seconds_by_month[m]) for m in sorted(seconds_by_month)],
        first_date=min(dates) if dates else None,
        last_date=max(dates) if dates else None,
        finance=finance,
        estimates=estimates,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Obtiene un proyecto específico del usuario"""
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza parcialmente un proyecto.
    Para archivarlo sin borrar sus tareas, envía is_active=false.
    """
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    if project_in.name is not None and project_in.name != project.name:
        existing = session.exec(
            select(Project).where(
                Project.user_id == current_user.id,
                Project.name == project_in.name,
                Project.id != project_id
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un proyecto con el nombre '{project_in.name}' para este usuario"
            )

    update_data = project_in.model_dump(exclude_unset=True)

    if project.is_system and (
        ("name" in update_data and update_data["name"] != project.name)
        or update_data.get("is_active") is False
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{project.name}' es el proyecto de las tareas sin proyecto: no se renombra ni se archiva"
        )

    for field, value in update_data.items():
        setattr(project, field, value)

    session.add(project)
    session.commit()
    session.refresh(project)

    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    delete_sessions: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Borra un proyecto. Es una etiqueta de las tareas, no su contenedor, así
    que sus tareas NO se borran: pasan a "Sin asignar", en la misma columna.

    Su tiempo registrado también pasa a "Sin asignar", salvo con
    ?delete_sessions=true, que lo borra (el de sus tareas y el registrado
    directo al proyecto). Para ocultarlo sin perder nada, archivarlo
    (PATCH is_active=false). "Sin asignar" no se borra.
    """
    project = session.exec(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado"
        )

    if project.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{project.name}' es el proyecto de las tareas sin proyecto y no se borra"
        )

    ensure_user_setup(session, current_user.id)
    unassigned_id = unassigned_project_id(session, current_user.id)

    for t in session.exec(
        select(Task).where(
            Task.project_id == project_id,
            Task.user_id == current_user.id
        )
    ).all():
        t.project_id = unassigned_id
        session.add(t)

    for s in session.exec(
        select(PomodoroSession).where(
            PomodoroSession.project_id == project_id,
            PomodoroSession.user_id == current_user.id
        )
    ).all():
        if delete_sessions:
            session.delete(s)
        else:
            s.project_id = unassigned_id
            session.add(s)

    # Su costeo y sus gastos (plan maker) no tienen sentido sin él: se van con
    # el proyecto. Archivarlo los conserva.
    finance = finance_row(session, current_user.id, project_id)
    if finance:
        session.delete(finance)
    for cost in session.exec(
        select(ProjectCost).where(ProjectCost.project_id == project_id, ProjectCost.user_id == current_user.id)
    ).all():
        session.delete(cost)

    session.delete(project)
    session.commit()
