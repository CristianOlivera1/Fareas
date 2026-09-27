"""Tests del motor de asistencia (Bloque 6) — RF-21…RF-26.

El motor resuelve sesiones por aula/hora, marca única con clasificación
RF-23, cierre con faltas automáticas RF-26 y alertas DPI RF-24. Escenario
temporal creado por ``helpers_b6`` (limpio antes y después de cada test).
"""
import pytest
from sqlmodel import select

from app.services import errors
from app.services.attendance_engine import (
    cerrar_sesion,
    es_feriado,
    registrar_marca,
    resolver_sesion,
)
from app.tables import AttendanceRecord, Holiday
from tests.helpers_b6 import FERIADO_DESC, crear, h, limpiar


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


async def test_sesion_se_crea_y_se_reusa(db_session, escenario):
    esc = escenario
    s1, b1 = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"))
    assert s1 is not None and b1 is not None and b1.id == esc["bloque_id"]
    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:30"))
    assert s2 is not None and s2.id == s1.id  # misma sesión (UNIQUE bloque+fecha)


async def test_fuera_de_horario_y_feriado(db_session, escenario):
    esc = escenario
    # 07:00: antes del bloque
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "07:00"))
    assert s is None and b is None
    # 12:00: después del bloque + tolerancia
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "12:00"))
    assert s is None and b is None
    # Feriado: no abre aunque sea lunes 09:00
    db_session.add(Holiday(holiday_date=esc["lunes"], description=FERIADO_DESC))
    await db_session.commit()
    assert await es_feriado(db_session, esc["lunes"]) is True
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:00"))
    assert s is None and b is None


async def test_ventana_de_tardanza_rf23(db_session, escenario):
    """10:05 sigue abriendo (tolerancia 10 min); 10:20 ya no."""
    esc = escenario
    s, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "10:05"))
    assert s is not None
    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "10:20"))
    assert s2 is None


async def test_marca_unica_y_clasificacion(db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:10"))
    assert sesion is not None

    r1 = await registrar_marca(db_session, sesion, esc["e1"], similarity=0.91,
                               now=h(esc["lunes"], "08:10"))
    assert r1.status.value == "asistio"
    await db_session.commit()

    with pytest.raises(errors.ConflictError):  # marca ÚNICA (RF-21/Tabla 2)
        await registrar_marca(db_session, sesion, esc["e1"], now=h(esc["lunes"], "08:20"))

    r2 = await registrar_marca(db_session, sesion, esc["e2"], now=h(esc["lunes"], "10:04"))
    assert r2.status.value == "tardanza"  # dentro de la tolerancia post-bloque
    await db_session.commit()


async def test_cierre_genera_faltas_e_idempotente(db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:10"))
    await registrar_marca(db_session, sesion, esc["e1"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()

    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["status"] == "cerrada" and resumen["faltas"] == 1  # solo e2

    marcas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)  # type: ignore[arg-type]
        )
    ).all()
    por_est = {m.student_id: m for m in marcas}
    assert por_est[esc["e1"]].status.value == "asistio"
    assert por_est[esc["e2"]].status.value == "falta"
    assert por_est[esc["e2"]].marked_at is None  # falta generada por cierre

    assert (await cerrar_sesion(db_session, sesion))["status"] == "ya_cerrada"

    # sesión cerrada no reabre
    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"))
    assert s2 is None


async def test_estudiante_no_matriculado_no_recibe_falta(db_session, escenario):
    """El cierre solo genera faltas para MATRICULADOS del grupo."""
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:10"))
    # un tercero NO matriculado intenta marca (el pipeline con candidates
    # ya lo bloquea; el motor también por integridad del flujo):
    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["faltas"] == 2  # e1 y e2 (nadie marcó)
    # EST1/EST2 existen como usuarios pero solo 2 faltas generadas
    assert (await cerrar_sesion(db_session, sesion))["status"] == "ya_cerrada"


async def test_smoke_horario_settings(db_session, escenario):
    """app_settings existe y sus ventanas son coherentes (RF-34)."""
    from app.tables import AppSettings

    s = await db_session.get(AppSettings, 1)
    assert s is not None
    assert s.attendance_hour_start < s.attendance_hour_end
    assert 0 < float(s.face_match_threshold) < 1
