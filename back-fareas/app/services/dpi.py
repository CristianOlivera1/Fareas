"""DPI — R7 (Deficiencia Personal Injustificada).

- Porcentaje: faltas NO justificadas / sesiones dictadas válidas (vista
  ``v_student_dpi``: cerradas, no canceladas, sin needs_review, semestre
  vigente, dentro del rango de matrícula del alumno).
- Niveles (decisión 2026-10-11: inhabilitación al SUPERAR el límite):
    * 'limite' cuando absence_percent > dpi_limit_percent (30)
    * 'alerta' cuando absence_percent >= dpi_alert_percent (20)
  Las tardanzas NO suman; las justificadas NO cuentan.
- Correo SOLO si sessions_held >= dpi_min_sessions (4) y UNA vez por nivel
  y semestre (tabla dpi_alert_sent: INSERT … ON CONFLICT DO NOTHING).
- 'Faltas restantes' se calcula contra el total PLANIFICADO del semestre.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text as sql_text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services.settings import get_settings_row
from app.tables import (
    AppSettings,
    AppUser,
    CourseGroup,
    DpiAlertSent,
    Enrollment,
    Holiday,
    ScheduleBlock,
)

logger = logging.getLogger("fareas.dpi")

# ¿Para qué nivel se pregunta primero? Si un salto directo pasa el límite,
# solo se envía 'limite' (R7: nunca dos correos el mismo día por alumno).
_NIVELES = ("limite", "alerta")


def nivel_de(percent: float, cfg: AppSettings) -> str | None:
    """Nivel de riesgo de un porcentaje (None = sin alerta)."""
    if percent > float(cfg.dpi_limit_percent):
        return "limite"
    if percent >= float(cfg.dpi_alert_percent):
        return "alerta"
    return None


async def _enviado_antes(db, student_id: int, course_id: int, semestre: str, level: str) -> bool:
    ya = (
        await db.exec(
            select(DpiAlertSent).where(
                DpiAlertSent.student_id == student_id,  # type: ignore[arg-type]
                DpiAlertSent.course_id == course_id,  # type: ignore[arg-type]
                DpiAlertSent.semester_label == semestre,  # type: ignore[arg-type]
                DpiAlertSent.level == level,  # type: ignore[arg-type]
            )
        )
    ).first()
    return ya is not None


async def marcar_enviado(db, student_id: int, course_id: int, semestre: str, level: str) -> bool:
    """INSERT de control con dedup (ON CONFLICT DO NOTHING): True solo la
    PRIMERA vez que se envía ese nivel (alumno, curso, semestre)."""
    from sqlalchemy import text as _sql

    fila = (
        await db.exec(
            _sql(
                "INSERT INTO dpi_alert_sent (student_id, course_id, semester_label, level) "
                "VALUES (:s, :c, :sem, :lvl) ON CONFLICT DO NOTHING RETURNING student_id"
            ).bindparams(s=student_id, c=course_id, sem=semestre, lvl=level)
        )
    ).first()
    return fila is not None


async def procesar_alertas_cierre(db, session) -> int:
    """R7 tras el cierre: correos de nivel a quienes cruzaron umbrales con
    esta sesión. Solo alumnos con faltas nuevas en esta sesión (los demás se
    notificaron cuando cruzaron). Devuelve correos enviados."""
    from sqlalchemy import text as _sql

    bloque = await db.get(ScheduleBlock, session.block_id)
    grupo = await db.get(CourseGroup, bloque.group_id) if bloque else None
    if grupo is None:
        return 0
    cfg = await get_settings_row(db)

    # Faltantes de esta sesión = los que el cierre acaba de marcar 'falta'.
    filas = (
        await db.exec(
            _sql(
                "SELECT ar.student_id, v.course_code, v.sessions_held, v.absences, "
                "v.absence_percent FROM attendance_record ar "
                "JOIN v_student_dpi v ON v.student_id = ar.student_id "
                " AND v.course_id = :curso "
                "WHERE ar.session_id = :sesion AND ar.status = 'falta'"
            ).bindparams(curso=grupo.course_id, sesion=session.id)
        )
    ).all()

    from app.services.notifications import send_dpi_alert

    enviadas = 0
    for fila in filas:
        sid = int(fila.student_id)
        percent = float(fila.absence_percent)
        nivel = nivel_de(percent, cfg)
        if nivel is None or int(fila.sessions_held) < cfg.dpi_min_sessions:
            continue
        if await _enviado_antes(db, sid, grupo.course_id, cfg.semester_label, nivel):
            continue
        if not await marcar_enviado(db, sid, grupo.course_id, cfg.semester_label, nivel):
            continue
        alumno = await db.get(AppUser, sid)
        if alumno is None or not alumno.email:
            continue
        ok = await send_dpi_alert(
            alumno.email, alumno.full_name, str(fila.course_code),
            int(fila.sessions_held), int(fila.absences), percent,
            float(cfg.dpi_limit_percent), nivel=nivel,
        )
        if ok:
            enviadas += 1
    if enviadas:
        await db.commit()
    return enviadas


# Resumen por alumno (R7) — sesiones planificadas y faltas restantes
async def sesiones_planificadas(
    db: SQLModelAsyncSession, student_id: int, course_id: int, cfg: AppSettings
) -> int | None:
    """Total de sesiones PLANIFICADAS del curso para el alumno en el semestre:
    fechas entre max(semester_start, enrolled_at) y semester_end con el día
    de semana de cada bloque del grupo activo, menos feriados.
    None si el semestre no tiene fechas (la UI muestra '—')."""
    if cfg.semester_start is None or cfg.semester_end is None:
        return None

    grupo = (
        await db.exec(
            select(CourseGroup)
            .join(Enrollment, Enrollment.group_id == CourseGroup.id)
            .where(
                CourseGroup.course_id == course_id,  # type: ignore[arg-type]
                CourseGroup.semester_label == cfg.semester_label,  # type: ignore[arg-type]
                CourseGroup.is_active,  # type: ignore[arg-type]
                Enrollment.student_id == student_id,  # type: ignore[arg-type]
                Enrollment.withdrawn_at.is_(None),  # type: ignore[union-attr]
            )
            .limit(1)
        )
    ).first()
    if grupo is None:
        return None
    # La matrícula más antigua entre los grupos del curso (el alumno pudo
    # transferirse de grupo: sus faltas anteriores se conservan y se suman).
    enrol = (
        await db.exec(
            select(Enrollment.enrolled_at)
            .where(
                Enrollment.student_id == student_id,  # type: ignore[arg-type]
                Enrollment.group_id == grupo.id,  # type: ignore[arg-type]
            )
        )
    ).first()
    # OJO: una select() de UNA columna devuelve escalares (no tuplas).
    enrolled_at = enrol[0] if isinstance(enrol, tuple) else enrol
    desde = cfg.semester_start
    if isinstance(enrolled_at, datetime) and enrolled_at.date() > desde:
        desde = enrolled_at.date()

    bloques = (
        await db.exec(select(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id))  # type: ignore[arg-type]
    ).all()
    if not bloques:
        return None
    weekdays = {b.weekday for b in bloques}

    feriados = {
        h[0] if isinstance(h, tuple) else h
        for h in (await db.exec(select(Holiday.holiday_date))).all()
    }

    total = 0
    d = desde
    while d <= cfg.semester_end:
        if d.isoweekday() in weekdays and d not in feriados:
            total += 1
        d += timedelta(days=1)
    return total


async def resumen_alumno(db, student_id: int) -> list[dict]:
    """R7: por curso del alumno — sesiones, faltas (y justificadas), tardanzas,
    porcentaje, nivel, planificadas, permitidas y restantes."""
    cfg = await get_settings_row(db)
    filas = (
        await db.exec(
            sql_text(
                "SELECT course_id, course_code, course_name, sessions_held, absences, "
                "absence_percent, justified_absences, lates FROM v_student_dpi "
                "WHERE student_id = :alumno ORDER BY course_code"
            ).bindparams(alumno=student_id)
        )
    ).all()

    out = []
    for f in filas:
        percent = float(f.absence_percent)
        nivel = nivel_de(percent, cfg)
        planificadas = await sesiones_planificadas(db, student_id, int(f.course_id), cfg)
        limite = float(cfg.dpi_limit_percent)
        faltas_permitidas = None
        if planificadas is not None:
            faltas_permitidas = int(planificadas * limite / 100)
        out.append(
            {
                "course_id": int(f.course_id),
                "course_code": f.course_code,
                "course_name": f.course_name,
                "sessions_held": int(f.sessions_held),
                "absences": int(f.absences),
                "justified_absences": int(f.justified_absences),
                "lates": int(f.lates),
                "absence_percent": percent,
                "nivel": nivel,
                "sesiones_planificadas": planificadas,
                "faltas_permitidas": faltas_permitidas,
                "faltas_restantes": (
                    max(0, faltas_permitidas - int(f.absences))
                    if faltas_permitidas is not None
                    else None
                ),
                "semester_label": cfg.semester_label,
            }
        )
    return out
