from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.tables import AppSettings, CourseGroup


async def get_settings_row(db: SQLModelAsyncSession) -> AppSettings:
    s = await db.get(AppSettings, 1)
    if s is None:
        raise errors.DomainError("Falta la fila app_settings id=1 (ejecutar 002_seed.sql)")
    return s

async def semestre_vigente(db: SQLModelAsyncSession) -> str:
    return (await get_settings_row(db)).semester_label

async def semestre_en_curso(db: SQLModelAsyncSession, d: date | None = None) -> bool:
    d = d or date.today()
    s = await get_settings_row(db)
    if s.semester_start is None or s.semester_end is None:
        return True
    return s.semester_start <= d <= s.semester_end

async def grupo_del_semestre_o_404(
    db: SQLModelAsyncSession, group_id: int, vigente: str
) -> CourseGroup:
    group = await db.get(CourseGroup, group_id)
    if group is None:
        raise errors.NotFoundError("Grupo no encontrado")
    return group

async def semesters_con_grupos(db: SQLModelAsyncSession) -> list[str]:
    rows = (
        await db.exec(
            select(CourseGroup.semester_label)
            .distinct()
            .order_by(CourseGroup.semester_label)
        )
    ).all()
    return [r[0] if isinstance(r, tuple) else r for r in rows]
