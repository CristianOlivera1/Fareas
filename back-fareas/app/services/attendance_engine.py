"""Motor de asistencia (Bloque 6) — RF-21…RF-26, el corazón del sistema.

Lógica pura sobre la BD, testeable sin HTTP. Los routers (marca manual),
el scheduler (cierre automático) y el bucle de cámaras llaman aquí.

Reglas:
- RF-23: 'asistio' dentro del bloque; 'tardanza' dentro de
  late_tolerance_minutes tras el fin; después la puerta responde azul.
- Marca ÚNICA por (session_id, student_id) — UNIQUE de la BD; el cooldown
  del pipeline solo evita repetir el verde en la puerta.
- RF-26: al cerrar se genera 'falta' (marked_at NULL) para cada matriculado
  sin registro. No se abren sesiones en feriados (RF-09).
- RF-24: al cerrar, quienes cruzan dpi_alert_percent reciben correo.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.tables import (
    AppSettings,
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    CourseGroup,
    Holiday,
    Room,
    ScheduleBlock,
    SessionStatus,
)

logger = logging.getLogger("fareas.attendance")

# Zona de la facultad: Perú = UTC-5, sin DST todo el año.
PERU_TZ = timezone(timedelta(hours=-5))


def ahora_peru() -> datetime:
    """Ahora en la zona de la facultad (aware, UTC-5)."""
    return datetime.now(PERU_TZ)


def _to_peru(dt: datetime) -> datetime:
    """Normaliza a la zona Perú (naive = hora local asumida)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PERU_TZ)
    return dt.astimezone(PERU_TZ)


def _naive_peru(dt: datetime) -> datetime:
    """Convierte a naive en hora Perú (para comparar con TIME de la BD)."""
    return _to_peru(dt).replace(tzinfo=None)


def _combo(hora: time, d: date) -> datetime:
    """Combina date+time naive en hora local Perú."""
    return datetime.combine(d, hora)


# ---------------------------------------------------------------------------
# Resolución de sesión (RF-26: una sesión por bloque y fecha)
# ---------------------------------------------------------------------------
async def es_feriado(db: SQLModelAsyncSession, d: date) -> bool:
    """RF-09: no se abren sesiones en feriados/paros."""
    return (await db.exec(select(Holiday).where(Holiday.holiday_date == d))).first() is not None


async def resolver_sesion(
    db: SQLModelAsyncSession,
    room_id: int,
    now: datetime | None = None,
) -> tuple[AttendanceSession | None, ScheduleBlock | None]:
    """Aula → sesión activa a esa hora (crea la sesión si no existe).

    Devuelve (sesión, bloque) o (None, None) si no hay clase: feriado,
    fuera del bloque + tolerancia, aula sin grupos activos, sesión ya
    cerrada o fuera del horario de asistencia (app_settings, RF-34).
    """
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    hoy = now.date()
    weekday = hoy.isoweekday()  # 1=Lunes … 7=Domingo (convención del esquema)
    hora_actual = now.time()

    if await es_feriado(db, hoy):
        return None, None
    if await db.get(Room, room_id) is None:
        return None, None

    settings = await db.get(AppSettings, 1)
    if settings is None:
        raise errors.DomainError("Falta la fila app_settings id=1 (ejecutar 002_seed.sql)")
    if not (settings.attendance_hour_start <= hora_actual < settings.attendance_hour_end):
        return None, None

    tolerancia = timedelta(minutes=settings.late_tolerance_minutes)
    pares = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.room_id == room_id,
                CourseGroup.is_active,  # type: ignore[arg-type]
                ScheduleBlock.weekday == weekday,
                ScheduleBlock.start_time <= hora_actual,
            )
        )
    ).all()
    # Ventana de tardanza (RF-23): end + tolerancia se calcula en Python
    # porque PostgreSQL no permite aritmética directa sobre TIME en el filtro.
    ahora_dt = _combo(hora_actual, hoy)
    pares = [(b, g) for (b, g) in pares if ahora_dt < _combo(b.end_time, hoy) + tolerancia]
    if not pares:
        return None, None

    bloque, _grupo = min(pares, key=lambda par: par[0].start_time)

    sesion = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == bloque.id,  # type: ignore[arg-type]
                AttendanceSession.session_date == hoy,
            )
        )
    ).first()
    if sesion is None:
        sesion = AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA)
        db.add(sesion)
        await db.flush()
    elif sesion.status is SessionStatus.CERRADA:
        return None, None  # ya cerró; no se reabre
    return sesion, bloque


# ---------------------------------------------------------------------------
# Marca de asistencia (RF-21 / RF-23)
# ---------------------------------------------------------------------------
async def registrar_marca(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    student_id: int,
    *,
    similarity: float | None = None,
    method: str = "facial",
    status_override: str | None = None,  # marca manual RF-21: fija el estado
    now: datetime | None = None,
    audit_actor=None,
    audit_ip: str | None = None,
) -> AttendanceRecord:
    """Inserta la marca ÚNICA del alumno clasificando RF-23.

    ConflictError si ya existe (la BD impone UNIQUE; el cooldown del
    pipeline evita llegar aquí dos veces seguidas). ``method='manual'`` la
    usa el docente desde la app (RF-15/RF-21), opcionalmente con
    ``status_override`` para fijar el estado a mano.
    """
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")

    ya = (
        await db.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session.id,  # type: ignore[arg-type]
                AttendanceRecord.student_id == student_id,
            )
        )
    ).first()
    if ya is not None:
        raise errors.ConflictError("El estudiante ya tiene registro en esta sesión")

    fin = _combo(bloque.end_time, session.session_date)
    if status_override is not None:
        status = status_override
    else:
        # RF-23: asistio dentro del bloque; TARDANZA si llega tras el fin
        # pero dentro de la tolerancia (la ventana que aún abre la sesión);
        # después de eso resolver_sesion() ya no abre → falta por cierre.
        status = "tardanza" if now > fin else "asistio"
    status_enum = AttendanceStatus(status)  # valida y bind con el enum de PG

    record = AttendanceRecord(
        session_id=session.id,  # type: ignore[arg-type]
        student_id=student_id,
        status=status_enum,
        marked_at=now,
        method=method,
        similarity=similarity,
    )
    db.add(record)
    await db.flush()
    if audit_actor is not None:
        await audit(
            db, audit_actor, action="marca_manual", entity="attendance_record",
            entity_id=record.id,
            new_value={"student_id": student_id, "session_id": session.id, "status": status},
            ip_address=audit_ip,
        )
    return record


