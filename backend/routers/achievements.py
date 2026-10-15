"""
/api/achievements: Logros, sus evidencias y el botón SOS (módulo "achievements").

Todo empieza con require_module(..., "achievements"): sin el módulo encendido, 403.
Toda consulta filtra por el usuario de la sesión; lo de otra cuenta es 404.
Las rutas literales (/categories, /collections, /files, /sos) van antes que
/{achievement_id}. Los archivos: backend/achievement_files.py. Los hitos y el
sorteo del SOS: backend/achievements.py.
"""
from datetime import date as date_type, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func, update
from sqlmodel import Session, select

from backend import achievement_files as storage
from backend import achievements as logic
from backend.auth import get_current_user
from backend.database import get_session
from backend.models import (Achievement, AchievementCategory, AchievementCollection, AchievementFile, SosAction,
                            SosNote, User)
from backend.routers.auth import require_module, user_modules
from backend.schemas import (
    AchievementCategoryCreate,
    AchievementCategoryResponse,
    AchievementCategoryUpdate,
    AchievementCollectionCreate,
    AchievementCollectionResponse,
    AchievementCreate,
    AchievementFileResponse,
    AchievementListResponse,
    AchievementResponse,
    AchievementUpdate,
    AchievementUsage,
    SosActionCreate,
    SosActionResponse,
    SosActionUpdate,
    SosNoteCreate,
    SosNoteResponse,
    SosResponse,
    format_partial_date,
    parse_partial_date,
)

router = APIRouter(tags=["achievements"])

NOT_FOUND = {"achievement": "Logro no encontrado", "category": "Categoría no encontrada",
             "collection": "Colección no encontrada", "file": "Archivo no encontrado",
             "action": "Acción no encontrada", "note": "Nota no encontrada"}
# Lo que puede pesar un formulario de subida además del archivo
FORM_OVERHEAD = 64 * 1024
SOS_EXCLUDE_MAX = 500
SOS_NOTES_LIST = 100


