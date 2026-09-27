"""API de asistencia (Bloque 6): marca manual, cierre y rectificación RF-15."""
import pytest
from sqlmodel import select

from app.services.attendance_engine import resolver_sesion
from app.tables import AttendanceRecord
from tests.helpers_b6 import crear, h, limpiar

API = "/api/v1"


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


async def test_marca_manual_cierre_y_rectificacion(client, admin_headers, db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()
    assert sesion is not None

    # Marca manual del admin (admin puede en cualquier grupo)
    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=admin_headers,
        json={"student_id": esc["e1"], "status": "asistio"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "asistio"

    # Duplicada por API → 409 (motor: marca única)
    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=admin_headers,
        json={"student_id": esc["e1"], "status": "tardanza"},
    )
    assert r.status_code == 409

    # Cierre manual (admin) → falta para e2
    r = await client.post(f"{API}/sessions/{sesion.id}/close", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["faltas"] == 1

    # Rectificación RF-15: e2 falta → tardanza con motivo
    rec_falta = (
        await db_session.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == sesion.id,
                AttendanceRecord.student_id == esc["e2"],  # type: ignore[arg-type]
            )
        )
    ).first()
    assert rec_falta is not None and rec_falta.status.value == "falta"

    r = await client.patch(
        f"{API}/attendance/{rec_falta.id}/rectify",
        headers=admin_headers,
        json={"new_status": "tardanza", "reason": "Llego 10:03, lo vi personalmente"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "tardanza"

    # La rectificación quedó en la bitácora (RF-32)
    r = await client.get(
        f"{API}/audit-log", headers=admin_headers,
        params={"action": "rectificacion", "entity_id": rec_falta.id, "page_size": 5},
    )
    assert r.status_code == 200 and r.json()["total"] >= 1


async def test_docente_no_marca_en_grupo_ajeno(client, admin_headers, docente_headers, db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()

    # docente_headers es OTRO docente (temp.docente.login) → 403
    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=docente_headers,
        json={"student_id": esc["e1"], "status": "asistio"},
    )
    assert r.status_code == 403

    # Y la rectificación sobre un registro ajeno también
    r = await client.patch(
        f"{API}/attendance/1/rectify",
        headers=docente_headers,
        json={"new_status": "asistio", "reason": "No es mi grupo"},
    )
    assert r.status_code in (403, 404)  # 404 si el record 1 no existe en la BD
