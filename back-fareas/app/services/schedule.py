"""Validación de horarios y choques - RF-06.

La BD NO impone esta regla a propósito: dos grupos pueden dictar bloques
simultáneos si son en aulas y docentes distintos (grupos paralelos, Tabla 2).
La API la aplica al crear cada bloque con la consulta de solapamiento:

    solapan si: mismo día  AND  nuevo.inicio < existente.fin  AND
                            existente.inicio < nuevo.fin
"""
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.tables import CourseGroup, ScheduleBlock


async def _raise_if_conflict(
    db: SQLModelAsyncSession,
    group: CourseGroup,
    *,
    weekday: int,
    start_time,
    end_time,
    exclude_block_id: int | None = None,
) -> None:
    """Rechaza si en ese día/rango ya hay un bloque activo que comparta la
    MISMA AULA o el MISMO DOCENTE del grupo (RF-06).

    Dos grupos paralelos con aula y docente distintos NO chocan aunque sus
    bloques coincidan en hora: por eso el OR sobre room_id/teacher_id."""
    rows = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.is_active,  # type: ignore[arg-type]
                CourseGroup.id != group.id,  # los bloques propios del grupo no chocan
                or_(
                    CourseGroup.room_id == group.room_id,      # misma aula
                    CourseGroup.teacher_id == group.teacher_id,  # mismo docente
                ),
                ScheduleBlock.weekday == weekday,
                ScheduleBlock.start_time < end_time,
                ScheduleBlock.end_time > start_time,
                ScheduleBlock.id != exclude_block_id,  # para updates (None no filtra)
            )
        )
    ).all()
    for _block, other in rows:
        raise errors.ConflictError(
            f"Choque de horario: el grupo #{other.id} ({other.group_code}) ya ocupa esa aula o docente "
            f"el día {weekday} entre {start_time} y {end_time}"
        )


async def add_block(
    db: SQLModelAsyncSession,
    actor,
    *,
    group_id: int,
    weekday: int,
    start_time,
    end_time,
    ip: str | None = None,
    commit: bool = True,
) -> ScheduleBlock:
    """Añade un bloque horario a un grupo validando solapamientos (RF-06).

    ``commit=False`` deja el commit al llamador: la importación masiva
    RF-07 necesita TODO O NADA (un choque revienta la propuesta completa).
    """
    group = await db.get(CourseGroup, group_id)
    if group is None or not group.is_active:
        raise errors.NotFoundError("Grupo no encontrado")
    if start_time >= end_time:
        raise errors.DomainError("La hora de inicio debe ser menor que la de fin")

    await _raise_if_conflict(db, group, weekday=weekday, start_time=start_time, end_time=end_time)
    block = ScheduleBlock(group_id=group_id, weekday=weekday, start_time=start_time, end_time=end_time)
    db.add(block)
    await db.flush()  # obtiene block.id para la bitácora antes de confirmar
    await audit(
        db,
        actor,
        action="bloque_creado",
        entity="schedule_block",
        entity_id=block.id,
        new_value={"group_id": group_id, "weekday": weekday,
                   "start_time": str(start_time), "end_time": str(end_time)},
        ip_address=ip,
    )
    if commit:
        await db.commit()
    await db.refresh(block)
    return block


async def update_block(db, actor, *, block_id: int, data: dict, ip: str | None = None) -> ScheduleBlock:
    """Modifica un bloque validando choques contra el resto (RF-06)."""
    block = await db.get(ScheduleBlock, block_id)
    if block is None:
        raise errors.NotFoundError("Bloque horario no encontrado")
    weekday = data.get("weekday", block.weekday)
    start_time = data.get("start_time", block.start_time)
    end_time = data.get("end_time", block.end_time)
    if start_time >= end_time:
        raise errors.DomainError("La hora de inicio debe ser menor que la de fin")

    block_group = await db.get(CourseGroup, block.group_id)
    if block_group is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    await _raise_if_conflict(
        db,
        block_group,
        weekday=weekday,
        start_time=start_time,
        end_time=end_time,
        exclude_block_id=block.id,
    )
    old = {"weekday": block.weekday, "start_time": str(block.start_time), "end_time": str(block.end_time)}
    block.weekday = weekday
    block.start_time = start_time
    block.end_time = end_time
    db.add(block)
    await audit(
        db,
        actor,
        action="bloque_actualizado",
        entity="schedule_block",
        entity_id=block.id,
        old_value=old,
        new_value={"weekday": weekday, "start_time": str(start_time), "end_time": str(end_time)},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(block)
    return block
