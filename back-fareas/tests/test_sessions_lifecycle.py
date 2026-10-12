"""R3/R4/R5/R10 — ciclo de vida de las sesiones (Bloque 11).

- R3: el scheduler abre la sesión al iniciar la ventana (sin cámara, sin marcas).
- R4: cierre con cero marcas → needs_review SIN faltas; al confirmar, faltas.
- R5: cancelar una sesión (o un día futuro) no genera faltas ni cuenta.
- R10: bloques contiguos en la misma aula → decide la matrícula del alumno.
"""
from datetime import datetime, time, timedelta

import pytest
from sqlmodel import select

from app.services import errors
from app.services.attendance_engine import (
    abrir_sesiones_del_dia,
    cancelar_dia,
    cancelar_sesion,
    cerrar_sesiones_pendientes,
    resolver_revision,
    resolver_sesion,
)
from app.tables import (
    AppSettings,
    AttendanceRecord,
    AttendanceSession,
    CourseGroup,
    Enrollment,
    ScheduleBlock,
    SessionStatus,
)
from tests.helpers_b6 import CURSO, AULA, crear, h, limpiar


async def _limpiar_aperturas_del_barrido(db) -> None:
    """R3: `abrir_sesiones_del_dia` abre sesiones de TODOS los grupos del
    semestre (también los del seed). Al terminar el test se borran las que
    quedaron ABIERTAS, sin registros y de hoy en adelante: artefactos del
    barrido, no datos reales."""
    from sqlmodel import delete

    ids = [
        (i[0] if isinstance(i, tuple) else i)
        for i in (
            await db.exec(
                select(AttendanceSession.id).where(
                    AttendanceSession.status == SessionStatus.ABIERTA,  # type: ignore[arg-type]
                    AttendanceSession.session_date >= datetime.now().date(),
                    ~AttendanceSession.id.in_(select(AttendanceRecord.session_id)),  # type: ignore[union-attr]
                )
            )
        ).all()
    ]
    if ids:
        await db.exec(delete(AttendanceSession).where(AttendanceSession.id.in_(ids)))  # type: ignore[attr-defined]
    await db.commit()


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await _limpiar_aperturas_del_barrido(db_session)
    await limpiar(db_session)


async def _sesion_de_escenario(db, esc, fecha):
    return (
        await db.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == esc["bloque_id"],  # type: ignore[arg-type]
                AttendanceSession.session_date == fecha,
            )
        )
    ).first()


async def test_apertura_sin_marcas_y_cierre_needs_review(db_session, escenario):
    """R3: la sesión se abre sola; R4: cierra en el fin con needs_review."""
    esc = escenario
    lunes = esc["lunes"]

    # 07:44 → la ventana del bloque aún no abre (08:00 − 15 min); 07:50 → abre
    await abrir_sesiones_del_dia(db_session, now=h(lunes, "07:44"))
    assert await _sesion_de_escenario(db_session, esc, lunes) is None
    await abrir_sesiones_del_dia(db_session, now=h(lunes, "07:50"))
    sesion = await _sesion_de_escenario(db_session, esc, lunes)
    assert sesion is not None and sesion.status is SessionStatus.ABIERTA

    # Idempotente: el segundo barrido no duplica (UNIQUE bloque+fecha)
    await abrir_sesiones_del_dia(db_session, now=h(lunes, "08:05"))
    todas = (
        await db_session.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == esc["bloque_id"],  # type: ignore[arg-type]
                AttendanceSession.session_date == lunes,
            )
        )
    ).all()
    assert len(todas) == 1

    # Cierre manual (equivale al barrido a las 10:00): cero marcas → needs_review
    from app.services.attendance_engine import cerrar_sesion

    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["status"] == "needs_review" and resumen["faltas"] == 0
    assert sesion.needs_review is True

    # R4: el admin confirma las faltas de los matriculados (e1 y e2)
    from app.tables import AppUser

    admin = await db_session.get(AppUser, esc["docente_id"])
    resumen2 = await resolver_revision(db_session, sesion, admin, "confirmar_faltas")
    assert resumen2["faltas"] == 2
    faltas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)  # type: ignore[arg-type]
        )
    ).all()
    assert {f.status.value for f in faltas} == {"falta"}


async def test_barrido_cierra_al_fin_del_bloque(db_session, escenario):
    """R4: cerrar_sesiones_pendientes cierra en el FIN (no en fin+tolerancia)."""
    esc = escenario
    hoy = datetime.now().date()
    # Bloque auxiliar que ya terminó hoy (00:10-00:20) para el barrido real
    bloque = ScheduleBlock(
        group_id=esc["grupo_id"], weekday=hoy.isoweekday(),
        start_time=time(0, 10), end_time=time(0, 20),
    )
    db_session.add(bloque)
    await db_session.flush()
    sesion = AttendanceSession(block_id=bloque.id, session_date=hoy, status=SessionStatus.ABIERTA)
    db_session.add(sesion)
    await db_session.commit()

    resumenes = await cerrar_sesiones_pendientes(db_session)
    assert any(r["session_id"] == sesion.id and r["status"] == "needs_review" for r in resumenes)