def achievements_user(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """El usuario del token, si tiene Logros encendido (si no, 403)"""
    require_module(session, current_user, "achievements")
    return current_user


def _own(session: Session, model, user_id: int, row_id: int, what: str):
    row = session.exec(select(model).where(model.id == row_id, model.user_id == user_id)).first()
    if row is None or getattr(row, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND[what])
    return row


def _file_response(row: AchievementFile) -> AchievementFileResponse:
    return AchievementFileResponse(id=row.id, achievement_id=row.achievement_id, original_name=row.original_name,
                                   mime=row.mime, size_bytes=row.size_bytes, has_thumb=bool(row.thumb_name),
                                   created_at=row.created_at)


def _files_by_achievement(session: Session, user_id: int, ids: List[int]) -> Dict[int, List[AchievementFileResponse]]:
    if not ids:
        return {}
    rows = session.exec(
        select(AchievementFile).where(AchievementFile.user_id == user_id, AchievementFile.achievement_id.in_(ids))
        .order_by(AchievementFile.id)
    ).all()
    files: Dict[int, List[AchievementFileResponse]] = {}
    for row in rows:
        files.setdefault(row.achievement_id, []).append(_file_response(row))
    return files


def _response(row: Achievement, files: List[AchievementFileResponse]) -> AchievementResponse:
    return AchievementResponse(
        id=row.id, title=row.title, date=format_partial_date(row.achieved_on, row.date_precision),
        date_precision=row.date_precision, achieved_on=row.achieved_on, kind=row.kind,
        category_id=row.category_id, collection_id=row.collection_id, situation=row.situation,
        what_i_did=row.what_i_did, what_it_shows=row.what_it_shows, is_featured=row.is_featured,
        origin=row.origin, is_hidden=row.is_hidden, files=files, created_at=row.created_at,
    )


def _one(session: Session, row: Achievement) -> AchievementResponse:
    return _response(row, _files_by_achievement(session, row.user_id, [row.id]).get(row.id, []))


def _date(value: str):
    """La fecha del logro; una futura (más allá de mañana, por el huso) no vale."""
    day, precision = parse_partial_date(value)
    if day > date_type.today() + timedelta(days=1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Un logro no puede tener fecha en el futuro")
    return day, precision


def _check_refs(session: Session, user_id: int, category_id: Optional[int], collection_id: Optional[int]) -> None:
    if category_id is not None:
        _own(session, AchievementCategory, user_id, category_id, "category")
    if collection_id is not None:
        _own(session, AchievementCollection, user_id, collection_id, "collection")


def _clean_text(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _used_bytes(session: Session, user_id: int) -> int:
    return session.exec(
        select(func.coalesce(func.sum(AchievementFile.size_bytes), 0)).where(AchievementFile.user_id == user_id)
    ).one()


def _visible(session: Session, user_id: int):
    return select(Achievement).where(Achievement.user_id == user_id, Achievement.is_deleted == False)  # noqa: E712


def _habits_on(session: Session, user: User) -> bool:
    return user_modules(session, user.id)["habits"]["enabled"]


# ==================== Lista ====================

@router.get("", response_model=AchievementListResponse)
def list_achievements(
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """
    Todos los logros (también los ocultos, con is_hidden), sus categorías y
    colecciones y el espacio usado. Antes crea los hitos automáticos que se
    hayan cruzado desde la última vez.
    """
    logic.ensure_defaults(session, current_user.id)
    logic.sync_milestones(session, current_user.id, habits=_habits_on(session, current_user))
    rows = session.exec(
        _visible(session, current_user.id).order_by(Achievement.achieved_on.desc(), Achievement.id.desc())
    ).all()
    files = _files_by_achievement(session, current_user.id, [r.id for r in rows])
    categories = session.exec(
        select(AchievementCategory).where(AchievementCategory.user_id == current_user.id)
        .order_by(AchievementCategory.order, AchievementCategory.id)
    ).all()
    collections = session.exec(
        select(AchievementCollection).where(AchievementCollection.user_id == current_user.id)
        .order_by(AchievementCollection.name)
    ).all()
    return AchievementListResponse(
        achievements=[_response(r, files.get(r.id, [])) for r in rows],
        categories=[AchievementCategoryResponse(id=c.id, name=c.name, order=c.order) for c in categories],
        collections=[AchievementCollectionResponse(id=c.id, name=c.name) for c in collections],
        usage=AchievementUsage(bytes=_used_bytes(session, current_user.id), quota=storage.QUOTA_BYTES,
                               file_max=storage.MAX_FILE_BYTES),
    )


# ==================== Categorías ====================

def _category_name(session: Session, user_id: int, value: str, exclude_id: Optional[int] = None) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El nombre no puede estar vacío")
    query = select(AchievementCategory.id).where(AchievementCategory.user_id == user_id,
                                                 AchievementCategory.name == name)
    if exclude_id is not None:
        query = query.where(AchievementCategory.id != exclude_id)
    if session.exec(query).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya tienes una categoría llamada '{name}'")
    return name


@router.post("/categories", response_model=AchievementCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: AchievementCategoryCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    logic.ensure_defaults(session, current_user.id)
    name = _category_name(session, current_user.id, payload.name)
    last = session.exec(select(func.max(AchievementCategory.order))
                        .where(AchievementCategory.user_id == current_user.id)).one()
    category = AchievementCategory(user_id=current_user.id, name=name, order=(last or 0) + 1)
    session.add(category)
    session.commit()
    session.refresh(category)
    return AchievementCategoryResponse(id=category.id, name=category.name, order=category.order)


@router.patch("/categories/{category_id}", response_model=AchievementCategoryResponse)
def update_category(
    category_id: int,
    payload: AchievementCategoryUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    category = _own(session, AchievementCategory, current_user.id, category_id, "category")
    if payload.name is not None:
        category.name = _category_name(session, current_user.id, payload.name, exclude_id=category.id)
    if payload.order is not None:
        category.order = payload.order
    session.add(category)
    session.commit()
    session.refresh(category)
    return AchievementCategoryResponse(id=category.id, name=category.name, order=category.order)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """Sus logros quedan sin categoría. La última no se borra: sin ninguna, la
    cuenta volvería a recibir las de inicio."""
    category = _own(session, AchievementCategory, current_user.id, category_id, "category")
    count = session.exec(select(func.count(AchievementCategory.id))
                         .where(AchievementCategory.user_id == current_user.id)).one()
    if count <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Es tu única categoría: crea otra antes")
    session.exec(update(Achievement).where(Achievement.user_id == current_user.id,
                                           Achievement.category_id == category.id).values(category_id=None))
    session.delete(category)
    session.commit()


# ==================== Colecciones ====================

def _collection_name(session: Session, user_id: int, value: str, exclude_id: Optional[int] = None) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El nombre no puede estar vacío")
    query = select(AchievementCollection.id).where(AchievementCollection.user_id == user_id,
                                                   AchievementCollection.name == name)
    if exclude_id is not None:
        query = query.where(AchievementCollection.id != exclude_id)
    if session.exec(query).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya tienes una colección llamada '{name}'")
    return name


@router.post("/collections", response_model=AchievementCollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: AchievementCollectionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    collection = AchievementCollection(user_id=current_user.id,
                                       name=_collection_name(session, current_user.id, payload.name))
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return AchievementCollectionResponse(id=collection.id, name=collection.name)


@router.patch("/collections/{collection_id}", response_model=AchievementCollectionResponse)
def rename_collection(
    collection_id: int,
    payload: AchievementCollectionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    collection = _own(session, AchievementCollection, current_user.id, collection_id, "collection")
    collection.name = _collection_name(session, current_user.id, payload.name, exclude_id=collection.id)
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return AchievementCollectionResponse(id=collection.id, name=collection.name)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """Sus logros quedan sueltos; no se borra ninguno."""
    collection = _own(session, AchievementCollection, current_user.id, collection_id, "collection")
    session.exec(update(Achievement).where(Achievement.user_id == current_user.id,
                                           Achievement.collection_id == collection.id).values(collection_id=None))
    session.delete(collection)
    session.commit()


# ==================== Archivos ====================

def _file_headers() -> dict:
    # Solo su dueño y nunca en caché; si alguien lo abriera directo, ni se
    # interpreta como otro tipo ni corre nada
    return {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox"}


@router.get("/files/{file_id}")
def get_file(
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    row = _own(session, AchievementFile, current_user.id, file_id, "file")
    try:
        path = storage.file_path(current_user.id, row.stored_name)
    except FileNotFoundError:
        path = None
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND["file"])
    return FileResponse(path, media_type=row.mime, filename=row.original_name, content_disposition_type="inline",
                        headers=_file_headers())


@router.get("/files/{file_id}/thumb")
def get_thumb(
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    row = _own(session, AchievementFile, current_user.id, file_id, "file")
    if not row.thumb_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Este archivo no tiene miniatura")
    path = storage.file_path(current_user.id, row.thumb_name)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND["file"])
    return FileResponse(path, media_type="image/webp", headers=_file_headers())


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    row = _own(session, AchievementFile, current_user.id, file_id, "file")
    names = (row.stored_name, row.thumb_name)
    session.delete(row)
    session.commit()
    storage.remove(current_user.id, *names)


def _save_upload(user_id: int, achievement_id: int, name: str, data: bytes) -> AchievementFileResponse:
    """La parte con base de datos y disco de la subida (fuera del event loop)."""
    from backend.database import engine
    with Session(engine) as session:
        _own(session, Achievement, user_id, achievement_id, "achievement")
        count = session.exec(select(func.count(AchievementFile.id))
                             .where(AchievementFile.achievement_id == achievement_id,
                                    AchievementFile.user_id == user_id)).one()
        if count >= storage.MAX_FILES_PER_ACHIEVEMENT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Un logro lleva como mucho {storage.MAX_FILES_PER_ACHIEVEMENT} archivos")
        if _used_bytes(session, user_id) + len(data) > storage.QUOTA_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail=f"Llegaste al espacio de tu cuenta ({storage.QUOTA_BYTES // (1024 * 1024)} MB). "
                                       "Borra alguna evidencia para subir más.")
        try:
            mime, thumb = storage.check_upload(data)
        except storage.UploadRejected as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
        stored, thumb_name = storage.store(user_id, mime, data, thumb)
        row = AchievementFile(user_id=user_id, achievement_id=achievement_id, original_name=storage.clean_name(name),
                              mime=mime, size_bytes=len(data), stored_name=stored, thumb_name=thumb_name)
        session.add(row)
        try:
            session.commit()
        except BaseException:
            session.rollback()
            storage.remove(user_id, stored, thumb_name)
            raise
        session.refresh(row)
        return _file_response(row)


@router.post("/{achievement_id}/files", response_model=AchievementFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    achievement_id: int,
    request: Request,
    current_user: User = Depends(achievements_user),
):
    """
    Sube una evidencia (multipart, campo `file`). El tamaño se mira ANTES de leer
    el formulario: sin Content-Length, 411; con uno mayor que el tope, 413. Después
    el contenido decide el tipo (backend/achievement_files.py).
    """
    too_big = HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"El archivo pasa de {storage.MAX_FILE_BYTES // (1024 * 1024)} MB")
    length = request.headers.get("content-length")
    if not length or not length.isdigit():
        raise HTTPException(status_code=status.HTTP_411_LENGTH_REQUIRED, detail="Falta el tamaño del archivo")
    if int(length) > storage.MAX_FILE_BYTES + FORM_OVERHEAD:
        raise too_big
    form = await request.form(max_files=1, max_fields=2)
    try:
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Falta el archivo")
        data = await upload.read(storage.MAX_FILE_BYTES + 1)
        if len(data) > storage.MAX_FILE_BYTES:
            raise too_big
        name = upload.filename
    finally:
        await form.close()
    return await run_in_threadpool(_save_upload, current_user.id, achievement_id, name, data)


# ==================== SOS ====================

@router.get("/sos", response_model=SosResponse)
def sos(
    exclude: str = "",
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """
    Hasta 3 logros al azar (sin los de `exclude`, los ids ya vistos en esta
    apertura, separados por comas), un dato acumulado y una acción pequeña.
    Los ocultos no salen.
    """
    try:
        seen = [int(part) for part in exclude.split(",") if part.strip()][:SOS_EXCLUDE_MAX]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="exclude: ids separados por comas")
    logic.ensure_defaults(session, current_user.id)
    habits = _habits_on(session, current_user)
    logic.sync_milestones(session, current_user.id, habits=habits)
    candidates = session.exec(
        _visible(session, current_user.id).where(Achievement.is_hidden == False)  # noqa: E712
    ).all()
    picked, restarted = logic.pick_achievements(candidates, seen)
    files = _files_by_achievement(session, current_user.id, [a.id for a in picked])

    best = None
    if habits:
        from backend.routers.habits import calculate_streak
        best = calculate_streak(current_user.id, session, current_user, date_type.today()).best
    facts = logic.cumulative_facts(session, current_user.id, habits, best)
    actions = session.exec(select(SosAction).where(SosAction.user_id == current_user.id)).all()
    action = logic.rng.choice(actions) if actions else None
    return SosResponse(
        achievements=[_response(a, files.get(a.id, [])) for a in picked],
        restarted=restarted,
        fact=logic.rng.choice(facts) if facts else None,
        action=SosActionResponse(id=action.id, text=action.text, order=action.order) if action else None,
    )


@router.get("/sos/actions", response_model=List[SosActionResponse])
def list_actions(
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    logic.ensure_defaults(session, current_user.id)
    rows = session.exec(select(SosAction).where(SosAction.user_id == current_user.id)
                        .order_by(SosAction.order, SosAction.id)).all()
    return [SosActionResponse(id=r.id, text=r.text, order=r.order) for r in rows]


@router.post("/sos/actions", response_model=SosActionResponse, status_code=status.HTTP_201_CREATED)
def create_action(
    payload: SosActionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    logic.ensure_defaults(session, current_user.id)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La acción no puede estar vacía")
    last = session.exec(select(func.max(SosAction.order)).where(SosAction.user_id == current_user.id)).one()
    row = SosAction(user_id=current_user.id, text=text, order=(last or 0) + 1)
    session.add(row)
    session.commit()
    session.refresh(row)
    return SosActionResponse(id=row.id, text=row.text, order=row.order)


@router.patch("/sos/actions/{action_id}", response_model=SosActionResponse)
def update_action(
    action_id: int,
    payload: SosActionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    row = _own(session, SosAction, current_user.id, action_id, "action")
    if payload.text is not None:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La acción no puede estar vacía")
        row.text = text
    if payload.order is not None:
        row.order = payload.order
    session.add(row)
    session.commit()
    session.refresh(row)
    return SosActionResponse(id=row.id, text=row.text, order=row.order)


@router.delete("/sos/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action(
    action_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """La última no se borra: sin ninguna, la cuenta volvería a recibir las de inicio."""
    row = _own(session, SosAction, current_user.id, action_id, "action")
    count = session.exec(select(func.count(SosAction.id)).where(SosAction.user_id == current_user.id)).one()
    if count <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Es tu única acción: agrega otra antes")
    session.delete(row)
    session.commit()


@router.get("/sos/notes", response_model=List[SosNoteResponse])
def list_notes(
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """Las más recientes primero."""
    rows = session.exec(select(SosNote).where(SosNote.user_id == current_user.id)
                        .order_by(SosNote.note_date.desc(), SosNote.id.desc()).limit(SOS_NOTES_LIST)).all()
    return [SosNoteResponse(id=r.id, note_date=r.note_date, body=r.body, created_at=r.created_at) for r in rows]


@router.post("/sos/notes", response_model=SosNoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: SosNoteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La nota está vacía")
    row = SosNote(user_id=current_user.id, note_date=payload.note_date, body=body)
    session.add(row)
    session.commit()
    session.refresh(row)
    return SosNoteResponse(id=row.id, note_date=row.note_date, body=row.body, created_at=row.created_at)


@router.delete("/sos/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    row = _own(session, SosNote, current_user.id, note_id, "note")
    session.delete(row)
    session.commit()


# ==================== Un logro ====================

@router.post("", response_model=AchievementResponse, status_code=status.HTTP_201_CREATED)
def create_achievement(
    payload: AchievementCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    day, precision = _date(payload.date)
    _check_refs(session, current_user.id, payload.category_id, payload.collection_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El título no puede estar vacío")
    row = Achievement(
        user_id=current_user.id, title=title, achieved_on=day, date_precision=precision, kind=payload.kind,
        category_id=payload.category_id, collection_id=payload.collection_id,
        situation=_clean_text(payload.situation), what_i_did=_clean_text(payload.what_i_did),
        what_it_shows=_clean_text(payload.what_it_shows), is_featured=payload.is_featured, origin="manual",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _response(row, [])


@router.get("/{achievement_id}", response_model=AchievementResponse)
def get_achievement(
    achievement_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    return _one(session, _own(session, Achievement, current_user.id, achievement_id, "achievement"))


@router.patch("/{achievement_id}", response_model=AchievementResponse)
def update_achievement(
    achievement_id: int,
    payload: AchievementUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """PATCH parcial; también sirve para ocultar (is_hidden) un hito automático."""
    row = _own(session, Achievement, current_user.id, achievement_id, "achievement")
    sent = payload.model_fields_set
    if "title" in sent and payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El título no puede estar vacío")
        row.title = title
    if "date" in sent and payload.date is not None:
        row.achieved_on, row.date_precision = _date(payload.date)
    if "kind" in sent and payload.kind is not None:
        row.kind = payload.kind
    if "category_id" in sent:
        _check_refs(session, current_user.id, payload.category_id, None)
        row.category_id = payload.category_id
    if "collection_id" in sent:
        _check_refs(session, current_user.id, None, payload.collection_id)
        row.collection_id = payload.collection_id
    for field in ("situation", "what_i_did", "what_it_shows"):
        if field in sent:
            setattr(row, field, _clean_text(getattr(payload, field)))
    for field in ("is_featured", "is_hidden"):
        if field in sent and getattr(payload, field) is not None:
            setattr(row, field, getattr(payload, field))
    session.add(row)
    session.commit()
    session.refresh(row)
    return _one(session, row)


@router.delete("/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_achievement(
    achievement_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(achievements_user),
):
    """Borra el logro y sus archivos. Un hito automático queda marcado como
    borrado (sin archivos ni textos) para que no vuelva a generarse."""
    row = _own(session, Achievement, current_user.id, achievement_id, "achievement")
    files = session.exec(select(AchievementFile).where(AchievementFile.user_id == current_user.id,
                                                       AchievementFile.achievement_id == row.id)).all()
    names = [n for f in files for n in (f.stored_name, f.thumb_name)]
    for f in files:
        session.delete(f)
    if row.auto_key:
        row.is_deleted, row.is_hidden, row.is_featured = True, True, False
        row.situation = row.what_i_did = row.what_it_shows = None
        row.category_id = row.collection_id = None
        session.add(row)
    else:
        session.delete(row)
    session.commit()
    storage.remove(current_user.id, *names)
