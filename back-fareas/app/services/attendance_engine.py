"""Motor de asistencia (Bloques 6 + 11) — RF-21…RF-26 y reglas R1-R5, R10.

Lógica pura sobre la BD, testeable sin HTTP. Los routers (marca manual),
el scheduler (apertura/cierre automáticos) y el bucle de cámaras llaman aquí.

Reglas de ventana (R2): para un bloque inicio–fin, tolerancia T y apertura
anticipada E: antes de inicio−E no hay sesión; [inicio−E, inicio+T] → asistio;
(inicio+T, fin] → tardanza; después de fin no se marca (falta al cierre).

- Marca ÚNICA por (session_id, student_id) — UNIQUE de la BD.
- R3: la sesión la ABRE el scheduler (respaldo: si no existe y la ventana
  está abierta, resolver_sesion la crea al vuelo).
- R4: al cerrar con cero marcas queda needs_review SIN faltas ni alertas.
- R5: estado 'cancelada' con motivo y actor; no genera faltas ni cuenta.
- R6: las faltas nacen justificadas si hay justificación vigente del alumno.
- R10: bloques contiguos en la misma aula → el desempate lo hace la
  matrícula del alumno reconocido; si persiste, el bloque que empezó tarde.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.services.settings import get_settings_row, semestre_en_curso
from app.tables import (
    AppSettings,
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    CourseGroup,
    Enrollment,
    Holiday,
    Justification,
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
# Ventanas (R2) y resolución de sesión (R3, R10)
# ---------------------------------------------------------------------------
def clasificar(now: datetime, bloque: ScheduleBlock, fecha: date, cfg: AppSettings) -> str | None:
    """R2: clasifica un instante dentro de la ventana del bloque.

    None = fuera de la ventana (no hay sesión / no se marca).
    """
    inicio = _combo(bloque.start_time, fecha)
    fin = _combo(bloque.end_time, fecha)
    if now < inicio - timedelta(minutes=cfg.early_open_minutes):
        return None
    if now <= inicio + timedelta(minutes=cfg.late_tolerance_minutes):
        return "asistio"
    if now <= fin:
        return "tardanza"
    return None


async def es_feriado(db: SQLModelAsyncSession, d: date) -> bool:
    """RF-09: no se abren sesiones en feriados/paros."""
    return (await db.exec(select(Holiday).where(Holiday.holiday_date == d))).first() is not None


async def bloques_candidatos(
    db: SQLModelAsyncSession, room_id: int, now: datetime, cfg: AppSettings
) -> list[tuple[ScheduleBlock, CourseGroup]]:
    """Bloques del aula cuya ventana R2 contiene `now`: grupos activos del
    semestre vigente (R1); la ventana de sesión es [inicio−E, fin]."""
    weekday = now.date().isoweekday()
    ahora_dt = _combo(now.time(), now.date())
    pares = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.room_id == room_id,
                CourseGroup.is_active,  # type: ignore[arg-type]
                CourseGroup.semester_label == cfg.semester_label,  # R1
                ScheduleBlock.weekday == weekday,
            )
        )
    ).all()
    apertura = timedelta(minutes=cfg.early_open_minutes)
    return [
        (b, g)
        for (b, g) in pares
        if _combo(b.start_time, now.date()) - apertura <= ahora_dt <= _combo(b.end_time, now.date())
    ]


async def resolver_sesion(
    db: SQLModelAsyncSession,
    room_id: int,
    now: datetime | None = None,
    student_id: int | None = None,
) -> tuple[AttendanceSession | None, ScheduleBlock | None]:
    """Aula → sesión activa a esa hora (R10: desempate por matrícula).

    Devuelve (sesión, bloque) o (None, None) si no hay clase: feriado, fuera
    del semestre (R1), fuera de la ventana R2, aula sin grupos, sesión ya
    cerrada o cancelada. La sesión la crea el scheduler (R3); aquí se crea
    SOLO como respaldo si la ventana está abierta y nadie la abrió.
    """
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    hoy = now.date()

    if await es_feriado(db, hoy):
        return None, None
    if not await semestre_en_curso(db, hoy):  # R1: nada fuera del semestre
        return None, None
    if await db.get(Room, room_id) is None:
        return None, None

    cfg = await get_settings_row(db)
    if not (cfg.attendance_hour_start <= now.time() < cfg.attendance_hour_end):
        return None, None

    pares = await bloques_candidatos(db, room_id, now, cfg)
    if not pares:
        return None, None

    if student_id is not None:
        # R10: si hay varios bloques simultáneos, decide la MATRÍCULA del
        # alumno (activa a la fecha: enrolado antes de hoy, no retirado aún).
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
        propios = [(b, g) for (b, g) in pares if g.id in matriculas]
        if propios:
            pares = propios
    # Empate persistente (sin alumno o sin matrícula): el que empezó más tarde.
    bloque, _grupo = max(pares, key=lambda par: par[0].start_time)

    sesion = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == bloque.id,  # type: ignore[arg-type]
                AttendanceSession.session_date == hoy,
            )
        )
    ).first()
    if sesion is None:
        # Respaldo (R3): el scheduler debió abrirla; si la ventana corre y
        # nadie la abrió, se crea aquí para no perder la primera marca.
        sesion = AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA)
        db.add(sesion)
        await db.flush()
    elif sesion.status is not SessionStatus.ABIERTA:
        return None, None  # cerrada: no se reabre; cancelada: no se marca
    return sesion, bloque


# ---------------------------------------------------------------------------
# Matrícula activa a la fecha (R8) y justificación vigente (R6)
# ---------------------------------------------------------------------------
async def matriculados_activos(
    db: SQLModelAsyncSession, group_id: int, fecha: date
) -> list[Enrollment]:
    """Matriculados VIGENTES para una fecha: enrolados antes (o ese día) y
    aún no retirados a esa fecha (R8)."""
    filas = (await db.exec(select(Enrollment).where(Enrollment.group_id == group_id))).all()
    return [
        e
        for e in filas
        if e.enrolled_at is not None
        and e.enrolled_at.date() <= fecha
        and (e.withdrawn_at is None or e.withdrawn_at.date() >= fecha)
    ]


async def justificacion_vigente(
    db: SQLModelAsyncSession, student_id: int, course_id: int, fecha: date
) -> int | None:
    """R6: id de la justificación que cubre (alumno, curso, fecha); None si no."""
    fila = (
        await db.exec(
            select(Justification.id)
            .where(
                Justification.student_id == student_id,  # type: ignore[arg-type]
                Justification.start_date <= fecha,  # type: ignore[arg-type]
                Justification.end_date >= fecha,  # type: ignore[arg-type]
                Justification.course_id.is_(None)  # type: ignore[union-attr]
                | (Justification.course_id == course_id),  # type: ignore[arg-type]
            )
            .limit(1)
        )
    ).first()
    return fila[0] if isinstance(fila, tuple) else fila


# ---------------------------------------------------------------------------
# Marca de asistencia (RF-21 / R2)
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
    """Inserta la marca ÚNICA del alumno clasificando R2.

    ConflictError si ya existe (la BD impone UNIQUE). ``method='manual'`` la
    usa el docente desde la app (RF-21); permitido también en sesiones
    cerradas con needs_review (R4) — el router valida el estado.
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

    cfg = await get_settings_row(db)
    if status_override is not None:
        status = status_override
    else:
        # R2: asistio hasta inicio+tolerancia; tardanza hasta el FIN del
        # bloque (decisión confirmada: 55 min tarde en 1 h = tardanza).
        status = clasificar(now, bloque, session.session_date, cfg) or "asistio"
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
# Apertura programada (R3)
# ---------------------------------------------------------------------------
async def abrir_sesiones_del_dia(db: SQLModelAsyncSession, now: datetime | None = None) -> int:
    """R3: abre la sesión de cada bloque cuya ventana de apertura ya empezó.

    Idempotente (INSERT … ON CONFLICT DO NOTHING): el scheduler lo llama cada
    60 s. No abre en feriados ni fuera del semestre (R1) y no reabre las
    canceladas por adelantado (cancel-day, R5). Devuelve cuántas NUEVAS abrió.
    """
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    hoy = now.date()
    if await es_feriado(db, hoy):
        return 0
    if not await semestre_en_curso(db, hoy):
        return 0
    cfg = await get_settings_row(db)
    if not (cfg.attendance_hour_start <= now.time() < cfg.attendance_hour_end):
        return 0

    weekday = hoy.isoweekday()
    ahora_dt = _combo(now.time(), hoy)
    apertura = timedelta(minutes=cfg.early_open_minutes)
    pares = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                CourseGroup.is_active,  # type: ignore[arg-type]
                CourseGroup.semester_label == cfg.semester_label,  # R1
                ScheduleBlock.weekday == weekday,
            )
        )
    ).all()
    pares = [
        (b, g)
        for (b, g) in pares
        if _combo(b.start_time, hoy) - apertura <= ahora_dt <= _combo(b.end_time, hoy)
    ]

    abiertas = 0
    for bloque, _grupo in pares:
        ya = (
            await db.exec(
                select(AttendanceSession).where(
                    AttendanceSession.block_id == bloque.id,  # type: ignore[arg-type]
                    AttendanceSession.session_date == hoy,
                )
            )
        ).first()
        if ya is not None:
            continue  # ya existe (abierta, cerrada, needs_review o cancelada)
        db.add(AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA))
        abiertas += 1
    if abiertas:
        await db.commit()
    return abiertas


