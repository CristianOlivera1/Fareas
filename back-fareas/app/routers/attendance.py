from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlmodel import select

from app.core.deps import CurrentUser, DbSession, RequireRole
from app.routers.catalog import _client_ip, _get_or_404
from app.services import errors
from app.services.attendance_engine import (
    _naive_peru,
    ahora_peru,
    cancelar_dia,
    cancelar_sesion,
    cerrar_sesion,
    registrar_marca,
    resolver_revision,
)
from app.services.audit import audit
from app.services.dpi import resumen_alumno
from app.services.justifications import crear as crear_justificacion
from app.services.settings import get_settings_row
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    Course,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
    SessionStatus,
    UserRole,
)

router = APIRouter(tags=["attendance"])


async def _grupo_de_sesion(db, session: AttendanceSession) -> CourseGroup:
    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")
    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    return grupo

def _exige_grupo_propio(user, grupo: CourseGroup) -> None:
    if user.role is UserRole.DOCENTE and grupo.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No es tu grupo")

@router.get("/attendance/me")
async def my_attendance(
    db: DbSession,
    user: CurrentUser,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    if user.role is not UserRole.ESTUDIANTE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este endpoint es para el rol estudiante",
        )
    stmt = (
        select(AttendanceRecord, AttendanceSession, ScheduleBlock, Course, CourseGroup)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
        .join(Course, Course.id == CourseGroup.course_id)
        .where(AttendanceRecord.student_id == user.id)
        .order_by(AttendanceSession.session_date.desc(), ScheduleBlock.start_time)
    )
    if desde is not None:
        stmt = stmt.where(AttendanceSession.session_date >= desde)
    if hasta is not None:
        stmt = stmt.where(AttendanceSession.session_date <= hasta)
    filas = (await db.exec(stmt.limit(limit))).all()
    return [
        {
            "record_id": rec.id,
            "session_id": ses.id,
            "session_date": str(ses.session_date),
            "start_time": bloque.start_time.isoformat(timespec="minutes"),
            "end_time": bloque.end_time.isoformat(timespec="minutes"),
            "course_id": curso.id,
            "course_code": curso.code,
            "course_name": curso.name,
            "group_code": grupo.group_code,
            "status": rec.status.value,
            "is_justified": rec.is_justified,
            "marked_at": rec.marked_at.isoformat(timespec="seconds") if rec.marked_at else None,
            "method": rec.method,
            "correct_reason": rec.correct_reason,
        }
        for rec, ses, bloque, curso, grupo in filas
    ]

@router.get("/attendance/me/dpi")
async def my_dpi(db: DbSession, user: CurrentUser) -> list[dict]:
    if user.role is not UserRole.ESTUDIANTE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este endpoint es para el rol estudiante",
        )
    return await resumen_alumno(db, user.id)

@router.get("/attendance/today")
async def attendance_today(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = None,
    room: str | None = Query(None, max_length=20, description="Código de aula, p. ej. 'LAB 304'"),
    status_filter: str | None = Query(None, alias="status", pattern="^(asistio|tardanza|falta)$"),
) -> list[dict]:
    sql = (
        "SELECT record_id, att_date, student_id, student_code, student_name, course_id, "
        "course_code, course_name, group_code, room_code, status, marked_at, method, similarity, "
        "is_justified, session_id, start_time, end_time, correct_reason, teacher_id "
        "FROM v_today_attendance WHERE 1=1"
    )
    params: dict = {}
    if user.role is UserRole.DOCENTE:
        sql += " AND teacher_id = :docente"
        params["docente"] = user.id
    if course_id is not None:
        sql += " AND course_id = :curso"
        params["curso"] = course_id
    if room:
        sql += " AND room_code = :aula"
        params["aula"] = room
    if status_filter:
        sql += " AND status = CAST(:estado AS attendance_status)"
        params["estado"] = status_filter
    sql += " ORDER BY marked_at DESC NULLS LAST LIMIT 500"
    filas = (await db.exec(sql_text(sql).bindparams(**params))).all()
    return [
        {
            "record_id": f.record_id,
            "student_id": f.student_id,
            "student_code": f.student_code,
            "student_name": f.student_name,
            "course_id": f.course_id,
            "course_code": f.course_code,
            "course_name": f.course_name,
            "group_code": f.group_code,
            "room_code": f.room_code,
            "status": f.status,
            "marked_at": f.marked_at.isoformat(timespec="seconds") if f.marked_at else None,
            "method": f.method,
            "similarity": float(f.similarity) if f.similarity is not None else None,
            "is_justified": bool(f.is_justified),
            "session_id": f.session_id,
        }
        for f in filas
    ]

