import asyncio
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlmodel import select

from app.core.config import get_settings
from app.database import SessionLocal
from app.services.emailer import send_notification_email
from app.tables import (
    AppUser,
    Course,
    CourseGroup,
    Enrollment,
    Notification,
    Room,
    ScheduleBlock,
    UserRole,
)

logger = logging.getLogger("fareas.notifications")


async def crear_notificaciones(
    db,
    *,
    user_ids: Iterable[int] | None = None,
    roles: Iterable[UserRole] | None = None,
    kind: str,
    title: str,
    message: str,
    link: str | None = None,
    severity: str = "info",
    email: bool = False,
    dedupe_key: str | None = None,
    exclude_user_id: int | None = None,
) -> int:
    ids: set[int] = set()
    if roles:
        filas = (
            await db.exec(
                select(AppUser.id).where(
                    AppUser.role.in_(list(roles)),
                    AppUser.is_active.is_(True),
                )
            )
        ).all()
        ids |= {int(f[0] if isinstance(f, tuple) else f) for f in filas}
    if user_ids:
        ids |= {int(uid) for uid in user_ids if uid is not None}
    if exclude_user_id is not None:
        ids.discard(int(exclude_user_id))
    if not ids:
        return 0

    activos = {
        int(f[0] if isinstance(f, tuple) else f)
        for f in (
            await db.exec(
                select(AppUser.id).where(
                    AppUser.id.in_(ids),
                    AppUser.is_active.is_(True),
                )
            )
        ).all()
    }
    ids &= activos
    if not ids:
        return 0

    if dedupe_key:
        existentes = {
            int(f[0] if isinstance(f, tuple) else f)
            for f in (
                await db.exec(
                    select(Notification.user_id).where(
                        Notification.user_id.in_(ids),
                        Notification.dedupe_key == dedupe_key,
                    )
                )
            ).all()
        }
        ids -= existentes
    if not ids:
        return 0

    for uid in ids:
        db.add(
            Notification(
                user_id=uid,
                kind=kind,
                title=title[:160],
                message=message[:500],
                link=link[:200] if link else None,
                severity=severity,
                dedupe_key=dedupe_key,
                email_status="pending" if email else "skipped",
            )
        )
    await db.flush()
    return len(ids)


async def despachar_correos_pendientes(limit: int = 10) -> int:
    if not get_settings().MAIL_ENABLED:
        return 0

    enviados = 0
    async with SessionLocal() as db:
        filas = (
            await db.exec(
                select(Notification, AppUser)
                .join(AppUser, AppUser.id == Notification.user_id)
                .where(
                    Notification.email_status == "pending",
                    Notification.email_attempts < 3,
                )
                .order_by(Notification.created_at)
                .limit(limit)
            )
        ).all()
        if not filas:
            return 0

        logger.info("[notificaciones] Despachando %s correo(s) pendiente(s)", len(filas))

        for notificacion, usuario in filas:
            notificacion.email_attempts += 1
            if not usuario.email:
                notificacion.email_status = "skipped"
                db.add(notificacion)
                await db.commit()
                continue
            try:
                ok = await asyncio.wait_for(
                    send_notification_email(
                        usuario.email,
                        usuario.full_name,
                        notificacion.title,
                        notificacion.message,
                        notificacion.link,
                    ),
                    timeout=20,
                )
            except Exception as exc:
                ok = False
                notificacion.email_error = str(exc)[:300]

            if ok:
                notificacion.email_status = "sent"
                notificacion.email_sent_at = datetime.now(UTC)
                notificacion.email_error = None
                enviados += 1
            else:
                logger.warning(
                    "[notificaciones] Falló el correo #%s (intento %s)",
                    notificacion.id,
                    notificacion.email_attempts,
                )
                if notificacion.email_attempts >= 3:
                    notificacion.email_status = "failed"
                    notificacion.email_error = (
                        notificacion.email_error or "El servidor de correo rechazó el envío"
                    )[:300]

            db.add(notificacion)
            await db.commit()

    return enviados


async def _contexto_sesion(db, session) -> tuple[ScheduleBlock | None, CourseGroup | None, Course | None]:
    bloque = await db.get(ScheduleBlock, session.block_id)
    grupo = await db.get(CourseGroup, bloque.group_id) if bloque else None
    curso = await db.get(Course, grupo.course_id) if grupo else None
    return bloque, grupo, curso


