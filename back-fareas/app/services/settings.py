"""Acceso a los parámetros del semestre (RF-34) y helpers de reglas.

Pequeño servicio para no repetir ``db.get(AppSettings, 1)`` con validaciones
en cada módulo: ``get_settings_row`` y ``semestre_vigente`` viven aquí.

R1: el semestre vigente es ``app_settings.semester_label``; cambiarlo NO
modifica datos existentes (los grupos conservan su etiqueta histórica).
"""
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.tables import AppSettings, CourseGroup


async def get_settings_row(db: SQLModelAsyncSession) -> AppSettings:
    """Fila única de parámetros (id=1); 500 si falta (002_seed no aplicado)."""
    s = await db.get(AppSettings, 1)
    if s is None:
        raise errors.DomainError("Falta la fila app_settings id=1 (ejecutar 002_seed.sql)")
    return s


async def semestre_vigente(db: SQLModelAsyncSession) -> str:
    """R1: etiqueta del semestre vigente (grupos, sesiones y DPI)."""
    return (await get_settings_row(db)).semester_label


async def semestre_en_curso(db: SQLModelAsyncSession, d: date | None = None) -> bool:
    """R1: ¿la fecha cae dentro de semester_start..semester_end?

    Si alguna de las dos fechas es NULL (o ambas), no se restringe: True.
    """
    d = d or date.today()
    s = await get_settings_row(db)
    if s.semester_start is None or s.semester_end is None:
        return True
    return s.semester_start <= d <= s.semester_end


async def grupo_del_semestre_o_404(
    db: SQLModelAsyncSession, group_id: int, vigente: str
) -> CourseGroup:
    """Grupo activo del semestre vigente (los de semestres anteriores no
    abren sesiones ni participan en choques/listados por defecto)."""
    group = await db.get(CourseGroup, group_id)
    if group is None:
        raise errors.NotFoundError("Grupo no encontrado")
    return group


async def semesters_con_grupos(db: SQLModelAsyncSession) -> list[str]:
    """Etiquetas distintas con grupos creados (GET /settings/semesters)."""
    rows = (
        await db.exec(
            select(CourseGroup.semester_label)
            .distinct()  # type: ignore[arg-type]
            .order_by(CourseGroup.semester_label)  # type: ignore[arg-type]
        )
    ).all()
    return [r[0] if isinstance(r, tuple) else r for r in rows]
