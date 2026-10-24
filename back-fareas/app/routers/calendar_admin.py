import logging
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.core.config import get_settings
from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip, _get_or_404
from app.services import errors
from app.services.audit import audit
from app.services.justifications import crear as crear_justificacion
from app.services.justifications import eliminar as eliminar_justificacion
from app.services.settings import semesters_con_grupos
from app.services.storage import detect_document_type, get_storage, justification_key
from app.tables import AppSettings, AppUser, Course, Holiday, Justification, UserRole

router = APIRouter(tags=["calendar"])
logger = logging.getLogger("fareas.justifications")


class HolidayIn(BaseModel):
    holiday_date: date
    description: str = Field(min_length=3, max_length=160)

class HolidayOut(BaseModel):
    id: int
    holiday_date: date
    description: str

@router.get("/holidays", response_model=list[HolidayOut])
async def list_holidays(
    db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    year: int | None = Query(None, ge=2000, le=2100, description="Filtra por año"),
) -> list[HolidayOut]:
    stmt = select(Holiday).order_by(Holiday.holiday_date)
    if year is not None:
        stmt = stmt.where(Holiday.holiday_date >= date(year, 1, 1),
                          Holiday.holiday_date <= date(year, 12, 31))
    holidays = (await db.exec(stmt)).all()
    return [
        HolidayOut(id=h.id, holiday_date=h.holiday_date, description=h.description)
        for h in holidays
    ]

