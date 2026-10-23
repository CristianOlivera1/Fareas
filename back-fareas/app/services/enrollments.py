from datetime import datetime

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.services.settings import semestre_vigente
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseGroup,
    Enrollment,
    ScheduleBlock,
    UserRole,
)


async def _cuenta_activos(db, group_id: int) -> int:
    return (
        await db.exec(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.group_id == group_id, Enrollment.withdrawn_at.is_(None))
        )
    ).one()

def _solapan(w1: int, i1, f1: datetime, w2: int, i2, f2) -> bool:
    return w1 == w2 and i1 < f2 and i2 < f1

async def _bloques_del_grupo(db, group_id: int) -> list[ScheduleBlock]:
    return list((await db.exec(select(ScheduleBlock).where(ScheduleBlock.group_id == group_id))).all())

async def _conflicto_de_alumno(
    db, student_id: int, grupo_destino: CourseGroup
) -> str | None:
    nuevos = await _bloques_del_grupo(db, grupo_destino.id)
    if not nuevos:
        return None
    otros = (
        await db.exec(
            select(CourseGroup, Enrollment)
            .join(Enrollment, Enrollment.group_id == CourseGroup.id)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.withdrawn_at.is_(None),
                CourseGroup.id != grupo_destino.id,
                CourseGroup.is_active,
                CourseGroup.semester_label == grupo_destino.semester_label,
            )
        )
    ).all()
    for grupo, _e in otros:
        bloques = await _bloques_del_grupo(db, grupo.id)
        for nb in nuevos:
            for ob in bloques:
                if _solapan(nb.weekday, nb.start_time, nb.end_time, ob.weekday, ob.start_time, ob.end_time):
                    curso = await db.get(Course, grupo.course_id)
                    return f"{curso.code if curso else grupo.course_id} (grupo {grupo.group_code})"
    return None

async def matricular(
    db: SQLModelAsyncSession, actor, *, group_id: int, student_id: int, ip: str | None = None
) -> Enrollment:
    grupo = await db.get(CourseGroup, group_id)
    if grupo is None:
        raise errors.NotFoundError("Grupo no encontrado")
    if not grupo.is_active:
        raise errors.DomainError("No se puede matricular en un grupo inactivo")
    if await semestre_vigente(db) != grupo.semester_label:
        raise errors.DomainError(
            f"El grupo pertenece al semestre {grupo.semester_label}, no al vigente"
        )
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE:
        raise errors.DomainError("Solo se matricula a usuarios con rol estudiante")

    activos = await _cuenta_activos(db, group_id)
    if activos >= grupo.capacity:
        raise errors.ConflictError(f"Grupo lleno ({activos}/{grupo.capacity}); crea otro grupo")

    ya = (
        await db.exec(
            select(Enrollment).where(
                Enrollment.group_id == group_id, Enrollment.student_id == student_id
            )
        )
    ).first()
    if ya is not None and ya.withdrawn_at is None:
        raise errors.ConflictError("El estudiante ya está matriculado en este grupo")

    mismo_curso = (
        await db.exec(
            select(CourseGroup, Enrollment)
            .join(Enrollment, Enrollment.group_id == CourseGroup.id)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.withdrawn_at.is_(None),
                CourseGroup.course_id == grupo.course_id,
                CourseGroup.semester_label == grupo.semester_label,
                CourseGroup.is_active,
                CourseGroup.id != group_id,
            )
        )
    ).first()
    if mismo_curso is not None:
        g, _e = mismo_curso
        curso = await db.get(Course, grupo.course_id)
        raise errors.ConflictError(
            f"El alumno ya está matriculado en el grupo {g.group_code} de "
            f"{curso.code if curso else 'ese curso'}; usa la transferencia"
        )

    choque = await _conflicto_de_alumno(db, student_id, grupo)
    if choque:
        raise errors.ConflictError(
            f"El horario del grupo se cruza con otro curso del alumno: {choque}"
        )

    if ya is not None:
        ya.withdrawn_at = None
        db.add(ya)
        enrollment = ya
        accion = "matricula_reactivada"
    else:
        enrollment = Enrollment(student_id=student_id, group_id=group_id)
        db.add(enrollment)
        accion = "matricula_creada"
    await db.flush()
    await audit(
        db, actor, action=accion, entity="enrollment", entity_id=enrollment.id,
        new_value={"student_id": student_id, "group_id": group_id,
                   "cupo": f"{activos + 1}/{grupo.capacity}"},
        ip_address=ip,
    )
    await db.commit()
    return enrollment

