"""Calendario y parámetros - RF-09 (feriados), RF-10 (justificaciones por
rango) y RF-34 (parámetros del semestre, fila única id=1).

Todas las escrituras quedan en audit_log (RF-32).
"""
from datetime import date, time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip, _get_or_404
from app.services import errors
from app.services.audit import audit
from app.tables import AppSettings, AppUser, Course, Holiday, Justification, UserRole

router = APIRouter(tags=["calendar"])


# ---------------------------------------------------------------------------
# Feriados - RF-09
# ---------------------------------------------------------------------------
class HolidayIn(BaseModel):
    holiday_date: date
    description: str = Field(min_length=3, max_length=160)


class HolidayOut(BaseModel):
    id: int
    holiday_date: date
    description: str


@router.get("/holidays", response_model=list[HolidayOut])
async def list_holidays(
    db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> list[HolidayOut]:
    holidays = (await db.exec(select(Holiday).order_by(Holiday.holiday_date))).all()
    return [
        HolidayOut(id=h.id, holiday_date=h.holiday_date, description=h.description)  # type: ignore[arg-type]
        for h in holidays
    ]


@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
async def create_holiday(
    body: HolidayIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> HolidayOut:
    if (await db.exec(select(Holiday).where(Holiday.holiday_date == body.holiday_date))).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La fecha {body.holiday_date} ya está registrada como feriado",
        )
    holiday = Holiday(holiday_date=body.holiday_date, description=body.description.strip())
    db.add(holiday)
    await db.flush()  # obtiene holiday.id para la bitácora
    await audit(
        db, admin, action="feriado_creado", entity="holiday", entity_id=holiday.id,
        new_value={"date": str(body.holiday_date), "description": holiday.description},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(holiday)
    return HolidayOut(
        id=holiday.id, holiday_date=holiday.holiday_date, description=holiday.description  # type: ignore[arg-type]
    )


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


# ---------------------------------------------------------------------------
# Justificaciones - RF-10
# ---------------------------------------------------------------------------
class JustificationIn(BaseModel):
    student_id: int
    course_id: int | None = Field(default=None, description="NULL = aplica a todos los cursos")
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
    created_by_name: str


def _j_out(j: Justification, student: AppUser, course: Course | None, creator: AppUser) -> JustificationOut:
    return JustificationOut(
        id=j.id,  # type: ignore[arg-type]
        student_id=j.student_id,
        student_name=student.full_name,
        course_id=j.course_id,
        course_code=course.code if course is not None else None,
        start_date=j.start_date,
        end_date=j.end_date,
        reason=j.reason,
        document_url=j.document_url,
        created_by_name=creator.full_name,
    )


async def _validate_range(db, body: JustificationIn) -> Course | None:
    if body.end_date < body.start_date:
        raise errors.DomainError("La fecha fin no puede ser anterior a la inicio")
    student = await db.get(AppUser, body.student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE:
        raise errors.DomainError("student_id debe ser un estudiante existente")
    if body.course_id is not None:
        course = await db.get(Course, body.course_id)
        if course is None:
            raise errors.NotFoundError("Curso no encontrado")
        return course
    return None


@router.get("/justifications", response_model=list[JustificationOut])
async def list_justifications(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
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
    if student_id is not None:
        stmt = stmt.where(Justification.student_id == student_id)
    if course_id is not None:
        stmt = stmt.where(Justification.course_id == course_id)
    rows = (await db.exec(stmt)).all()
    return [_j_out(j, student, course, creator) for j, student, course, creator in rows]


@router.post("/justifications", response_model=JustificationOut, status_code=status.HTTP_201_CREATED)
async def create_justification(
    body: JustificationIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> JustificationOut:
    """RF-10: registra un descanso médico / justificación por rango de fechas."""
    course = await _validate_range(db, body)
    justification = Justification(
        student_id=body.student_id, course_id=body.course_id, start_date=body.start_date,
        end_date=body.end_date, reason=body.reason.strip(), document_url=body.document_url,
        created_by=admin.id,  # type: ignore[arg-type]
    )
    db.add(justification)
    await db.flush()
    await audit(
        db, admin, action="justificacion_creada", entity="justification", entity_id=justification.id,
        new_value={"student_id": body.student_id, "course_id": body.course_id,
                   "from": str(body.start_date), "to": str(body.end_date)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(justification)
    student = await db.get(AppUser, body.student_id)
    return _j_out(justification, student, course, admin)  # type: ignore[arg-type]


@router.delete("/justifications/{justification_id}", response_model=dict)
async def delete_justification(
    justification_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    justification = await _get_or_404(db, Justification, justification_id, "Justificación")
    await db.delete(justification)
    await audit(
        db, admin, action="justificacion_eliminada", entity="justification", entity_id=justification_id,
        old_value={"student_id": justification.student_id, "course_id": justification.course_id,
                   "from": str(justification.start_date), "to": str(justification.end_date)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"message": f"Justificación #{justification_id} eliminada"}


# ---------------------------------------------------------------------------
# Parámetros - RF-34 (fila única id=1)
# ---------------------------------------------------------------------------
def _settings_out(s: AppSettings) -> "SettingsOut":
    return SettingsOut(
        semester_label=s.semester_label,
        block_minutes=s.block_minutes,
        late_tolerance_minutes=s.late_tolerance_minutes,
        face_match_threshold=float(s.face_match_threshold),
        dpi_alert_percent=float(s.dpi_alert_percent),
        dpi_limit_percent=float(s.dpi_limit_percent),
        attendance_hour_start=s.attendance_hour_start.isoformat(timespec="minutes"),
        attendance_hour_end=s.attendance_hour_end.isoformat(timespec="minutes"),
        updated_at=s.updated_at.isoformat(timespec="seconds") if s.updated_at else None,
    )


class SettingsOut(BaseModel):
    semester_label: str
    block_minutes: int
    late_tolerance_minutes: int
    face_match_threshold: float
    dpi_alert_percent: float
    dpi_limit_percent: float
    attendance_hour_start: str
    attendance_hour_end: str
    updated_at: str | None


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
    block_minutes: int | None = Field(default=None, gt=0)
    late_tolerance_minutes: int | None = Field(default=None, ge=0)
    face_match_threshold: float | None = Field(default=None, ge=0, le=1)
    dpi_alert_percent: float | None = Field(default=None, gt=0)
    dpi_limit_percent: float | None = Field(default=None, gt=0)
    attendance_hour_start: time | None = None
    attendance_hour_end: time | None = None


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> SettingsOut:
    """RF-34: ajusta los parámetros del semestre (queda auditado, RF-32)."""
    s = await _get_settings_or_500(db)
    data = body.model_dump(exclude_unset=True)
    if "attendance_hour_start" in data or "attendance_hour_end" in data:
        start = data.get("attendance_hour_start", s.attendance_hour_start)
        end = data.get("attendance_hour_end", s.attendance_hour_end)
        if start >= end:
            raise errors.DomainError("La hora inicio debe ser menor que la hora fin")
    old = {
        "semester_label": s.semester_label,
        "block_minutes": s.block_minutes,
        "late_tolerance_minutes": s.late_tolerance_minutes,
        "face_match_threshold": float(s.face_match_threshold),
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
