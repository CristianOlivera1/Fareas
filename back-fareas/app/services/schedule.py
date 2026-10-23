from datetime import time

from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.services.enrollments import _conflicto_de_alumno
from app.services.settings import get_settings_row
from app.tables import (
    AppUser,
    AttendanceSession,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
    UserRole,
)

DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes"}
MAX_BLOCK_MINUTES = 120


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

def _validar_duracion(start_time: time, end_time: time) -> None:
    minutos = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
    if minutos > MAX_BLOCK_MINUTES:
        raise errors.DomainError("El bloque no puede durar más de 2 horas")

async def _aula_del_bloque(db: SQLModelAsyncSession, room_id: int | None) -> Room | None:
    if room_id is None:
        return None
    room = await db.get(Room, room_id)
    if room is None:
        raise errors.NotFoundError("Aula no encontrada")
    if not room.is_active:
        raise errors.DomainError(f"El aula {room.code} está inactiva")
    return room

async def _docente_valido(db: SQLModelAsyncSession, teacher_id: int) -> AppUser:
    docente = await db.get(AppUser, teacher_id)
    if docente is None or docente.role is not UserRole.DOCENTE or not docente.is_active:
        raise errors.DomainError("El docente asignado no existe o no está activo")
    return docente

async def _bloque_tiene_sesiones(db: SQLModelAsyncSession, block_id: int) -> bool:
    return (
        await db.exec(
            select(AttendanceSession.id).where(AttendanceSession.block_id == block_id).limit(1)
        )
    ).first() is not None

async def _grupo_tiene_sesiones(db: SQLModelAsyncSession, group_id: int) -> bool:
    return (
        await db.exec(
            select(AttendanceSession.id)
            .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
            .where(ScheduleBlock.group_id == group_id)
            .limit(1)
        )
    ).first() is not None

async def _raise_if_conflict(
    db: SQLModelAsyncSession,
    group: CourseGroup,
    *,
    room: Room | None,
    weekday: int,
    start_time,
    end_time,
    exclude_block_id: int | None = None,
    teacher_id: int | None = None,
    incluir_docente: bool = True,
) -> None:
    docente_id = teacher_id if teacher_id is not None else group.teacher_id
    condiciones = []
    if room is not None:
        condiciones.append(ScheduleBlock.room_id == room.id)
    if incluir_docente and docente_id is not None:
        condiciones.append(CourseGroup.teacher_id == docente_id)
    if not condiciones:
        return
    rows = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.is_active,
                ScheduleBlock.group_id != group.id,
                CourseGroup.semester_label == group.semester_label,
                or_(*condiciones),
                ScheduleBlock.weekday == weekday,
                ScheduleBlock.start_time < end_time,
                ScheduleBlock.end_time > start_time,
                ScheduleBlock.id != exclude_block_id,
            )
        )
    ).all()
    for block, other in rows:
        quien = (
            f"el aula {room.code}"
            if room is not None and block.room_id == room.id
            else "el docente"
        )
        raise errors.ConflictError(
            f"Choque de horario: el grupo #{other.id} ({other.group_code}) ya ocupa {quien} "
            f"el {DIAS[weekday]} entre {start_time} y {end_time}"
        )

async def _raise_if_teacher_conflict(
    db: SQLModelAsyncSession,
    group: CourseGroup,
    teacher_id: int,
    exclude_block_id: int | None = None,
) -> None:
    bloques = (
        await db.exec(select(ScheduleBlock).where(ScheduleBlock.group_id == group.id))
    ).all()
    for bloque in bloques:
        await _raise_if_conflict(
            db,
            group,
            room=None,
            teacher_id=teacher_id,
            weekday=bloque.weekday,
            start_time=bloque.start_time,
            end_time=bloque.end_time,
            exclude_block_id=exclude_block_id,
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
    teacher_id: int | None = None,
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
    _validar_duracion(start_time, end_time)

    if teacher_id is not None:
        await _docente_valido(db, teacher_id)
        if group.teacher_id is None:
            await _raise_if_teacher_conflict(db, group, teacher_id)
            group.teacher_id = teacher_id
            db.add(group)
        elif group.teacher_id != teacher_id:
            raise errors.DomainError("El grupo ya tiene otro docente")

    room = await _aula_del_bloque(db, room_id)
    await _raise_if_conflict(db, group, room=room, weekday=weekday,
                             start_time=start_time, end_time=end_time)
    block = ScheduleBlock(group_id=group_id, room_id=room.id if room else None,
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
        new_value={"group_id": group_id, "room_id": room.id if room else None,
                   "teacher_id": group.teacher_id, "weekday": weekday,
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
    _validar_duracion(start_time, end_time)

    block_group = await db.get(CourseGroup, block.group_id)
    if block_group is None:
        raise errors.NotFoundError("El grupo del bloque no existe")

    docente_anterior = block_group.teacher_id
    nuevo_docente = (
        data["teacher_id"] if "teacher_id" in data else block_group.teacher_id
    )
    if nuevo_docente is not None:
        await _docente_valido(db, nuevo_docente)
    if nuevo_docente != docente_anterior:
        if nuevo_docente is None and await _grupo_tiene_sesiones(db, block_group.id):
            raise errors.ConflictError(
                "No se puede quitar el docente de un grupo con sesiones registradas"
            )
        if nuevo_docente is not None:
            await _raise_if_teacher_conflict(
                db, block_group, nuevo_docente, exclude_block_id=block.id
            )

    nuevo_room_id = data["room_id"] if "room_id" in data else block.room_id
    room = await _aula_del_bloque(db, nuevo_room_id)
    if room is None and block.room_id is not None:
        if await _bloque_tiene_sesiones(db, block.id):
            raise errors.ConflictError(
                "No se puede quitar el aula de un bloque con sesiones registradas"
            )
    await _raise_if_conflict(
        db,
        block_group,
        room=room,
        teacher_id=nuevo_docente,
        incluir_docente=nuevo_docente is not None,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        exclude_block_id=block.id,
    )
    old = {"room_id": block.room_id, "teacher_id": docente_anterior,
           "weekday": block.weekday, "start_time": str(block.start_time),
           "end_time": str(block.end_time)}
    block_group.teacher_id = nuevo_docente
    db.add(block_group)
    block.room_id = room.id if room else None
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
        new_value={"room_id": room.id if room else None,
                   "teacher_id": nuevo_docente, "weekday": weekday,
                   "start_time": str(start_time), "end_time": str(end_time)},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(block)
    return block
