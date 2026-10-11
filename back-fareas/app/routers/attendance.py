"""Asistencia — RF-15 (rectificación docente), RF-21 (marca manual) y
consulta del día (alimenta app-student-list del dashboard, PLAN §5).

La lógica vive en el motor; aquí solo se orquesta y se audita.
"""
from datetime import date

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
    cerrar_sesion,
    registrar_marca,
)
from app.services.audit import audit
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    Course,
    CourseGroup,
    Room,
    ScheduleBlock,
    SessionStatus,
    UserRole,
)

router = APIRouter(tags=["attendance"])


# ---------------------------------------------------------------------------
# Asistencias propias del ESTUDIANTE autenticado (RF-22/RF-24)
# ---------------------------------------------------------------------------
@router.get("/attendance/me")
async def my_attendance(
    db: DbSession,
    user: CurrentUser,
    desde: date | None = None,
    hasta: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    """Historial de asistencias del ESTUDIANTE autenticado (rol estudiante).

    Requiere rol 'estudiante' (los usuarios admin/docente reciben 403: su
    vista es la del panel /attendance, no un historial personal).
    Los rangos filtran por fecha de sesión (default: sin límite).
    """
    if user.role is not UserRole.ESTUDIANTE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este endpoint es para el rol estudiante",
        )
    stmt = (
        select(AttendanceRecord, AttendanceSession, ScheduleBlock, Course, CourseGroup)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)  # type: ignore[arg-type]
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)  # type: ignore[arg-type]
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)  # type: ignore[arg-type]
        .join(Course, Course.id == CourseGroup.course_id)  # type: ignore[arg-type]
        .where(AttendanceRecord.student_id == user.id)  # type: ignore[arg-type]
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
            "session_date": str(ses.session_date),
            "start_time": bloque.start_time.isoformat(timespec="minutes"),
            "end_time": bloque.end_time.isoformat(timespec="minutes"),
            "course_id": curso.id,
            "course_code": curso.code,
            "course_name": curso.name,
            "group_code": grupo.group_code,
            "status": rec.status.value,
            "marked_at": rec.marked_at.isoformat(timespec="seconds") if rec.marked_at else None,
            "method": rec.method,
            "correct_reason": rec.correct_reason,
        }
        for rec, ses, bloque, curso, grupo in filas
    ]


# ---------------------------------------------------------------------------
# Consulta del día (vista v_today_attendance) — PLAN §5
# ---------------------------------------------------------------------------
@router.get("/attendance/today")
async def attendance_today(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = None,
    room: str | None = Query(None, max_length=20, description="Código de aula, p. ej. 'LAB 304'"),
    status_filter: str | None = Query(None, alias="status", pattern="^(asistio|tardanza|falta)$"),
) -> list[dict]:
    """Registros de HOY (vista v_today_attendance) con filtros del dashboard."""
    sql = (
        "SELECT record_id, att_date, student_id, student_code, student_name, course_id, "
        "course_code, course_name, group_code, room_code, status, marked_at, method, similarity "
        "FROM v_today_attendance WHERE 1=1"
    )
    params: dict = {}
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
        }
        for f in filas
    ]


# ---------------------------------------------------------------------------
# Sesiones abiertas de HOY (inicio de F3): alimenta el modal de marca
# manual RF-21 con la sesión activa por aula/curso/grupo.
# ---------------------------------------------------------------------------
@router.get("/attendance/sessions-today")
async def sessions_today(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> list[dict]:
    """Sesiones ABIERTAS de hoy (RF-26) con su aula/curso/grupo/bloque.

    Un docente solo ve las sesiones de SUS grupos; el admin las ve todas.
    El frontend lo usa para saber qué sesión corresponde al modal de
    marca manual (RF-21). Las cerradas se excluyen: una vez cerrada, la
    corrección es por rectificación (RF-15), no por marca manual.
    """
    stmt = (
        select(AttendanceSession, ScheduleBlock, CourseGroup, Course, Room, AppUser)
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)  # type: ignore[arg-type]
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)  # type: ignore[arg-type]
        .join(Course, Course.id == CourseGroup.course_id)  # type: ignore[arg-type]
        .join(Room, Room.id == CourseGroup.room_id)  # type: ignore[arg-type]
        .join(AppUser, AppUser.id == CourseGroup.teacher_id)  # type: ignore[arg-type]
        .where(
            AttendanceSession.session_date == _naive_peru(ahora_peru()).date(),
            AttendanceSession.status == SessionStatus.ABIERTA,  # type: ignore[arg-type]
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
            "room_id": aula.id,
            "room_code": aula.code,
            "teacher_id": docente.id,
            "teacher_name": docente.full_name,
        }
        for ses, bloque, grupo, curso, aula, docente in filas
    ]


# ---------------------------------------------------------------------------
# Marca manual del docente (RF-21) sobre una sesión abierta
# ---------------------------------------------------------------------------
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
    """RF-21: el docente marca a un alumno a mano (llegó sin recognition)."""
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    if session.status is not None and session.status.value == "cerrada":
        raise errors.DomainError("La sesión ya está cerrada; usa la rectificación (RF-15)")
    # El docente solo marca en SUS grupos (el admin, en cualquiera)
    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")
    from app.tables import CourseGroup

    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    if docente.role is UserRole.DOCENTE and grupo.teacher_id != docente.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No es tu grupo")

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


# ---------------------------------------------------------------------------
# Rectificación (RF-15): cambia el estado con motivo obligatorio
# ---------------------------------------------------------------------------
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
    """RF-15: rectifica el estado de una marca (motivo obligatorio, RF-32)."""
    record = await _get_or_404(db, AttendanceRecord, record_id, "Registro")
    session = await db.get(AttendanceSession, record.session_id)
    bloque = await db.get(ScheduleBlock, session.block_id) if session else None
    from app.tables import CourseGroup

    grupo = await db.get(CourseGroup, bloque.group_id) if bloque else None
    if grupo is None:
        raise errors.NotFoundError("La sesión del registro no tiene grupo")
    if docente.role is UserRole.DOCENTE and grupo.teacher_id != docente.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No es tu grupo")

    old = {"status": str(record.status.value), "corrected_by": record.corrected_by}
    record.status = body.new_status
    record.corrected_by = docente.id  # type: ignore[arg-type]
    record.corrected_at = _naive_peru(ahora_peru())  # columna TIMESTAMP (naive)
    record.correct_reason = body.reason.strip()
    record.method = "manual"
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


# ---------------------------------------------------------------------------
# Cierre manual de una sesión (admin) — RF-26 a demanda
# ---------------------------------------------------------------------------
@router.post("/sessions/{session_id}/close")
async def cerrar_sesion_endpoint(
    session_id: int,
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    session = await _get_or_404(db, AttendanceSession, session_id, "Sesión")
    return await cerrar_sesion(db, session, actor=admin, ip=_client_ip(request))