async def notificar_sesion_por_revisar(db, *, session, actor=None) -> int:
    bloque, grupo, curso = await _contexto_sesion(db, session)
    if grupo is None:
        return 0
    codigo = curso.code if curso else "Curso"
    mensaje = (
        f"La sesión de {codigo} del {session.session_date} se cerró sin marcas de asistencia. "
        "Confirma las faltas o cancela la clase desde Asistencias."
    )
    return await crear_notificaciones(
        db,
        user_ids=[grupo.teacher_id] if grupo.teacher_id else [],
        roles=[UserRole.ADMIN],
        exclude_user_id=actor.id if actor is not None else None,
        kind="sesion_revision",
        title="Sesión por revisar",
        message=mensaje,
        link="/admin/attendance",
        severity="warning",
        email=True,
        dedupe_key=f"review:{session.id}",
    )


async def notificar_sesion_cancelada(db, *, session, actor, reason: str) -> int:
    _bloque, grupo, curso = await _contexto_sesion(db, session)
    if grupo is None:
        return 0
    codigo = curso.code if curso else "Curso"
    mensaje = (
        f"La clase de {codigo} del {session.session_date} fue cancelada. "
        f"Motivo: {reason}"
    )
    creadas = 0

    estudiantes = [
        int(f[0] if isinstance(f, tuple) else f)
        for f in (
            await db.exec(
                select(Enrollment.student_id).where(
                    Enrollment.group_id == grupo.id,
                    Enrollment.withdrawn_at.is_(None),
                )
            )
        ).all()
    ]
    creadas += await crear_notificaciones(
        db,
        user_ids=estudiantes,
        kind="clase_cancelada",
        title="Clase cancelada",
        message=mensaje,
        link="/admin/my-attendance",
        severity="warning",
        email=True,
        dedupe_key=f"cancel:{session.id}",
    )

    if grupo.teacher_id and grupo.teacher_id != actor.id:
        creadas += await crear_notificaciones(
            db,
            user_ids=[grupo.teacher_id],
            kind="clase_cancelada",
            title="Clase cancelada",
            message=mensaje,
            link="/admin/attendance",
            severity="warning",
            email=True,
            dedupe_key=f"cancel:{session.id}",
        )

    if actor.role is UserRole.DOCENTE:
        creadas += await crear_notificaciones(
            db,
            roles=[UserRole.ADMIN],
            kind="clase_cancelada",
            title="Clase cancelada por docente",
            message=f"{actor.full_name} canceló {codigo} del {session.session_date}. Motivo: {reason}",
            link="/admin/attendance",
            severity="info",
            email=False,
            dedupe_key=f"cancel-admin:{session.id}",
        )
    return creadas


async def notificar_justificacion_creada(
    db, *, actor, just, student: AppUser, course: Course | None, afectadas: int
) -> int:
    codigo = course.code if course else "todos los cursos"
    mensaje = (
        f"Se registró una justificación para {codigo} del {just.start_date} al {just.end_date}. "
        f"{afectadas} falta(s) quedaron justificadas."
    )
    creadas = await crear_notificaciones(
        db,
        user_ids=[just.student_id],
        kind="justificacion",
        title="Justificación registrada",
        message=mensaje,
        link="/admin/my-justifications",
        severity="success",
        email=False,
        dedupe_key=f"just:{just.id}:student",
    )

    if just.course_id:
        docentes = {
            int(f[0] if isinstance(f, tuple) else f)
            for f in (
                await db.exec(
                    select(CourseGroup.teacher_id).where(
                        CourseGroup.course_id == just.course_id,
                        CourseGroup.is_active.is_(True),
                        CourseGroup.teacher_id.is_not(None),
                    )
                )
            ).all()
        }
        docentes.discard(actor.id)
        creadas += await crear_notificaciones(
            db,
            user_ids=docentes,
            kind="justificacion",
            title=f"Nueva justificación en {codigo}",
            message=(
                f"{actor.full_name} registró una justificación para {student.full_name} "
                f"del {just.start_date} al {just.end_date}."
            ),
            link="/admin/calendar/justifications",
            severity="info",
            email=False,
            dedupe_key=f"just:{just.id}:teacher",
        )

    if actor.role is UserRole.DOCENTE:
        creadas += await crear_notificaciones(
            db,
            roles=[UserRole.ADMIN],
            kind="justificacion",
            title="Justificación registrada por docente",
            message=(
                f"{actor.full_name} justificó {afectadas} falta(s) de {student.full_name} "
                f"en {codigo}."
            ),
            link="/admin/calendar/justifications",
            severity="info",
            email=False,
            dedupe_key=f"just:{just.id}:admin",
        )
    return creadas


