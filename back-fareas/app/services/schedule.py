from datetime import time

from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.services.enrollments import _conflicto_de_alumno
from app.services.settings import get_settings_row, semestre_vigente
from app.tables import CourseGroup, Enrollment, Room, ScheduleBlock

DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes"}


def _validar_dia(weekday: int) -> None:
    if weekday not in DIAS:
        raise errors.DomainError(
            f"Día inválido: {weekday}. La semana lectiva es de Lunes (1) a Viernes (5)."
        )

async def _validar_franja(db: SQLModelAsyncSession, start_time: time, end_time: time) -> None:
    cfg = await get_settings_row(db)
    if start_time < cfg.attendance_hour_start or end_time > cfg.attendance_hour_end:
        raise errors.DomainError(
            "El bloque debe estar dentro de la franja de clases "
            f"({cfg.attendance_hour_start.strftime('%H:%M')}–"
            f"{cfg.attendance_hour_end.strftime('%H:%M')})"
        )

async def _aula_del_bloque(db: SQLModelAsyncSession, room_id: int | None) -> Room:
    if room_id is None:
        raise errors.DomainError("Indica el aula donde se dicta el bloque")
    room = await db.get(Room, room_id)
    if room is None:
        raise errors.NotFoundError("Aula no encontrada")
    if not room.is_active:
        raise errors.DomainError(f"El aula {room.code} está inactiva")
    return room

async def _raise_if_conflict(
    db: SQLModelAsyncSession,
    group: CourseGroup,
    *,
    room: Room,
    weekday: int,
    start_time,
    end_time,
    exclude_block_id: int | None = None,
) -> None:
    vigente = await semestre_vigente(db)
    rows = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.is_active,
                ScheduleBlock.group_id != group.id,
                CourseGroup.semester_label == vigente,
                or_(
                    ScheduleBlock.room_id == room.id,
                    CourseGroup.teacher_id == group.teacher_id,
                ),
                ScheduleBlock.weekday == weekday,
                ScheduleBlock.start_time < end_time,
                ScheduleBlock.end_time > start_time,
                ScheduleBlock.id != exclude_block_id,
            )
        )
    ).all()
    for block, other in rows:
        quien = f"el aula {room.code}" if block.room_id == room.id else "el docente"
        raise errors.ConflictError(
            f"Choque de horario: el grupo #{other.id} ({other.group_code}) ya ocupa {quien} "
            f"el {DIAS[weekday]} entre {start_time} y {end_time}"
        )

async def _raise_si_alumnos_chocan(
    db: SQLModelAsyncSession, group: CourseGroup
) -> None:
    matriculas = (
        await db.exec(
            select(Enrollment.student_id).where(
                Enrollment.group_id == group.id,
                Enrollment.withdrawn_at.is_(None),
            )
        )
    ).all()
    casos: list[str] = []
    for fila in matriculas:
        sid = fila[0] if isinstance(fila, tuple) else fila
        choque = await _conflicto_de_alumno(db, sid, group)
        if choque:
            casos.append(f"alumno #{sid} choca con {choque}")
        if len(casos) >= 5:
            break
    if casos:
        raise errors.ConflictError(
            "El bloque cruzaría el horario de alumnos ya matriculados: " + "; ".join(casos)
        )

async def add_block(
    db: SQLModelAsyncSession,
    actor,
    *,
    group_id: int,
    weekday: int,
    start_time,
    end_time,
    room_id: int | None,
    ip: str | None = None,
    commit: bool = True,
) -> ScheduleBlock:
    group = await db.get(CourseGroup, group_id)
    if group is None or not group.is_active:
        raise errors.NotFoundError("Grupo no encontrado")
    _validar_dia(weekday)
    if start_time >= end_time:
        raise errors.DomainError("La hora de inicio debe ser menor que la de fin")
    await _validar_franja(db, start_time, end_time)

    room = await _aula_del_bloque(db, room_id)
    await _raise_if_conflict(db, group, room=room, weekday=weekday,
                             start_time=start_time, end_time=end_time)
    block = ScheduleBlock(group_id=group_id, room_id=room.id,
                          weekday=weekday, start_time=start_time, end_time=end_time)
    db.add(block)
    await db.flush()
    await _raise_si_alumnos_chocan(db, group)
    await audit(
        db,
        actor,
        action="bloque_creado",
        entity="schedule_block",
        entity_id=block.id,
        new_value={"group_id": group_id, "room_id": room.id, "weekday": weekday,
                   "start_time": str(start_time), "end_time": str(end_time)},
        ip_address=ip,
    )
    if commit:
        await db.commit()
    await db.refresh(block)
    return block

async def update_block(db, actor, *, block_id: int, data: dict, ip: str | None = None) -> ScheduleBlock:
    block = await db.get(ScheduleBlock, block_id)
    if block is None:
        raise errors.NotFoundError("Bloque horario no encontrado")
    weekday = data.get("weekday", block.weekday)
    start_time = data.get("start_time", block.start_time)
    end_time = data.get("end_time", block.end_time)
    _validar_dia(weekday)
    if start_time >= end_time:
        raise errors.DomainError("La hora de inicio debe ser menor que la de fin")
    await _validar_franja(db, start_time, end_time)

    block_group = await db.get(CourseGroup, block.group_id)
    if block_group is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    room = await _aula_del_bloque(db, data.get("room_id", block.room_id))
    await _raise_if_conflict(
        db,
        block_group,
        room=room,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        exclude_block_id=block.id,
    )
    old = {"room_id": block.room_id, "weekday": block.weekday,
           "start_time": str(block.start_time), "end_time": str(block.end_time)}
    block.room_id = room.id
    block.weekday = weekday
    block.start_time = start_time
    block.end_time = end_time
    db.add(block)
    await db.flush()
    await _raise_si_alumnos_chocan(db, block_group)
    await audit(
        db,
        actor,
        action="bloque_actualizado",
        entity="schedule_block",
        entity_id=block.id,
        old_value=old,
        new_value={"room_id": room.id, "weekday": weekday,
                   "start_time": str(start_time), "end_time": str(end_time)},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(block)
    return block