async def test_cancelar_sesion_no_genera_faltas(db_session, escenario):
    """R5: cancelada no admite marcas ni genera faltas; el motivo se guarda."""
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    assert sesion is not None

    from app.tables import AppUser

    admin = await db_session.get(AppUser, esc["docente_id"])
    resultado = await cancelar_sesion(db_session, sesion, admin, "Paro de transporte")
    assert resultado["status"] == "cancelada" and resultado["reason"] == "Paro de transporte"

    # R5: no se puede volver a cancelar
    with pytest.raises(errors.DomainError):
        await cancelar_sesion(db_session, sesion, admin, "otra vez")

    # La sesión cancelada ya no resuelve (no admite marcas)
    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"))
    assert s2 is None

    # Y no hay registros de faltas
    faltas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)  # type: ignore[arg-type]
        )
    ).all()
    assert faltas == []


async def test_cancelar_dia_futuro_crea_sesion_cancelada(db_session, escenario):
    """R5: 'cancel-day' por adelantado crea la sesión ya cancelada para que
    el scheduler (R3) no la abra. Solo el ADMIN pre-cancela fechas futuras."""
    esc = escenario
    from app.tables import AppUser

    admin = (await db_session.exec(select(AppUser).where(AppUser.email == "admin@unamba.edu.pe"))).first()
    assert admin is not None
    lunes = esc["lunes"]
    assert lunes.isoweekday() == 1
    futuro = lunes + timedelta(days=7)
    resultado = await cancelar_dia(db_session, await db_session.get(ScheduleBlock, esc["bloque_id"]),
                                   futuro, admin, "Feriado local")
    assert resultado["status"] == "cancelada" and resultado["anticipada"] is True

    # El barrido de apertura del siguiente lunes NO reabre (sigue cancelada)
    await abrir_sesiones_del_dia(db_session, now=h(futuro, "07:50"))
    sesion = await _sesion_de_escenario(db_session, esc, futuro)
    assert sesion is not None and sesion.status is SessionStatus.CANCELADA

    # Y un día que no corresponde al bloque se rechaza
    with pytest.raises(errors.DomainError):
        await cancelar_dia(db_session, await db_session.get(ScheduleBlock, esc["bloque_id"]),
                           futuro + timedelta(days=1), admin, "Día equivocado")


async def test_bloques_contiguos_r10(db_session, escenario):
    """R10: dos bloques que se solapan en la misma aula; el desempate lo hace
    la matrícula del alumno reconocido y, sin alumno, el que empezó más tarde."""
    esc = escenario
    cfg = await db_session.get(AppSettings, 1)
    assert cfg is not None

    # Grupo B del MISMO curso en la MISMA aula, con bloque 09:00-11:00 (se solapa)
    grupo_b = CourseGroup(course_id=esc["curso_id"], group_code="B",
                          teacher_id=esc["docente_id"], room_id=esc["aula_id"],
                          semester_label=cfg.semester_label)
    db_session.add(grupo_b)
    await db_session.flush()
    bloque_b = ScheduleBlock(group_id=grupo_b.id, weekday=1,
                             start_time=time(9, 0), end_time=time(11, 0))
    db_session.add(bloque_b)

    from app.tables import AppUser

    e3 = AppUser(role="estudiante", email="temp.est3.b6@unamba.edu.pe", code="996003",
                 full_name="Estudiante Tres B6", password_hash="x" * 20, semester=5,
                 must_change_password=False, dni="74444003")
    db_session.add(e3)
    await db_session.flush()
    db_session.add(Enrollment(student_id=e3.id, group_id=grupo_b.id))
    await db_session.commit()

    try:
        # 09:30: las dos ventanas contienen el instante
        # e1 (matriculado en A) → bloque A; e3 (matriculado en B) → bloque B
        ses_a, bl_a = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"),
                                            student_id=esc["e1"])
        ses_b, bl_b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"),
                                            student_id=e3.id)
        assert bl_a.id == esc["bloque_id"] and bl_b.id == bloque_b.id

        # Sin alumno (p. ej. veredicto desconocido): gana el que empezó más tarde
        _ses, bl_x = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"))
        assert bl_x.id == bloque_b.id

        # 08:30: solo la ventana de A está activa
        _ses, bl_y = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"),
                                           student_id=e3.id)
        assert bl_y.id == esc["bloque_id"]
    finally:
        # Limpieza propia (limpiar() cubre el resto del escenario B6)
        from sqlmodel import delete

        from app.tables import AuditLog

        ses = (await db_session.exec(
            select(AttendanceSession).where(AttendanceSession.block_id == bloque_b.id)  # type: ignore[arg-type]
        )).all()
        for s in ses:  # registros → sesiones → bloque → matrícula → grupo → usuario
            await db_session.exec(delete(AttendanceRecord).where(AttendanceRecord.session_id == s.id))  # type: ignore[arg-type]
            await db_session.delete(s)
        await db_session.flush()
        await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.id == bloque_b.id))  # type: ignore[arg-type]
        await db_session.exec(delete(Enrollment).where(Enrollment.student_id == e3.id))  # type: ignore[arg-type]
        await db_session.exec(delete(CourseGroup).where(CourseGroup.id == grupo_b.id))  # type: ignore[arg-type]
        await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == e3.id))  # type: ignore[arg-type]
        await db_session.delete(e3)
        await db_session.commit()
