import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.audit import audit
from app.services.settings import get_settings_row, semestre_en_curso
from app.tables import (
    AppSettings,
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


PERU_TZ = timezone(timedelta(hours=-5))


def ahora_peru() -> datetime:
    return datetime.now(PERU_TZ)

def _to_peru(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PERU_TZ)
    return dt.astimezone(PERU_TZ)

def _naive_peru(dt: datetime) -> datetime:
    return _to_peru(dt).replace(tzinfo=None)

def _combo(hora: time, d: date) -> datetime:
    return datetime.combine(d, hora)

def clasificar(now: datetime, bloque: ScheduleBlock, fecha: date, cfg: AppSettings) -> str | None:
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
    return (await db.exec(select(Holiday).where(Holiday.holiday_date == d))).first() is not None

async def bloques_candidatos(
    db: SQLModelAsyncSession, room_id: int, now: datetime, cfg: AppSettings
) -> list[tuple[ScheduleBlock, CourseGroup]]:
    weekday = now.date().isoweekday()
    ahora_dt = _combo(now.time(), now.date())
    pares = (
        await db.exec(
            select(ScheduleBlock, CourseGroup)
            .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
            .where(
                ScheduleBlock.room_id == room_id,
                CourseGroup.is_active,
                CourseGroup.semester_label == cfg.semester_label,
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
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    hoy = now.date()

    if await es_feriado(db, hoy):
        return None, None
    if not await semestre_en_curso(db, hoy):
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
        matriculas = {
            r[0] if isinstance(r, tuple) else r
            for r in (
                await db.exec(
                    select(Enrollment.group_id).where(
                        Enrollment.student_id == student_id,
                        Enrollment.withdrawn_at.is_(None),
                    )
                )
            ).all()
        }
        propios = [(b, g) for (b, g) in pares if g.id in matriculas]
        if propios:
            pares = propios
    bloque, _grupo = max(pares, key=lambda par: par[0].start_time)

    sesion = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == bloque.id,
                AttendanceSession.session_date == hoy,
            )
        )
    ).first()
    if sesion is None:
        sesion = AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA)
        db.add(sesion)
        await db.flush()
    elif sesion.status is not SessionStatus.ABIERTA:
        return None, None
    return sesion, bloque

async def matriculados_activos(
    db: SQLModelAsyncSession, group_id: int, fecha: date
) -> list[Enrollment]:
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
    fila = (
        await db.exec(
            select(Justification.id)
            .where(
                Justification.student_id == student_id,
                Justification.start_date <= fecha,
                Justification.end_date >= fecha,
                Justification.course_id.is_(None)
                | (Justification.course_id == course_id),
            )
            .limit(1)
        )
    ).first()
    return fila[0] if isinstance(fila, tuple) else fila

async def registrar_marca(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    student_id: int,
    *,
    similarity: float | None = None,
    method: str = "facial",
    status_override: str | None = None,
    now: datetime | None = None,
    audit_actor=None,
    audit_ip: str | None = None,
) -> AttendanceRecord:
    now = _naive_peru(now) if now else _naive_peru(ahora_peru())
    bloque = await db.get(ScheduleBlock, session.block_id)
    if bloque is None:
        raise errors.NotFoundError("El bloque de la sesión no existe")

    ya = (
        await db.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session.id,
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
        status = clasificar(now, bloque, session.session_date, cfg) or "asistio"
    status_enum = AttendanceStatus(status)

    record = AttendanceRecord(
        session_id=session.id,
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

async def abrir_sesiones_del_dia(db: SQLModelAsyncSession, now: datetime | None = None) -> int:
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
                CourseGroup.is_active,
                ScheduleBlock.room_id.is_not(None),
                CourseGroup.semester_label == cfg.semester_label,
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
                    AttendanceSession.block_id == bloque.id,
                    AttendanceSession.session_date == hoy,
                )
            )
        ).first()
        if ya is not None:
            continue
        db.add(AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA))
        abiertas += 1
    if abiertas:
        await db.commit()
    return abiertas