# ---------------------------------------------------------------------------
# Cierre de sesión (RF-26 + R4) → faltas automáticas + alertas DPI (R7)
# ---------------------------------------------------------------------------
async def cerrar_sesion(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    *,
    actor=None,  # None = sistema (scheduler); AppUser = cierre manual admin
    ip: str | None = None,
) -> dict:
    """Cierra la sesión: R4 — con cero marcas queda needs_review SIN faltas;
    con marcas genera faltas a matriculados activos sin registro (nacen
    justificadas si hay justificación vigente, R6) y dispara alertas DPI
    (R7, con envío único por nivel). Canceladas: no se tocan (R5)."""
    if session.status is SessionStatus.CERRADA:
        return {"session_id": session.id, "status": "ya_cerrada", "faltas": 0, "alertas": 0}
    if session.status is SessionStatus.CANCELADA:
        return {"session_id": session.id, "status": "cancelada", "faltas": 0, "alertas": 0}

    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")
    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")

    matriculados = await matriculados_activos(db, grupo.id, session.session_date)
    con_marca = {
        r.student_id
        for r in (
            await db.exec(
                select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)  # type: ignore[arg-type]
            )
        ).all()
    }

    if not con_marca:
        # R4: nadie marcó → la sesión requiere revisión (¿cámara caída?),
        # SIN faltas y SIN alertas hasta que el admin/docente la resuelva.
        session.status = SessionStatus.CERRADA
        session.needs_review = True
        session.closed_at = _naive_peru(ahora_peru())
        db.add(session)
        await audit(
            db, actor, action="sesion_cerrada", entity="attendance_session",
            entity_id=session.id,
            new_value={"block_id": session.block_id, "fecha": str(session.session_date),
                       "needs_review": True, "cerrada_por": "sistema" if actor is None else "admin"},
            ip_address=ip,
        )
        await db.commit()
        return {"session_id": session.id, "status": "needs_review", "faltas": 0, "alertas": 0}

    faltas = 0
    for e in matriculados:
        if e.student_id in con_marca:
            continue
        justif_id = await justificacion_vigente(db, e.student_id, grupo.course_id, session.session_date)
        db.add(
            AttendanceRecord(
                session_id=session.id,  # type: ignore[arg-type]
                student_id=e.student_id,
                status=AttendanceStatus.FALTA,  # RF-26: falta generada por el cierre
                marked_at=None,
                method="facial",
                is_justified=justif_id is not None,  # R6
                justification_id=justif_id,
            )
        )
        faltas += 1

    session.status = SessionStatus.CERRADA
    # TIMESTAMP (sin tz) en la BD: asyncpg rechazaría un datetime aware
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

    alertas = 0
    if faltas:  # R7: solo hay niveles DPI si hubo faltas nuevas
        from app.services.dpi import procesar_alertas_cierre

        alertas = await procesar_alertas_cierre(db, session)
    return {"session_id": session.id, "status": "cerrada", "faltas": faltas, "alertas": alertas}