async def retirar(
    db: SQLModelAsyncSession, actor, *, group_id: int, student_id: int, ip: str | None = None
) -> dict:
    enrollment = (
        await db.exec(
            select(Enrollment).where(
                Enrollment.group_id == group_id, Enrollment.student_id == student_id
            )
        )
    ).first()
    if enrollment is None:
        raise errors.NotFoundError("El estudiante no está matriculado en ese grupo")
    if enrollment.withdrawn_at is not None:
        raise errors.DomainError("La matrícula ya está retirada")

    con_registros = (
        await db.exec(
            select(AttendanceRecord.id)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
            .where(
                AttendanceRecord.student_id == student_id,
                ScheduleBlock.group_id == group_id,
            )
            .limit(1)
        )
    ).first()

    if con_registros is None:
        await db.delete(enrollment)
        modo = "eliminada"
    else:
        enrollment.withdrawn_at = datetime.now()
        db.add(enrollment)
        modo = "retirada"
    await audit(
        db, actor, action="matricula_retirada", entity="enrollment",
        entity_id=enrollment.id,
        old_value={"student_id": student_id, "group_id": group_id},
        new_value={"modo": modo},
        ip_address=ip,
    )
    await db.commit()
    return {"modo": modo, "student_id": student_id, "group_id": group_id}

async def transferir(
    db: SQLModelAsyncSession, actor, *, group_id: int, student_id: int,
    destino_group_id: int, ip: str | None = None,
) -> dict:
    origen = await db.get(CourseGroup, group_id)
    destino = await db.get(CourseGroup, destino_group_id)
    if origen is None or destino is None:
        raise errors.NotFoundError("Grupo de origen o destino no encontrado")
    if origen.course_id != destino.course_id:
        raise errors.DomainError("La transferencia es entre grupos del MISMO curso")
    if destino_group_id == group_id:
        raise errors.DomainError("El grupo destino es el mismo de origen")
    if not destino.is_active:
        raise errors.DomainError("El grupo destino está inactivo")
    if await semestre_vigente(db) != destino.semester_label:
        raise errors.DomainError("El grupo destino no pertenece al semestre vigente")

    activos = await _cuenta_activos(db, destino_group_id)
    if activos >= destino.capacity:
        raise errors.ConflictError(f"Grupo destino lleno ({activos}/{destino.capacity})")
    choque = await _conflicto_de_alumno(db, student_id, destino)
    if choque:
        raise errors.ConflictError(f"El horario del grupo destino se cruza con: {choque}")

    enrollment = (
        await db.exec(
            select(Enrollment).where(
                Enrollment.group_id == group_id, Enrollment.student_id == student_id
            )
        )
    ).first()
    if enrollment is None or enrollment.withdrawn_at is not None:
        raise errors.NotFoundError("El estudiante no está matriculado (activo) en el grupo origen")

    enrollment.withdrawn_at = datetime.now()
    db.add(enrollment)
    nuevo = Enrollment(student_id=student_id, group_id=destino_group_id)
    db.add(nuevo)
    await db.flush()
    await audit(
        db, actor, action="matricula_transferida", entity="enrollment",
        entity_id=nuevo.id,
        new_value={"student_id": student_id, "desde_grupo": group_id,
                   "a_grupo": destino_group_id},
        ip_address=ip,
    )
    await db.commit()
    return {"student_id": student_id, "desde": group_id, "hacia": destino_group_id}
