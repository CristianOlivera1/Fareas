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
    assert s2 is not None and s2.id == s1.id

async def test_fuera_de_horario_y_feriado(db_session, escenario):
    esc = escenario
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "07:00"))
    assert s is None and b is None
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "12:00"))
    assert s is None and b is None
    db_session.add(Holiday(holiday_date=esc["lunes"], description=FERIADO_DESC))
    await db_session.commit()
    assert await es_feriado(db_session, esc["lunes"]) is True
    s, b = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:00"))
    assert s is None and b is None

async def test_ventana_de_tardanza_rf23(db_session, escenario):
    esc = escenario
    cfg = await _cfg(db_session)
    assert cfg.late_tolerance_minutes == 10 and cfg.early_open_minutes == 15

    s, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "07:44"))
    assert s is None
    s, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "07:45"))
    assert s is not None
    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "10:00"))
    assert s2 is not None and s2.id == s.id
    s3, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "10:01"))
    assert s3 is None

async def test_marca_unica_y_clasificacion(db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:10"))
    assert sesion is not None

    r1 = await registrar_marca(db_session, sesion, esc["e1"], similarity=0.91,
                               now=h(esc["lunes"], "08:10"))
    assert r1.status.value == "asistio"
    await db_session.commit()

    with pytest.raises(errors.ConflictError):
        await registrar_marca(db_session, sesion, esc["e1"], now=h(esc["lunes"], "08:20"))

    r2 = await registrar_marca(db_session, sesion, esc["e2"], now=h(esc["lunes"], "08:30"))
    assert r2.status.value == "tardanza"
    await db_session.commit()

async def test_cierre_genera_faltas_e_idempotente(db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:10"))
    await registrar_marca(db_session, sesion, esc["e1"], now=h(esc["lunes"], "08:05"))
    await db_session.commit()

    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["status"] == "cerrada" and resumen["faltas"] == 1

    marcas = (
        await db_session.exec(
            select(AttendanceRecord).where(AttendanceRecord.session_id == sesion.id)
        )
    ).all()
    por_est = {m.student_id: m for m in marcas}
    assert por_est[esc["e1"]].status.value == "asistio"
    assert por_est[esc["e2"]].status.value == "falta"
    assert por_est[esc["e2"]].marked_at is None

    assert (await cerrar_sesion(db_session, sesion))["status"] == "ya_cerrada"

    s2, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:30"))
    assert s2 is None

async def test_estudiante_no_matriculado_no_recibe_falta(db_session, escenario):
    from app.services.attendance_engine import resolver_revision
    from app.tables import AppUser

    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "10:30"))
    assert sesion is None
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "09:00"))
    assert sesion is not None

    resumen = await cerrar_sesion(db_session, sesion)
    assert resumen["status"] == "needs_review" and resumen["faltas"] == 0
    assert sesion.needs_review is True

    admin = await db_session.get(AppUser, esc["docente_id"])
    resumen2 = await resolver_revision(db_session, sesion, admin, "confirmar_faltas")
    assert resumen2["faltas"] == 2
    assert sesion.needs_review is False
    assert (await cerrar_sesion(db_session, sesion))["status"] == "ya_cerrada"

async def test_smoke_horario_settings(db_session, escenario):
    from app.tables import AppSettings

    s = await db_session.get(AppSettings, 1)
    assert s is not None
    assert s.attendance_hour_start < s.attendance_hour_end
    assert 0 < float(s.face_match_threshold) < 1

async def _cfg(db_session):
    from app.tables import AppSettings

    return await db_session.get(AppSettings, 1)