# ---------------------------------------------------------------------------
# Cierre de sesión (RF-26) → faltas automáticas + alertas DPI (RF-24)
# ---------------------------------------------------------------------------
async def cerrar_sesion(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    *,
    actor=None,  # None = sistema (scheduler); AppUser = cierre manual admin
    ip: str | None = None,
) -> dict:
    """Cierra la sesión: faltas para matriculados sin marca y alertas DPI.

    Idempotente: si ya está cerrada no repite nada. Devuelve un resumen.
    """
    if session.status is SessionStatus.CERRADA:
        return {"session_id": session.id, "status": "ya_cerrada", "faltas": 0, "alertas": 0}

    # Matriculados del grupo del bloque
    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")
    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")

    from app.tables import Enrollment

    matriculados = (
        await db.exec(select(Enrollment).where(Enrollment.group_id == grupo.id))
    ).all()
    con_marca = {
        r.student_id
        for r in (
            await db.exec(
                select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)  # type: ignore[arg-type]
            )
        ).all()
    }

    faltas = 0
    for e in matriculados:
        if e.student_id in con_marca:
            continue
        db.add(
            AttendanceRecord(
                session_id=session.id,  # type: ignore[arg-type]
                student_id=e.student_id,
                status=AttendanceStatus.FALTA,  # RF-26: falta generada por el cierre
                marked_at=None,
                method="facial",
            )
        )
        faltas += 1

    session.status = SessionStatus.CERRADA
    # TIMESTAMP (sin tz) en la BD: el aware de asyncpg rechazaría un datetime aware
    session.closed_at = _naive_peru(ahora_peru())
    db.add(session)

    await audit(
        db, actor, action="sesion_cerrada", entity="attendance_session",
        entity_id=session.id,
        new_value={"block_id": session.block_id, "fecha": str(session.session_date),
                   "faltas_generadas": faltas, "cerrada_por": "sistema" if actor is None else "admin"},
        ip_address=ip,
    )
    await db.commit()

    alertas = await _alertas_dpi(db, session)
    return {"session_id": session.id, "status": "cerrada", "faltas": faltas, "alertas": alertas}


async def _alertas_dpi(db: SQLModelAsyncSession, session: AttendanceSession) -> int:
    """RF-24: correo a los alumnos que cruzan dpi_alert_percent (SQL crudo
    sobre la vista v_student_dpi de este curso)."""
    bloque = await db.get(ScheduleBlock, session.block_id)
    grupo = await db.get(CourseGroup, bloque.group_id) if bloque else None
    if grupo is None:
        return 0
    settings = await db.get(AppSettings, 1)
    umbral = float(settings.dpi_alert_percent) if settings else 30.0

    from sqlalchemy import text as sql_text

    filas = (
        await db.exec(
            sql_text(
                "SELECT student_id, course_code, sessions_held, absences, absence_percent "
                "FROM v_student_dpi WHERE course_id = :curso AND absence_percent >= :umbral"
            ).bindparams(curso=grupo.course_id, umbral=umbral)
        )
    ).all()

    from app.services.notifications import send_dpi_alert

    enviadas = 0
    for fila in filas:
        alumno = await db.get(AppUser, int(fila.student_id))
        if alumno is None or not alumno.email:
            continue
        ok = await send_dpi_alert(
            alumno.email,
            alumno.full_name,
            str(fila.course_code),
            int(fila.sessions_held),
            int(fila.absences),
            float(fila.absence_percent),
            float(umbral),
        )
        if ok:
            enviadas += 1
    if enviadas:
        await audit(
            db, None, action="alerta_dpi_enviada", entity="course",
            entity_id=grupo.course_id,
            new_value={"sesion": session.id, "correos": enviadas},
        )
        await db.commit()
    return enviadas


async def cerrar_sesiones_pendientes(db: SQLModelAsyncSession) -> list[dict]:
    """Barrido del scheduler (RF-26): cierra toda sesión abierta cuyo bloque
    ya terminó (+ tolerancia). Devuelve resúmenes por sesión cerrada."""
    settings = await db.get(AppSettings, 1)
    tolerancia = timedelta(minutes=settings.late_tolerance_minutes if settings else 10)
    now = _naive_peru(ahora_peru())
    hoy = now.date()

    abiertas = (
        await db.exec(
            select(AttendanceSession, ScheduleBlock)
            .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
            .where(AttendanceSession.status == SessionStatus.ABIERTA)  # type: ignore[arg-type]
        )
    ).all()

    resumenes = []
    for sesion, bloque in abiertas:
        fin = _combo(bloque.end_time, sesion.session_date) + tolerancia
        # cierra si su ventana terminó (hoy u otra fecha pasada)
        if sesion.session_date < hoy or (sesion.session_date == hoy and now >= fin):
            resumenes.append(await cerrar_sesion(db, sesion))
    return resumenes