async def notificar_justificacion_eliminada(db, *, actor, just, revertidas: int) -> int:
    student = await db.get(AppUser, just.student_id)
    course = await db.get(Course, just.course_id) if just.course_id else None
    codigo = course.code if course else "todos los cursos"
    creadas = await crear_notificaciones(
        db,
        user_ids=[just.student_id],
        kind="justificacion",
        title="Justificación eliminada",
        message=(
            f"Se eliminó la justificación de {codigo} del {just.start_date} al {just.end_date}. "
            f"{revertidas} falta(s) vuelven a contar para el límite de inasistencias."
        ),
        link="/admin/my-justifications",
        severity="warning",
        email=False,
        dedupe_key=f"just-del:{just.id}:student",
    )

    if just.course_id:
        docentes = {
            int(f[0] if isinstance(f, tuple) else f)
            for f in (
                await db.exec(
                    select(CourseGroup.teacher_id).where(
                        CourseGroup.course_id == just.course_id,
                        CourseGroup.is_active.is_(True),
                        CourseGroup.teacher_id.is_not(None),
                    )
                )
            ).all()
        }
        docentes.discard(actor.id)
        creadas += await crear_notificaciones(
            db,
            user_ids=docentes,
            kind="justificacion",
            title=f"Justificación eliminada en {codigo}",
            message=(
                f"{actor.full_name} eliminó la justificación de "
                f"{student.full_name if student else 'un estudiante'}."
            ),
            link="/admin/calendar/justifications",
            severity="warning",
            email=False,
            dedupe_key=f"just-del:{just.id}:teacher",
        )

    if actor.role is UserRole.DOCENTE:
        creadas += await crear_notificaciones(
            db,
            roles=[UserRole.ADMIN],
            kind="justificacion",
            title="Justificación eliminada por docente",
            message=(
                f"{actor.full_name} eliminó una justificación en {codigo}. "
                f"{revertidas} falta(s) vuelven a contar."
            ),
            link="/admin/calendar/justifications",
            severity="warning",
            email=False,
            dedupe_key=f"just-del:{just.id}:admin",
        )
    return creadas


async def notificar_rectificacion(
    db, *, record, session, actor, old_status: str, new_status: str, reason: str
) -> int:
    _bloque, _grupo, curso = await _contexto_sesion(db, session)
    codigo = curso.code if curso else "tu curso"
    mensaje = (
        f"Tu asistencia de {codigo} del {session.session_date} cambió de "
        f"{old_status} a {new_status}. Motivo: {reason}"
    )
    return await crear_notificaciones(
        db,
        user_ids=[record.student_id],
        kind="rectificacion",
        title="Asistencia rectificada",
        message=mensaje,
        link="/admin/my-attendance",
        severity="warning" if new_status == "falta" else "info",
        email=True,
    )


async def notificar_dispositivo_offline(db, *, device) -> int:
    aula = await db.get(Room, device.room_id)
    nombre = device.name or device.device_key
    lugar = f" del aula {aula.code}" if aula is not None else ""
    return await crear_notificaciones(
        db,
        roles=[UserRole.ADMIN],
        kind="dispositivo_offline",
        title="Dispositivo sin conexión",
        message=f"El dispositivo {nombre}{lugar} dejó de responder.",
        link="/admin/devices",
        severity="danger",
        email=False,
        dedupe_key=f"device:{device.id}:offline:{datetime.now(UTC).strftime('%Y%m%d%H')}",
    )


async def notificar_dpi(
    db,
    *,
    student: AppUser,
    course_id: int,
    course_code: str,
    level: str,
    sessions: int,
    absences: int,
    percent: float,
    semester: str,
    teacher_id: int | None = None,
) -> int:
    limite = level == "limite"
    titulo = "Inhabilitación por inasistencias" if limite else "Alerta de inasistencias"
    mensaje = (
        f"{course_code}: {absences} inasistencia(s) en {sessions} sesión(es) "
        f"({percent:.1f} %). "
        + (
            "Superaste el límite permitido; el curso puede quedar inhabilitado."
            if limite
            else "Alcanzaste el nivel de alerta preventiva."
        )
    )
    creadas = await crear_notificaciones(
        db,
        user_ids=[student.id],
        kind="dpi",
        title=titulo,
        message=mensaje,
        link="/admin/my-attendance",
        severity="danger" if limite else "warning",
        email=False,
        dedupe_key=f"dpi:{course_id}:{semester}:{level}",
    )
    if limite:
        creadas += await crear_notificaciones(
            db,
            user_ids=[teacher_id] if teacher_id else [],
            roles=[UserRole.ADMIN],
            kind="dpi_limite",
            title="Alumno en límite de inasistencias",
            message=(
                f"{student.full_name} superó el límite en {course_code} "
                f"({absences}/{sessions} sesiones, {percent:.1f} %)."
            ),
            link="/admin/at-risk",
            severity="warning",
            email=False,
            dedupe_key=f"dpi-limit:{course_id}:{student.id}:{semester}",
        )
    return creadas
