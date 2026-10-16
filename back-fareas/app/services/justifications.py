"""Justificaciones con EFECTO sobre las faltas (R6, RF-10).

- Crear: marca is_justified=TRUE + justification_id en las faltas EXISTENTES
  dentro del rango (y curso si acota); las futuras nacen justificadas porque
  el motor de cierre consulta justificacion_vigente().
- Eliminar: revierte primero (is_justified=FALSE, justification_id=NULL) y
  luego borra — el ON DELETE SET NULL de la BD no basta.
- Permisos: docente SOLO alumnos matriculados en SUS grupos y con course_id
  obligatorio (sus cursos); admin cualquiera, course_id opcional (NULL =
  todos los cursos). Sin plazo para justificar (el descanso médico llega
  tarde), siempre con motivo y auditoría.
"""
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    CourseGroup,
    Enrollment,
    Justification,
    ScheduleBlock,
    UserRole,
)


async def _grupos_del_docente(db, teacher_id: int, curso_id: int | None) -> set[int]:
    """IDs de grupos ACTIVOS del docente (todos, o solo los de un curso)."""
    stmt = select(CourseGroup).where(
        CourseGroup.teacher_id == teacher_id,  # type: ignore[arg-type]
        CourseGroup.is_active,  # type: ignore[arg-type]
    )
    if curso_id is not None:
        stmt = stmt.where(CourseGroup.course_id == curso_id)  # type: ignore[arg-type]
    return {g.id for g in (await db.exec(stmt)).all()}


async def _validar_permisos(db, actor, student_id: int, course_id: int | None) -> None:
    """R6: docente → course_id obligatorio y alumno matriculado en SUS grupos."""
    if actor.role is UserRole.ADMIN:
        return
    if actor.role is not UserRole.DOCENTE:
        raise errors.DomainError("Solo admin o docente registran justificaciones")
    if course_id is None:
        raise errors.DomainError(
            "Como docente debes indicar el curso de la justificación (solo puedes justificar tus cursos)"
        )
    grupos_docente = await _grupos_del_docente(db, actor.id, course_id)
    if not grupos_docente:
        raise errors.DomainError("No dictas grupos de ese curso")
    matriculas = {
        r[0] if isinstance(r, tuple) else r
        for r in (
            await db.exec(
                select(Enrollment.group_id).where(
                    Enrollment.student_id == student_id,  # type: ignore[arg-type]
                    Enrollment.withdrawn_at.is_(None),  # type: ignore[union-attr]
                )
            )
        ).all()
    }
    if not (matriculas & grupos_docente):
        raise errors.DomainError("El alumno no está matriculado en ninguno de tus grupos")


async def _faltas_del_rango(
    db, student_id: int, course_id: int | None, desde: date, hasta: date
) -> list[AttendanceRecord]:
    """Faltas del alumno en el rango de fechas (del curso si se acota).

    Excluye sesiones CANCELADAS (R5: no cuentan para nada) y las ya
    justificadas (idempotencia: no se re-marcian dos veces)."""
    stmt = (
        select(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)  # type: ignore[arg-type]
        .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)  # type: ignore[arg-type]
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)  # type: ignore[arg-type]
        .where(
            AttendanceRecord.student_id == student_id,  # type: ignore[arg-type]
            AttendanceRecord.status == AttendanceStatus.FALTA,  # type: ignore[arg-type]
            AttendanceRecord.is_justified.is_(False),  # type: ignore[union-attr]
            AttendanceSession.session_date >= desde,  # type: ignore[arg-type]
            AttendanceSession.session_date <= hasta,  # type: ignore[arg-type]
            AttendanceSession.status != "cancelada",  # R5
        )
    )
    if course_id is not None:
        stmt = stmt.where(CourseGroup.course_id == course_id)  # type: ignore[arg-type]
    return list((await db.exec(stmt)).all())


async def crear(
    db: SQLModelAsyncSession,
    actor,
    *,
    student_id: int,
    course_id: int | None,
    start_date: date,
    end_date: date,
    reason: str,
    document_url: str | None = None,
    ip: str | None = None,
) -> tuple[Justification, int]:
    """R6: registra la justificación y APLICA el efecto sobre las faltas
    existentes del rango. Devuelve (justificación, faltas_afectadas)."""
    if end_date < start_date:
        raise errors.DomainError("La fecha fin no puede ser anterior a la inicio")
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE:
        raise errors.DomainError("student_id debe ser un estudiante existente")
    await _validar_permisos(db, actor, student_id, course_id)

    just = Justification(
        student_id=student_id, course_id=course_id, start_date=start_date,
        end_date=end_date, reason=reason.strip(), document_url=document_url,
        created_by=actor.id,  # type: ignore[arg-type]
    )
    db.add(just)
    await db.flush()  # obtiene just.id antes de ligar las faltas

    afectadas = 0
    for falta in await _faltas_del_rango(db, student_id, course_id, start_date, end_date):
        falta.is_justified = True
        falta.justification_id = just.id  # type: ignore[arg-type]
        db.add(falta)
        afectadas += 1

    await audit(
        db, actor, action="justificacion_creada", entity="justification",
        entity_id=just.id,
        new_value={"student_id": student_id, "course_id": course_id,
                   "from": str(start_date), "to": str(end_date),
                   "faltas_afectadas": afectadas},
        ip_address=ip,
    )
    await db.commit()
    return just, afectadas


async def eliminar(
    db: SQLModelAsyncSession, actor, justification_id: int, ip: str | None = None
) -> int:
    """R6: elimina la justificación REVERTIENDO primero el efecto (solo
    admin elimina cualquiera; docente solo las que él creó y de sus cursos)."""
    just = await db.get(Justification, justification_id)
    if just is None:
        raise errors.NotFoundError("Justificación no encontrada")
    if actor.role is not UserRole.ADMIN:
        if actor.role is not UserRole.DOCENTE or just.created_by != actor.id:
            raise errors.DomainError("Solo puedes eliminar las justificaciones que creaste")

    faltas = (
        await db.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.justification_id == justification_id,  # type: ignore[arg-type]
            )
        )
    ).all()
    revertidas = 0
    for falta in faltas:
        falta.is_justified = False
        falta.justification_id = None
        db.add(falta)
        revertidas += 1

    await db.delete(just)
    await audit(
        db, actor, action="justificacion_eliminada", entity="justification",
        entity_id=justification_id,
        old_value={"student_id": just.student_id, "course_id": just.course_id,
                   "from": str(just.start_date), "to": str(just.end_date)},
        new_value={"faltas_revertidas": revertidas},
        ip_address=ip,
    )
    await db.commit()
    return revertidas
