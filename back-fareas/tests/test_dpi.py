"""R7 — DPI: porcentaje sobre sesiones válidas, faltas justificadas aparte,
mínimo de sesiones, envío único por nivel y aislamiento por semestre.
"""
from datetime import date, datetime, timedelta

import pytest

from app.services.dpi import marcar_enviado, resumen_alumno
from app.tables import (
    AppSettings,
    AttendanceRecord,
    AttendanceSession,
    SessionStatus,
)
from tests.helpers_b6 import crear, limpiar

_API = "/api/v1"


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


async def _sembrar_sesiones(db, esc, estados_e2: list[tuple[str, bool]]) -> None:
    """Sesiones cerradas (válidas) con e1 siempre 'asistio' y e2 según la lista."""
    hoy = date.today()
    for i, (estado, justificada) in enumerate(estados_e2, start=1):
        sesion = AttendanceSession(
            block_id=esc["bloque_id"], session_date=hoy + timedelta(days=i),
            status=SessionStatus.CERRADA, needs_review=False, closed_at=datetime.now(),
        )
        db.add(sesion)
        await db.flush()
        db.add(AttendanceRecord(
            session_id=sesion.id, student_id=esc["e1"], status="asistio",
            marked_at=datetime.now(), method="facial",
        ))
        db.add(AttendanceRecord(
            session_id=sesion.id, student_id=esc["e2"], status=estado,
            marked_at=None if estado == "falta" else datetime.now(),
            method="facial", is_justified=justificada,
        ))
    await db.commit()


async def test_porcentaje_justificadas_y_nivel(db_session, escenario):
    """4 sesiones: e2 con 1 falta, 1 falta justificada y 2 asistencias → 25 % (alerta)."""
    esc = escenario
    await _sembrar_sesiones(db_session, esc, [
        ("falta", False),
        ("falta", True),   # justificada: NO cuenta para el porcentaje
        ("asistio", False),
        ("asistio", False),
    ])

    filas = await resumen_alumno(db_session, esc["e2"])
    fila = next(f for f in filas if f["course_id"] == esc["curso_id"])
    assert fila["sessions_held"] == 4
    assert fila["absences"] == 1 and fila["justified_absences"] == 1
    assert fila["absence_percent"] == 25.0
    assert fila["nivel"] == "alerta"  # ≥ 20 % y ≤ 30 %: aviso, no inhabilitación
    assert fila["lates"] == 0
    # Planificadas del semestre (R7): un lunes por semana; permitidas = 30 %
    assert fila["sesiones_planificadas"] is not None and fila["sesiones_planificadas"] > 0
    esperado_permitidas = int(fila["sesiones_planificadas"] * 30 / 100)
    assert fila["faltas_permitidas"] == esperado_permitidas
    assert fila["faltas_restantes"] == max(0, esperado_permitidas - 1)

    # e1 no tiene faltas
    fila1 = next(f for f in await resumen_alumno(db_session, esc["e1"]) if f["course_id"] == esc["curso_id"])
    assert fila1["absences"] == 0 and fila1["nivel"] is None


async def test_limite_al_superar_30(db_session, escenario):
    """Con 2 de 4 faltas (50 %) el alumno supera el límite → 'limite'."""
    esc = escenario
    await _sembrar_sesiones(db_session, esc, [
        ("falta", False),
        ("falta", False),
        ("asistio", False),
        ("asistio", False),
    ])
    fila = next(f for f in await resumen_alumno(db_session, esc["e2"]) if f["course_id"] == esc["curso_id"])
    assert fila["absence_percent"] == 50.0 and fila["nivel"] == "limite"


async def test_envio_unico_por_nivel_y_semestre(db_session, escenario):
    """R7: el control dpi_alert_sent deduplica (alumno, curso, semestre, nivel)."""
    esc = escenario
    semestre = (await db_session.get(AppSettings, 1)).semester_label
    primero = await marcar_enviado(db_session, esc["e2"], esc["curso_id"], semestre, "alerta")
    segundo = await marcar_enviado(db_session, esc["e2"], esc["curso_id"], semestre, "alerta")
    assert primero is True and segundo is False  # solo el primero envía correo
    assert await marcar_enviado(db_session, esc["e2"], esc["curso_id"], semestre, "limite") is True


async def test_cambio_de_semestre_no_mezcla_datos(db_session, escenario):
    """R1/R7: al cambiar semester_label, la vista no mezcla datos del anterior."""
    esc = escenario
    await _sembrar_sesiones(db_session, esc, [("falta", False)])
    assert len(await resumen_alumno(db_session, esc["e2"])) == 1

    cfg = await db_session.get(AppSettings, 1)
    original = cfg.semester_label
    try:
        cfg.semester_label = "2025-X"
        db_session.add(cfg)
        await db_session.commit()
        # Los grupos y sesiones del escenario son del semestre anterior → fuera
        assert await resumen_alumno(db_session, esc["e2"]) == []
    finally:
        cfg.semester_label = original
        db_session.add(cfg)
        await db_session.commit()
    assert len(await resumen_alumno(db_session, esc["e2"])) == 1