async def cerrar_sesiones_pendientes(db: SQLModelAsyncSession) -> list[dict]:
    """Barrido del scheduler (RF-26): cierra toda sesión abierta cuyo bloque
    YA TERMINÓ (fin del bloque, sin tolerancia — R4). Devuelve resúmenes."""
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
        fin = _combo(bloque.end_time, sesion.session_date)
        # cierra si su ventana terminó (hoy u otra fecha pasada)
        if sesion.session_date < hoy or (sesion.session_date == hoy and now >= fin):
            resumenes.append(await cerrar_sesion(db, sesion))
    return resumenes


# ---------------------------------------------------------------------------
# Cancelación (R5)
# ---------------------------------------------------------------------------
def _es_docente(actor) -> bool:
    return getattr(actor, "role", None) is not None and actor.role.value == "docente"


def _puede_cancelar(session: AttendanceSession, actor) -> None:
    """R5: docente cancela sesiones ABIERTAS o needs_review (el router valida
    que sea su grupo); admin también puede cancelar una CERRADA (feriado
    olvidado). Cancelada dos veces → error de dominio."""
    if session.status is SessionStatus.CANCELADA:
        raise errors.DomainError("La sesión ya está cancelada")
    if _es_docente(actor) and session.status is not SessionStatus.ABIERTA and not session.needs_review:
        raise errors.DomainError(
            "Como docente solo puedes cancelar sesiones abiertas o por revisar; pide al admin cancelar una cerrada"
        )