async def cerrar_sesion(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    *,
    actor=None,
    ip: str | None = None,
) -> dict:
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
                select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
            )
        ).all()
    }

    if not con_marca:
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

        from app.services.notification_center import notificar_sesion_por_revisar

        await notificar_sesion_por_revisar(db, session=session, actor=actor)
        await db.commit()
        return {"session_id": session.id, "status": "needs_review", "faltas": 0, "alertas": 0}

    faltas = 0
    for e in matriculados:
        if e.student_id in con_marca:
            continue
        justif_id = await justificacion_vigente(db, e.student_id, grupo.course_id, session.session_date)
        db.add(
            AttendanceRecord(
                session_id=session.id,
                student_id=e.student_id,
                status=AttendanceStatus.FALTA,
                marked_at=None,
                method="facial",
                is_justified=justif_id is not None,
                justification_id=justif_id,
            )
        )
        faltas += 1

    session.status = SessionStatus.CERRADA

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
    if faltas:
        from app.services.dpi import procesar_alertas_cierre

        alertas = await procesar_alertas_cierre(db, session)
    return {"session_id": session.id, "status": "cerrada", "faltas": faltas, "alertas": alertas}

async def cerrar_sesiones_pendientes(db: SQLModelAsyncSession) -> list[dict]:
    now = _naive_peru(ahora_peru())
    hoy = now.date()

    abiertas = (
        await db.exec(
            select(AttendanceSession, ScheduleBlock)
            .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
            .where(AttendanceSession.status == SessionStatus.ABIERTA)
        )
    ).all()

    resumenes = []
    for sesion, bloque in abiertas:
        fin = _combo(bloque.end_time, sesion.session_date)
        if sesion.session_date < hoy or (sesion.session_date == hoy and now >= fin):
            resumenes.append(await cerrar_sesion(db, sesion))
    return resumenes

def _es_docente(actor) -> bool:
    return getattr(actor, "role", None) is not None and actor.role.value == "docente"

def _puede_cancelar(session: AttendanceSession, actor) -> None:
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
    _puede_cancelar(session, actor)
    old = {"status": session.status.value if hasattr(session.status, "value") else str(session.status)}
    session.status = SessionStatus.CANCELADA
    session.cancel_reason = reason.strip()[:200]
    session.cancelled_by = actor.id
    session.cancelled_at = _naive_peru(ahora_peru())
    db.add(session)
    await audit(
        db, actor, action="sesion_cancelada", entity="attendance_session",
        entity_id=session.id, old_value=old,
        new_value={"reason": session.cancel_reason, "fecha": str(session.session_date)},
        ip_address=ip,
    )

    from app.services.notification_center import notificar_sesion_cancelada

    await notificar_sesion_cancelada(
        db, session=session, actor=actor, reason=session.cancel_reason or ""
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
    grupo = await db.get(CourseGroup, bloque.group_id)
    if grupo is None:
        raise errors.NotFoundError("El grupo del bloque no existe")
    if fecha.isoweekday() != bloque.weekday:
        raise errors.DomainError(
            f"El bloque del día {bloque.weekday} no tiene clase el {fecha} (día {fecha.isoweekday()})"
        )
    sesion = (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == bloque.id,
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

        from app.services.notification_center import notificar_sesion_cancelada

        await notificar_sesion_cancelada(
            db, session=sesion, actor=actor, reason=sesion.cancel_reason or ""
        )
        await db.commit()
        return {"session_id": sesion.id, "status": "cancelada", "anticipada": True}
    return await cancelar_sesion(db, sesion, actor, reason, ip)

async def resolver_revision(
    db: SQLModelAsyncSession,
    session: AttendanceSession,
    actor,
    action: str,
    reason: str | None = None,
    ip: str | None = None,
) -> dict:
    if not session.needs_review or session.status is not SessionStatus.CERRADA:
        raise errors.DomainError("La sesión no está pendiente de revisión")

    if action == "cancelar":
        if not reason:
            raise errors.DomainError("Cancelar una sesión por revisar requiere motivo")
        resultado = await cancelar_sesion(db, session, actor, reason, ip)
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
                select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
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
                session_id=session.id,
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
