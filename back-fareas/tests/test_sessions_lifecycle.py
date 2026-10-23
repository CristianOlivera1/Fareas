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
from tests.helpers_b6 import crear, h, limpiar, weekday_hoy


async def _limpiar_aperturas_del_barrido(db) -> None:
    from sqlmodel import delete

    ids = [
        (i[0] if isinstance(i, tuple) else i)
        for i in (
            await db.exec(
                select(AttendanceSession.id).where(
                    AttendanceSession.status == SessionStatus.ABIERTA,
                    AttendanceSession.session_date >= datetime.now().date(),
                    ~AttendanceSession.id.in_(select(AttendanceRecord.session_id)),
                )
            )
        ).all()
    ]
    if ids:
        await db.exec(delete(AttendanceSession).where(AttendanceSession.id.in_(ids)))
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
                AttendanceSession.block_id == esc["bloque_id"],
                AttendanceSession.session_date == fecha,
            )
        )
    ).first()

async def test_apertura_sin_marcas_y_cierre_needs_review(db_session, escenario):
    esc = escenario
    lunes = esc["lunes"]

    await abrir_sesiones_del_dia(db_session, now=h(lunes, "07:44"))
    assert await _sesion_de_escenario(db_session, esc, lunes) is None
    await abrir_sesiones_del_dia(db_session, now=h(lunes, "07:50"))
    sesion = await _sesion_de_escenario(db_session, esc, lunes)
    assert sesion is not None and sesion.status is SessionStatus.ABIERTA

    await abrir_sesiones_del_dia(db_session, now=h(lunes, "08:05"))
    todas = (
        await db_session.exec(
            select(AttendanceSession).where(
                AttendanceSession.block_id == esc["bloque_id"],
                AttendanceSession.session_date == lunes,
            )
        )
    ).all()
    assert len(todas) == 1

    from app.services.attendance_engine import cerrar_sesion

    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["status"] == "needs_review" and resumen["faltas"] == 0
    assert sesion.needs_review is True

    from app.tables import AppUser

    admin = await db_session.get(AppUser, esc["docente_id"])
    resumen2 = await resolver_revision(db_session, sesion, admin, "confirmar_faltas")
    assert resumen2["faltas"] == 2
    faltas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)
        )
    ).all()
    assert {f.status.value for f in faltas} == {"falta"}

async def test_no_abre_sesion_sin_docente_o_aula(db_session, escenario):
    esc = escenario
    grupo = await db_session.get(CourseGroup, esc["grupo_id"])
    bloque = await db_session.get(ScheduleBlock, esc["bloque_id"])
    assert grupo is not None and bloque is not None
    grupo.teacher_id = None
    bloque.room_id = None
    db_session.add_all([grupo, bloque])
    await db_session.commit()

    lunes = esc["lunes"]
    abiertas = await abrir_sesiones_del_dia(db_session, now=h(lunes, "08:05"))
    assert abiertas == 0
    assert await _sesion_de_escenario(db_session, esc, lunes) is None

async def test_barrido_cierra_al_fin_del_bloque(db_session, escenario):
    esc = escenario
    hoy = datetime.now().date()
    bloque = ScheduleBlock(
        group_id=esc["grupo_id"], room_id=esc["aula_id"], weekday=weekday_hoy(),
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
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    assert sesion is not None

    from app.tables import AppUser

    admin = await db_session.get(AppUser, esc["docente_id"])
    resultado = await cancelar_sesion(db_session, sesion, admin, "Paro de transporte")
    assert resultado["status"] == "cancelada" and resultado["reason"] == "Paro de transporte"

    with pytest.raises(errors.DomainError):
        await cancelar_sesion(db_session, sesion, admin, "otra vez")

    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"))
    assert s2 is None

    faltas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)
        )
    ).all()
    assert faltas == []

async def test_cancelar_dia_futuro_crea_sesion_cancelada(db_session, escenario):
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

    await abrir_sesiones_del_dia(db_session, now=h(futuro, "07:50"))
    sesion = await _sesion_de_escenario(db_session, esc, futuro)
    assert sesion is not None and sesion.status is SessionStatus.CANCELADA

    with pytest.raises(errors.DomainError):
        await cancelar_dia(db_session, await db_session.get(ScheduleBlock, esc["bloque_id"]),
                           futuro + timedelta(days=1), admin, "Día equivocado")

async def test_bloques_contiguos_r10(db_session, escenario):
    esc = escenario
    cfg = await db_session.get(AppSettings, 1)
    assert cfg is not None

    grupo_b = CourseGroup(course_id=esc["curso_id"], group_code="B",
                          teacher_id=esc["docente_id"],
                          semester_label=cfg.semester_label)
    db_session.add(grupo_b)
    await db_session.flush()
    bloque_b = ScheduleBlock(group_id=grupo_b.id, room_id=esc["aula_id"], weekday=1,
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
        ses_a, bl_a = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"),
                                            student_id=esc["e1"])
        ses_b, bl_b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"),
                                            student_id=e3.id)
        assert bl_a.id == esc["bloque_id"] and bl_b.id == bloque_b.id

        _ses, bl_x = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"))
        assert bl_x.id == bloque_b.id

        _ses, bl_y = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"),
                                           student_id=e3.id)
        assert bl_y.id == esc["bloque_id"]
    finally:
        from sqlmodel import delete

        from app.tables import AuditLog

        ses = (await db_session.exec(
            select(AttendanceSession).where(AttendanceSession.block_id == bloque_b.id)
        )).all()
        for s in ses:
            await db_session.exec(delete(AttendanceRecord).where(AttendanceRecord.session_id == s.id))
            await db_session.delete(s)
        await db_session.flush()
        await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.id == bloque_b.id))
        await db_session.exec(delete(Enrollment).where(Enrollment.student_id == e3.id))
        await db_session.exec(delete(CourseGroup).where(CourseGroup.id == grupo_b.id))
        await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == e3.id))
        await db_session.delete(e3)
        await db_session.commit()
