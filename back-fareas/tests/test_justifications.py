"""R6/R11 — justificaciones (efecto retroactivo y futuro, reversión, permisos)
y plazo de rectificación para docentes (R11).
"""
from datetime import date, timedelta

import pytest
from sqlmodel import select

from app.services import errors
from app.services.attendance_engine import cerrar_sesion, registrar_marca, resolver_sesion
from app.services.justifications import crear as crear_justificacion
from app.services.justifications import eliminar as eliminar_justificacion
from app.tables import AppUser, AttendanceRecord, UserRole
from tests.helpers_b6 import crear, h, limpiar

API = "/api/v1"


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


async def _sesion_con_e1_y_cierre(db, esc, fecha_lunes):
    """Abre la sesión del lunes, marca a e1 (para que el cierre SÍ genere
    faltas: cero marcas → needs_review) y cierra. Devuelve la sesión."""
    sesion, _ = await resolver_sesion(db, esc["aula_id"], now=h(fecha_lunes, "08:15"))
    assert sesion is not None
    await registrar_marca(db, sesion, esc["e1"], now=h(fecha_lunes, "08:05"))
    await db.commit()
    return sesion


async def _admin(db) -> AppUser:
    user = (await db.exec(select(AppUser).where(AppUser.email == "admin@unamba.edu.pe"))).first()
    assert user is not None
    return user


async def _falta(db, session_id: int, student_id: int) -> AttendanceRecord:
    rec = (
        await db.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,  # type: ignore[arg-type]
            )
        )
    ).first()
    assert rec is not None
    return rec


async def test_justificacion_efecto_retroactivo_y_reversion(db_session, escenario):
    """R6: crear justifica las faltas EXISTENTES del rango; eliminar revierte."""
    esc = escenario
    admin = await _admin(db_session)
    sesion = await _sesion_con_e1_y_cierre(db_session, esc, esc["lunes"])
    # e2 no marca → el cierre le genera falta
    await cerrar_sesion(db_session, sesion)
    falta = await _falta(db_session, sesion.id, esc["e2"])
    assert falta.status.value == "falta" and falta.is_justified is False

    just, afectadas = await crear_justificacion(
        db_session, admin, student_id=esc["e2"], course_id=esc["curso_id"],
        start_date=esc["lunes"], end_date=esc["lunes"],
        reason="Descanso médico presentado en secretaría",
    )
    assert afectadas == 1
    falta = await _falta(db_session, sesion.id, esc["e2"])
    assert falta.is_justified is True and falta.justification_id == just.id

    revertidas = await eliminar_justificacion(db_session, admin, just.id)
    assert revertidas == 1
    falta = await _falta(db_session, sesion.id, esc["e2"])
    assert falta.is_justified is False and falta.justification_id is None


async def test_falta_futura_nace_justificada(db_session, escenario):
    """R6: las faltas futuras dentro del rango nacen justificadas (el cierre
    consulta la justificación vigente)."""
    esc = escenario
    admin = await _admin(db_session)
    futuro = esc["lunes"] + timedelta(days=7)
    _just, afectadas = await crear_justificacion(
        db_session, admin, student_id=esc["e2"], course_id=esc["curso_id"],
        start_date=futuro, end_date=futuro, reason="Viaje académico autorizado",
    )
    assert afectadas == 0  # todavía no hay faltas; aplica a las futuras

    sesion = await _sesion_con_e1_y_cierre(db_session, esc, futuro)
    await cerrar_sesion(db_session, sesion)
    falta = await _falta(db_session, sesion.id, esc["e2"])
    assert falta.is_justified is True and falta.justification_id is not None