async def cancelar_sesion(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    actor,
    reason: str,
    ip: str | None = None,
) -> dict:
    """R5: cancela UNA sesión (con motivo). No genera faltas; si ya tenía
    registros los conserva en BD pero TODA consulta debe excluir canceladas
    (v_today_attendance, stats y DPI ya lo hacen)."""
    _puede_cancelar(session, actor)
    old = {"status": session.status.value if hasattr(session.status, "value") else str(session.status)}
    session.status = SessionStatus.CANCELADA
    session.cancel_reason = reason.strip()[:200]
    session.cancelled_by = actor.id  # type: ignore[arg-type]
    session.cancelled_at = _naive_peru(ahora_peru())
    db.add(session)
    await audit(
        db, actor, action="sesion_cancelada", entity="attendance_session",
        entity_id=session.id, old_value=old,
        new_value={"reason": session.cancel_reason, "fecha": str(session.session_date)},
        ip_address=ip,
    )
    await db.commit()
    return {"session_id": session.id, "status": "cancelada", "reason": session.cancel_reason}


async def cancelar_dia(
    db: SQLModelAsyncSession,
    bloque: ScheduleBlock,
    fecha: date,
    actor,
    reason: str,
    ip: str | None = None,
) -> dict:
    """R5: cancela (o pre-cancela) el día de un bloque. Si la sesión existe se
    cancela; si no (fecha futura), se CREA ya cancelada para que el scheduler
    (R3) no la abra. El docente solo puede cancelar sesiones abiertas propias."""
    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    # La fecha debe ser un día de clase del bloque (mismo weekday).
    if fecha.isoweekday() != bloque.weekday:
        raise errors.DomainError(
            f"El bloque del día {bloque.weekday} no tiene clase el {fecha} (día {fecha.isoweekday()})"
        )
    sesion = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == bloque.id,  # type: ignore[arg-type]
                AttendanceSession.session_date == fecha,
            )
        )
    ).first()
    if sesion is None:
        if _es_docente(actor):
            raise errors.DomainError("Como docente solo puedes cancelar sesiones ya abiertas")
        sesion = AttendanceSession(
            block_id=bloque.id, session_date=fecha, status=SessionStatus.CANCELADA,
            cancel_reason=reason.strip()[:200], cancelled_by=actor.id,
            cancelled_at=_naive_peru(ahora_peru()),
        )
        db.add(sesion)
        await db.flush()
        await audit(
            db, actor, action="sesion_cancelada", entity="attendance_session",
            entity_id=sesion.id,
            new_value={"reason": sesion.cancel_reason, "fecha": str(fecha), "anticipada": True},
            ip_address=ip,
        )
        await db.commit()
        return {"session_id": sesion.id, "status": "cancelada", "anticipada": True}
    return await cancelar_sesion(db, sesion, actor, reason, ip)