@router.post("/holidays", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_holiday(
    body: HolidayIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    if (await db.exec(select(Holiday).where(Holiday.holiday_date == body.holiday_date))).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La fecha {body.holiday_date} ya está registrada como feriado",
        )
    holiday = Holiday(holiday_date=body.holiday_date, description=body.description.strip())
    db.add(holiday)
    await db.flush()

    from app.tables import AttendanceSession, SessionStatus

    sesiones = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.session_date == body.holiday_date,
                AttendanceSession.status.in_([
                    SessionStatus.ABIERTA, SessionStatus.CERRADA
                ]),
            )
        )
    ).all()
    canceladas = 0
    for s in sesiones:
        s.status = SessionStatus.CANCELADA
        s.cancel_reason = "Feriado"
        s.cancelled_by = admin.id
        s.cancelled_at = _now_naive()
        if s.status == SessionStatus.CERRADA:
            s.needs_review = False
        db.add(s)
        canceladas += 1

    await audit(
        db, admin, action="feriado_creado", entity="holiday", entity_id=holiday.id,
        new_value={"date": str(body.holiday_date), "description": holiday.description,
                   "sesiones_canceladas": canceladas},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(holiday)
    return {
        "id": holiday.id,
        "holiday_date": str(holiday.holiday_date),
        "description": holiday.description,
        "sesiones_canceladas": canceladas,
    }

def _now_naive():
    from app.services.attendance_engine import _naive_peru, ahora_peru

    return _naive_peru(ahora_peru())

class HolidayRangeIn(BaseModel):
    desde: date
    hasta: date
    description: str = Field(
        min_length=3, max_length=160,
        validation_alias=AliasChoices("description", "descripcion"),
    )
    omitir_fines_de_semana: bool = True

@router.post("/holidays/range", status_code=status.HTTP_201_CREATED)
async def create_holiday_range(
    body: HolidayRangeIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    if body.hasta < body.desde:
        raise errors.DomainError("La fecha 'hasta' no puede ser anterior a 'desde'")
    creados, omitidos, canceladas = 0, 0, 0
    d = body.desde
    while d <= body.hasta:
        if body.omitir_fines_de_semana and d.isoweekday() >= 6:
            d += _un_dia()
            continue
        ya = (await db.exec(select(Holiday).where(Holiday.holiday_date == d))).first()
        if ya is not None:
            omitidos += 1
            d += _un_dia()
            continue
        r = await create_holiday(
            HolidayIn(holiday_date=d, description=body.description), request, db, admin
        )
        creados += 1
        canceladas += r["sesiones_canceladas"]
        d += _un_dia()
    await audit(
        db, admin, action="feriado_rango", entity="holiday",
        new_value={"desde": str(body.desde), "hasta": str(body.hasta),
                   "creados": creados, "omitidos": omitidos, "canceladas": canceladas},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"creados": creados, "omitidos": omitidos, "sesiones_canceladas": canceladas}

def _un_dia():
    from datetime import timedelta

    return timedelta(days=1)

class HolidayNationalIn(BaseModel):
    year: int = Field(ge=2000, le=2100)

@router.post("/holidays/national", status_code=status.HTTP_201_CREATED)
async def create_holidays_national(
    body: HolidayNationalIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    from app.services.holidays_pe import feriados_nacionales

    creados, omitidos = 0, 0
    for fecha, descripcion in feriados_nacionales(body.year):
        ya = (await db.exec(select(Holiday).where(Holiday.holiday_date == fecha))).first()
        if ya is not None:
            omitidos += 1
            continue
        holiday = Holiday(holiday_date=fecha, description=descripcion)
        db.add(holiday)
        creados += 1
    await audit(
        db, admin, action="feriado_rango", entity="holiday",
        new_value={"anio": body.year, "nacionales_creados": creados, "omitidos": omitidos},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"anio": body.year, "creados": creados, "omitidos": omitidos}

@router.delete("/holidays/{holiday_id}", response_model=dict)
async def delete_holiday(
    holiday_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    holiday = await _get_or_404(db, Holiday, holiday_id, "Feriado")
    await db.delete(holiday)
    await audit(
        db, admin, action="feriado_eliminado", entity="holiday", entity_id=holiday_id,
        old_value={"date": str(holiday.holiday_date), "description": holiday.description},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"message": f"Feriado #{holiday_id} eliminado"}

class JustificationIn(BaseModel):
    student_id: int
    course_id: int | None = Field(default=None, description="Docente: OBLIGATORIO (sus cursos). Admin: NULL = todos")
    start_date: date
    end_date: date
    reason: str = Field(min_length=5, max_length=400)
    document_url: str | None = Field(default=None, max_length=500)

class JustificationOut(BaseModel):
    id: int
    student_id: int
    student_name: str
    course_id: int | None
    course_code: str | None
    start_date: date
    end_date: date
    reason: str
    document_url: str | None
    created_by: int
    created_by_name: str

async def _j_out(
    j: Justification, student: AppUser, course: Course | None, creator: AppUser
) -> JustificationOut:
    document_url = j.document_url
    if j.document_key:
        document_url = await get_storage().url(j.document_key)
    return JustificationOut(
        id=j.id,
        student_id=j.student_id,
        student_name=student.full_name,
        course_id=j.course_id,
        course_code=course.code if course is not None else None,
        start_date=j.start_date,
        end_date=j.end_date,
        reason=j.reason,
        document_url=document_url,
        created_by=j.created_by,
        created_by_name=creator.full_name,
    )

@router.get("/justifications", response_model=list[JustificationOut])
async def list_justifications(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    student_id: int | None = None,
    course_id: int | None = None,
) -> list[JustificationOut]:
    student_tbl = aliased(AppUser)
    creator_tbl = aliased(AppUser)
    stmt = (
        select(Justification, student_tbl, Course, creator_tbl)
        .join(student_tbl, student_tbl.id == Justification.student_id)
        .outerjoin(Course, Course.id == Justification.course_id)
        .join(creator_tbl, creator_tbl.id == Justification.created_by)
        .order_by(Justification.start_date.desc())
    )
    if user.role is UserRole.DOCENTE:
        stmt = stmt.where(Justification.created_by == user.id)
    if student_id is not None:
        stmt = stmt.where(Justification.student_id == student_id)
    if course_id is not None:
        stmt = stmt.where(Justification.course_id == course_id)
    rows = (await db.exec(stmt)).all()
    return [await _j_out(j, student, course, creator) for j, student, course, creator in rows]

@router.post("/justifications", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_justification(
    body: JustificationIn, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    just, afectadas = await crear_justificacion(
        db, user,
        student_id=body.student_id, course_id=body.course_id,
        start_date=body.start_date, end_date=body.end_date,
        reason=body.reason, document_url=body.document_url,
        ip=_client_ip(request),
    )
    return {
        "id": just.id,
        "student_id": just.student_id,
        "course_id": just.course_id,
        "start_date": just.start_date.isoformat(),
        "end_date": just.end_date.isoformat(),
        "faltas_afectadas": afectadas,
        "message": f"Justificación registrada; {afectadas} falta(s) marcadas como justificadas",
    }

@router.delete("/justifications/{justification_id}", response_model=dict)
async def delete_justification(
    justification_id: int, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    revertidas = await eliminar_justificacion(
        db, user, justification_id, ip=_client_ip(request)
    )
    return {"message": f"Justificación eliminada; {revertidas} falta(s) volvieron a estado 'falta'"}


def _require_justification_owner(just: Justification, user: AppUser) -> None:
    if user.role is UserRole.ADMIN:
        return
    if user.role is not UserRole.DOCENTE or just.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes adjuntar documentos a las justificaciones que creaste",
        )


async def _read_document(file: UploadFile) -> bytes:
    settings = get_settings()
    limit = settings.R2_MAX_UPLOAD_MB * 1024 * 1024
    data = bytearray()
    try:
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > limit:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"El archivo supera el límite de {settings.R2_MAX_UPLOAD_MB} MB",
                )
    finally:
        await file.close()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El archivo está vacío",
        )
    return bytes(data)


async def _delete_stored(key: str) -> None:
    try:
        await get_storage().delete(key)
    except Exception:
        logger.warning("No se pudo borrar el adjunto %s", key, exc_info=True)


@router.post("/justifications/{justification_id}/document", response_model=dict)
async def upload_justification_document(
    justification_id: int,
    request: Request,
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    file: Annotated[UploadFile, File()],
) -> dict:
    just = await _get_or_404(db, Justification, justification_id, "Justificación")
    _require_justification_owner(just, user)

    data = await _read_document(file)
    detected = detect_document_type(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="El adjunto debe ser un PDF, JPG o PNG válido",
        )
    content_type, extension = detected

    storage = get_storage()
    try:
        key = await storage.put(
            justification_key(justification_id, extension), data, content_type
        )
    except Exception as exc:
        logger.exception("No se pudo subir el adjunto de la justificación %s", justification_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar el archivo; intenta de nuevo en unos minutos",
        ) from exc

    previous = just.document_key
    just.document_key = key
    db.add(just)
    await audit(
        db, user, action="justificacion_documento", entity="justification",
        entity_id=justification_id,
        new_value={"document_key": key, "bytes": len(data), "content_type": content_type},
        ip_address=_client_ip(request),
    )
    await db.commit()

    if previous and previous != key:
        await _delete_stored(previous)
    return {"id": justification_id, "document_url": await storage.url(key)}


@router.delete("/justifications/{justification_id}/document", response_model=dict)
async def delete_justification_document(
    justification_id: int,
    request: Request,
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    just = await _get_or_404(db, Justification, justification_id, "Justificación")
    _require_justification_owner(just, user)
    if not just.document_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La justificación no tiene documento adjunto",
        )

    key = just.document_key
    just.document_key = None
    db.add(just)
    await audit(
        db, user, action="justificacion_documento_eliminado", entity="justification",
        entity_id=justification_id, old_value={"document_key": key},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await _delete_stored(key)
    return {"message": "Documento adjunto eliminado"}

def _settings_out(s: AppSettings) -> "SettingsOut":
    return SettingsOut(
        semester_label=s.semester_label,
        semester_start=str(s.semester_start) if s.semester_start else None,
        semester_end=str(s.semester_end) if s.semester_end else None,
        block_minutes=s.block_minutes,
        late_tolerance_minutes=s.late_tolerance_minutes,
        early_open_minutes=s.early_open_minutes,
        rectify_days=s.rectify_days,
        dpi_min_sessions=s.dpi_min_sessions,
        face_match_threshold=float(s.face_match_threshold),
        dpi_alert_percent=float(s.dpi_alert_percent),
        dpi_limit_percent=float(s.dpi_limit_percent),
        attendance_hour_start=s.attendance_hour_start.isoformat(timespec="minutes"),
        attendance_hour_end=s.attendance_hour_end.isoformat(timespec="minutes"),
        updated_at=s.updated_at.isoformat(timespec="seconds") if s.updated_at else None,
    )

class SettingsOut(BaseModel):
    semester_label: str
    semester_start: str | None = None
    semester_end: str | None = None
    block_minutes: int
    late_tolerance_minutes: int
    early_open_minutes: int
    rectify_days: int
    dpi_min_sessions: int
    face_match_threshold: float
    dpi_alert_percent: float
    dpi_limit_percent: float
    attendance_hour_start: str
    attendance_hour_end: str
    updated_at: str | None

@router.get("/settings/semesters", response_model=list[str])
async def list_semesters(
    db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> list[str]:
    return await semesters_con_grupos(db)

async def _get_settings_or_500(db) -> AppSettings:
    s = await db.get(AppSettings, 1)
    if s is None:
        raise HTTPException(status_code=500, detail="Falta la fila app_settings id=1 (ejecutar 002_seed.sql)")
    return s

@router.get("/settings", response_model=SettingsOut)
async def get_settings_endpoint(
    db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> SettingsOut:
    return _settings_out(await _get_settings_or_500(db))

class SettingsUpdate(BaseModel):
    semester_label: str | None = Field(default=None, max_length=40)
    semester_start: date | None = None
    semester_end: date | None = None
    block_minutes: int | None = Field(default=None, gt=0)
    late_tolerance_minutes: int | None = Field(default=None, ge=0)
    early_open_minutes: int | None = Field(default=None, ge=0, le=60)
    rectify_days: int | None = Field(default=None, ge=0)
    dpi_min_sessions: int | None = Field(default=None, ge=0)
    face_match_threshold: float | None = Field(default=None, ge=0, le=1)
    dpi_alert_percent: float | None = Field(default=None, gt=0)
    dpi_limit_percent: float | None = Field(default=None, gt=0)
    attendance_hour_start: time | None = None
    attendance_hour_end: time | None = None

@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> SettingsOut:
    s = await _get_settings_or_500(db)
    data = body.model_dump(exclude_unset=True)
    if "attendance_hour_start" in data or "attendance_hour_end" in data:
        start = data.get("attendance_hour_start", s.attendance_hour_start)
        end = data.get("attendance_hour_end", s.attendance_hour_end)
        if start >= end:
            raise errors.DomainError("La hora inicio debe ser menor que la hora fin")
    alerta = data.get("dpi_alert_percent", float(s.dpi_alert_percent))
    limite = data.get("dpi_limit_percent", float(s.dpi_limit_percent))
    if alerta >= limite:
        raise errors.DomainError("dpi_alert_percent debe ser menor que dpi_limit_percent")
    inicio = data.get("semester_start", s.semester_start)
    fin = data.get("semester_end", s.semester_end)
    if inicio is not None and fin is not None and inicio >= fin:
        raise errors.DomainError("semester_start debe ser anterior a semester_end")
    old = {
        "semester_label": s.semester_label,
        "semester_start": str(s.semester_start) if s.semester_start else None,
        "semester_end": str(s.semester_end) if s.semester_end else None,
        "late_tolerance_minutes": s.late_tolerance_minutes,
        "early_open_minutes": s.early_open_minutes,
        "dpi_alert_percent": float(s.dpi_alert_percent),
        "dpi_limit_percent": float(s.dpi_limit_percent),
    }
    for field, value in data.items():
        setattr(s, field, value)
    db.add(s)
    await audit(
        db, admin, action="parametros_actualizados", entity="app_settings", entity_id=1,
        old_value=old, new_value={k: str(v) for k, v in data.items()},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(s)
    return _settings_out(s)