async def test_permisos_del_docente(db_session, escenario):
    """R6: docente sin grupos de ese curso o sin course_id → rechazado."""
    esc = escenario
    docente_ajeno = AppUser(
        role=UserRole.DOCENTE, email="temp.docente.b6.ajeno@unamba.edu.pe",
        full_name="Docente Ajeno B6", password_hash="x" * 20, must_change_password=False,
    )
    db_session.add(docente_ajeno)
    await db_session.commit()
    try:
        with pytest.raises(errors.DomainError):
            await crear_justificacion(
                db_session, docente_ajeno, student_id=esc["e2"], course_id=esc["curso_id"],
                start_date=esc["lunes"], end_date=esc["lunes"], reason="No es mi curso",
            )
        with pytest.raises(errors.DomainError):
            await crear_justificacion(
                db_session, docente_ajeno, student_id=esc["e2"], course_id=None,
                start_date=esc["lunes"], end_date=esc["lunes"], reason="Falta el curso",
            )
        # Un alumno no matriculado en sus grupos tampoco
        with pytest.raises(errors.DomainError):
            await crear_justificacion(
                db_session, docente_ajeno, student_id=esc["e1"], course_id=esc["curso_id"],
                start_date=esc["lunes"], end_date=esc["lunes"], reason="Alumno ajeno",
            )
    finally:
        from sqlmodel import delete

        await db_session.exec(delete(AppUser).where(AppUser.email == docente_ajeno.email))  # type: ignore[arg-type]
        await db_session.commit()


async def test_api_justify_y_bitacora(client, admin_headers, db_session, escenario):
    """R6 por API: PATCH /attendance/{id}/justify + rastro en /audit-log con
    actor_name y actor_role (R11/RF-32)."""
    esc = escenario
    sesion = await _sesion_con_e1_y_cierre(db_session, esc, esc["lunes"])
    await cerrar_sesion(db_session, sesion)
    falta = await _falta(db_session, sesion.id, esc["e2"])

    r = await client.patch(
        f"{API}/attendance/{falta.id}/justify", headers=admin_headers,
        json={"reason": "Certificado médico presentado al docente"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_justified"] is True and r.json()["justification_id"] is not None

    # Repetir la justificación → 409
    r = await client.patch(
        f"{API}/attendance/{falta.id}/justify", headers=admin_headers,
        json={"reason": "Otra vez"},
    )
    assert r.status_code == 409

    # La bitácora registra quién (nombre y rol) y qué valores cambiaron
    r = await client.get(f"{API}/audit-log", headers=admin_headers,
                         params={"action": "justificacion_creada", "page_size": 5})
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    entrada = r.json()["items"][0]
    assert entrada["actor_name"] == "Admin Fareas" and entrada["actor_role"] == "admin"


async def test_plazo_de_rectificacion_para_docente(client, admin_headers, docente_headers,
                                                   db_session, escenario):
    """R11: el docente solo rectifica los últimos rectify_days (7) días; el
    admin no tiene plazo."""
    from app.core.security import create_access_token

    esc = escenario
    sesion = await _sesion_con_e1_y_cierre(db_session, esc, esc["lunes"])
    await cerrar_sesion(db_session, sesion)
    falta = await _falta(db_session, sesion.id, esc["e2"])
    # Antigüedad de 10 días (> 7): fuera del plazo
    sesion.session_date = date.today() - timedelta(days=10)
    db_session.add(sesion)
    await db_session.commit()

    token_docente = create_access_token(esc["docente_id"], "docente")
    headers = {"Authorization": f"Bearer {token_docente}"}
    r = await client.patch(f"{API}/attendance/{falta.id}/rectify", headers=headers,
                           json={"new_status": "asistio", "reason": "Me equivoqué ese día"})
    assert r.status_code == 403 and "plazo" in r.json()["detail"].lower()

    # El admin sí puede (sin plazo) y cambiar de falta a asistio limpia la justificación
    r = await client.patch(f"{API}/attendance/{falta.id}/rectify", headers=admin_headers,
                           json={"new_status": "asistio", "reason": "Corrección administrativa"})
    assert r.status_code == 200 and r.json()["status"] == "asistio"
    falta = await _falta(db_session, sesion.id, esc["e2"])
    assert falta.is_justified is False and falta.justification_id is None