# ---------------------------------------------------------------------------
# Sesiones por revisar (R4)
# ---------------------------------------------------------------------------
async def resolver_revision(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    actor,
    action: str,  # 'confirmar_faltas' | 'cancelar'
    reason: str | None = None,
    ip: str | None = None,
) -> dict:
    """R4: resuelve una sesión cerrada con needs_review.

    - confirmar_faltas: genera las faltas de matriculados sin registro
      (justificadas si corresponde, R6) y dispara alertas DPI (R7).
    - cancelar: la cancela con motivo (R5) — no genera nada.
    """
    if not session.needs_review or session.status is not SessionStatus.CERRADA:
        raise errors.DomainError("La sesión no está pendiente de revisión")

    if action == "cancelar":
        if not reason:
            raise errors.DomainError("Cancelar una sesión por revisar requiere motivo")
        resultado = await cancelar_sesion(db, session, actor, reason, ip)
        # La cancelación conserva el historial de "estaba por revisar".
        session.needs_review = False
        db.add(session)
        await db.commit()
        resultado["needs_review"] = False
        return resultado
    if action != "confirmar_faltas":
        raise errors.DomainError("action debe ser 'confirmar_faltas' o 'cancelar'")

    bloque = await db.get(ScheduleBlock, session.block_id)
    grupo = await db.get(CourseGroup, bloque.group_id) if bloque else None
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")

    matriculados = await matriculados_activos(db, grupo.id, session.session_date)
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
        justif_id = await justificacion_vigente(db, e.student_id, grupo.course_id, session.session_date)
        db.add(
            AttendanceRecord(
                session_id=session.id,  # type: ignore[arg-type]
                student_id=e.student_id,
                status=AttendanceStatus.FALTA,
                marked_at=None,
                method="facial",
                is_justified=justif_id is not None,
                justification_id=justif_id,
            )
        )
        faltas += 1

    session.needs_review = False
    db.add(session)
    await audit(
        db, actor, action="sesion_revisada", entity="attendance_session",
        entity_id=session.id,
        new_value={"accion": "confirmar_faltas", "faltas_generadas": faltas,
                   "revisada_por": actor.full_name},
        ip_address=ip,
    )
    await db.commit()

    alertas = 0
    if faltas:
        from app.services.dpi import procesar_alertas_cierre

        alertas = await procesar_alertas_cierre(db, session)
    return {"session_id": session.id, "status": "cerrada", "faltas": faltas, "alertas": alertas}