@router.get("/attendance/sessions-today")
async def sessions_today(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> list[dict]:
    stmt = (
        select(AttendanceSession, ScheduleBlock, CourseGroup, Course, Room, AppUser)
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
        .join(Course, Course.id == CourseGroup.course_id)
        .outerjoin(Room, Room.id == ScheduleBlock.room_id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
        .where(
            AttendanceSession.session_date == _naive_peru(ahora_peru()).date(),
            AttendanceSession.status == SessionStatus.ABIERTA,
        )
    )
    if user.role is not UserRole.ADMIN:
        stmt = stmt.where(CourseGroup.teacher_id == user.id)
    stmt = stmt.order_by(ScheduleBlock.start_time)
    filas = (await db.exec(stmt)).all()
    return [
        {
            "session_id": ses.id,
            "status": ses.status.value,
            "session_date": str(ses.session_date),
            "block_id": bloque.id,
            "weekday": bloque.weekday,
            "start_time": bloque.start_time.isoformat(timespec="seconds"),
            "end_time": bloque.end_time.isoformat(timespec="seconds"),
            "group_id": grupo.id,
            "group_code": grupo.group_code,
            "course_id": curso.id,
            "course_code": curso.code,
            "course_name": curso.name,
            "room_id": aula.id if aula is not None else None,
            "room_code": aula.code if aula is not None else None,
            "teacher_id": docente.id if docente is not None else None,
            "teacher_name": docente.full_name if docente is not None else None,
        }
        for ses, bloque, grupo, curso, aula, docente in filas
    ]

@router.get("/attendance/sessions-review")
async def sessions_review(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> list[dict]:
    stmt = (
        select(AttendanceSession, ScheduleBlock, CourseGroup, Course, Room, AppUser)
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
        .join(Course, Course.id == CourseGroup.course_id)
        .outerjoin(Room, Room.id == ScheduleBlock.room_id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
        .where(
            AttendanceSession.needs_review.is_(True),
            AttendanceSession.status == SessionStatus.CERRADA,
        )
        .order_by(AttendanceSession.session_date.desc())
    )
    if user.role is not UserRole.ADMIN:
        stmt = stmt.where(CourseGroup.teacher_id == user.id)
    filas = (await db.exec(stmt.limit(200))).all()
    return [
        {
            "session_id": ses.id,
            "session_date": str(ses.session_date),
            "closed_at": ses.closed_at.isoformat(timespec="seconds") if ses.closed_at else None,
            "start_time": bloque.start_time.isoformat(timespec="minutes"),
            "end_time": bloque.end_time.isoformat(timespec="minutes"),
            "group_id": grupo.id,
            "group_code": grupo.group_code,
            "course_id": curso.id,
            "course_code": curso.code,
            "course_name": curso.name,
            "room_id": aula.id if aula is not None else None,
            "room_code": aula.code if aula is not None else None,
            "teacher_id": docente.id if docente is not None else None,
            "teacher_name": docente.full_name if docente is not None else None,
        }
        for ses, bloque, grupo, curso, aula, docente in filas
    ]

class ResolveReviewIn(BaseModel):
    action: str = Field(pattern="^(confirmar_faltas|cancelar)$")
    reason: str | None = Field(default=None, max_length=200, description="Obligatorio para 'cancelar'")

@router.post("/sessions/{session_id}/resolve-review")
async def resolve_review(
    session_id: int, body: ResolveReviewIn, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    grupo = await _grupo_de_sesion(db, session)
    _exige_grupo_propio(user, grupo)
    if body.action == "cancelar" and not body.reason:
        raise errors.DomainError("Cancelar una sesión por revisar requiere motivo")
    return await resolver_revision(
        db, session, user, body.action, reason=body.reason, ip=_client_ip(request)
    )

class MarcaManualIn(BaseModel):
    student_id: int
    status: AttendanceStatus = Field(description="asistio | tardanza | falta")

@router.post("/sessions/{session_id}/manual-mark", status_code=status.HTTP_201_CREATED)
async def marca_manual(
    session_id: int,
    body: MarcaManualIn,
    request: Request,
    db: DbSession,
    docente: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    if session.status is SessionStatus.CANCELADA:
        raise errors.DomainError("La sesión está cancelada; no admite marcas (R5)")
    if session.status is SessionStatus.CERRADA and not session.needs_review:
        raise errors.DomainError("La sesión ya está cerrada; usa la rectificación (RF-15)")
    grupo = await _grupo_de_sesion(db, session)
    _exige_grupo_propio(docente, grupo)
    matricula = (
        await db.exec(
            select(Enrollment).where(
                Enrollment.student_id == body.student_id,
                Enrollment.group_id == grupo.id,
            )
        )
    ).first()
    if matricula is None:
        raise errors.DomainError("El alumno no está matriculado en este grupo")
    if matricula.withdrawn_at is not None and matricula.withdrawn_at.date() <= session.session_date:
        raise errors.DomainError("El alumno está retirado de este grupo")

    record = await registrar_marca(
        db, session, body.student_id, method="manual",
        status_override=str(body.status.value),
        audit_actor=docente, audit_ip=_client_ip(request),
    )
    await db.commit()
    return {
        "record_id": record.id,
        "student_id": record.student_id,
        "status": record.status.value if hasattr(record.status, "value") else str(record.status),
        "session_id": session_id,
    }

class RectificarIn(BaseModel):
    new_status: AttendanceStatus
    reason: str = Field(min_length=5, max_length=400, description="Justificación presencial obligatoria")

@router.patch("/attendance/{record_id}/rectify", response_model=dict)
async def rectificar(
    record_id: int,
    body: RectificarIn,
    request: Request,
    db: DbSession,
    docente: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    record = await _get_or_404(db, AttendanceRecord, record_id, "Registro")
    session = await db.get(AttendanceSession, record.session_id)
    if session is None:
        raise errors.NotFoundError("La sesión del registro no existe")
    grupo = await _grupo_de_sesion(db, session)
    _exige_grupo_propio(docente, grupo)

    cfg = await get_settings_row(db)
    if docente.role is UserRole.DOCENTE:
        limite = session.session_date + timedelta(days=cfg.rectify_days)
        if _naive_peru(ahora_peru()).date() > limite:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El plazo de rectificación para docentes es de {cfg.rectify_days} días",
            )

    old = {"status": str(record.status.value), "corrected_by": record.corrected_by,
           "is_justified": record.is_justified}
    record.status = body.new_status
    record.corrected_by = docente.id
    record.corrected_at = _naive_peru(ahora_peru())
    record.correct_reason = body.reason.strip()
    record.method = "manual"
    if body.new_status is not AttendanceStatus.FALTA:
        record.is_justified = False
        record.justification_id = None
    db.add(record)
    await audit(
        db, docente, action="rectificacion", entity="attendance_record", entity_id=record.id,
        old_value=old,
        new_value={"status": str(body.new_status.value), "reason": body.reason.strip()},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(record)
    return {
        "record_id": record.id,
        "status": record.status.value,
        "corrected_by": record.corrected_by,
        "reason": record.correct_reason,
    }

class JustificarIn(BaseModel):
    reason: str = Field(min_length=5, max_length=400)

@router.patch("/attendance/{record_id}/justify", response_model=dict)
async def justificar_falta(
    record_id: int, body: JustificarIn, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    record = await _get_or_404(db, AttendanceRecord, record_id, "Registro")
    if record.status is not AttendanceStatus.FALTA:
        raise errors.DomainError("Solo se justifica un registro de estado 'falta'")
    if record.is_justified:
        raise errors.ConflictError("La falta ya está justificada")
    session = await db.get(AttendanceSession, record.session_id)
    if session is None:
        raise errors.NotFoundError("La sesión del registro no existe")
    grupo = await _grupo_de_sesion(db, session)
    _exige_grupo_propio(user, grupo)

    just, _afectadas = await crear_justificacion(
        db, user, student_id=record.student_id, course_id=grupo.course_id,
        start_date=session.session_date, end_date=session.session_date,
        reason=body.reason, ip=_client_ip(request),
    )
    record.is_justified = True
    record.justification_id = just.id
    db.add(record)
    await audit(
        db, user, action="falta_justificada", entity="attendance_record", entity_id=record.id,
        old_value={"is_justified": False},
        new_value={"justification_id": just.id, "reason": body.reason.strip()},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"record_id": record.id, "is_justified": True, "justification_id": just.id}

class CancelarIn(BaseModel):
    reason: str = Field(min_length=5, max_length=200)

class CancelarDiaIn(CancelarIn):
    fecha: date | None = Field(default=None, description="Default: hoy (R5 permite cancelar por adelantado)")

@router.post("/sessions/{session_id}/cancel")
async def cancelar_sesion_endpoint(
    session_id: int, body: CancelarIn, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    grupo = await _grupo_de_sesion(db, session)
    _exige_grupo_propio(user, grupo)
    return await cancelar_sesion(db, session, user, body.reason, ip=_client_ip(request))

@router.post("/blocks/{block_id}/cancel-day")
async def cancelar_dia_endpoint(
    block_id: int, body: CancelarDiaIn, request: Request, db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    bloque = await _get_or_404(db, ScheduleBlock, block_id, "Bloque horario")
    grupo = await _get_or_404(db, CourseGroup, bloque.group_id, "Grupo")
    _exige_grupo_propio(user, grupo)
    fecha = body.fecha or _naive_peru(ahora_peru()).date()
    return await cancelar_dia(
        db, bloque, fecha, user, body.reason,
        ip=_client_ip(request),
    )

@router.post("/sessions/{session_id}/close")
async def cerrar_sesion_endpoint(
    session_id: int,
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    return await cerrar_sesion(db, session, actor=admin, ip=_client_ip(request))
