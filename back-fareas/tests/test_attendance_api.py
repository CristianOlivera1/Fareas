from datetime import datetime

import pytest
from sqlmodel import select

from app.services.attendance_engine import resolver_sesion
from app.tables import AttendanceRecord
from tests.helpers_b6 import AULA, CURSO, crear, h, limpiar

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

    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=admin_headers,
        json={"student_id": esc["e1"], "status": "asistio"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "asistio"

    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=admin_headers,
        json={"student_id": esc["e1"], "status": "tardanza"},
    )
    assert r.status_code == 409

    r = await client.post(f"{API}/sessions/{sesion.id}/close", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["faltas"] == 1

    rec_falta = (
        await db_session.exec(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == sesion.id,
                AttendanceRecord.student_id == esc["e2"],
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

    r = await client.get(
        f"{API}/audit-log", headers=admin_headers,
        params={"action": "rectificacion", "entity_id": rec_falta.id, "page_size": 5},
    )
    assert r.status_code == 200 and r.json()["total"] >= 1

async def test_docente_no_marca_en_grupo_ajeno(client, admin_headers, docente_headers, db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()

    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=docente_headers,
        json={"student_id": esc["e1"], "status": "asistio"},
    )
    assert r.status_code == 403

    r = await client.patch(
        f"{API}/attendance/1/rectify",
        headers=docente_headers,
        json={"new_status": "asistio", "reason": "No es mi grupo"},
    )
    assert r.status_code in (403, 404)

async def test_sessions_today(client, admin_headers, db_session, escenario):
    esc = escenario

    def _del_escenario(resp) -> list[dict]:
        return [f for f in resp.json() if f["group_id"] == esc["grupo_id"]]

    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert _del_escenario(r) == []

    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()
    assert sesion is not None
    from datetime import timedelta, timezone

    peru_hoy = datetime.now(timezone(timedelta(hours=-5))).date()
    if sesion.session_date != peru_hoy:
        sesion.session_date = peru_hoy
        db_session.add(sesion)
        await db_session.commit()

    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert r.status_code == 200, r.text
    filas = _del_escenario(r)
    assert len(filas) == 1
    s = filas[0]
    assert s["session_id"] == sesion.id
    assert s["status"] == "abierta"
    assert s["room_code"] == AULA
    assert s["course_code"] == CURSO
    assert s["group_code"] == "A"
    assert s["start_time"] == "08:00:00" and s["end_time"] == "10:00:00"

    await client.post(f"{API}/sessions/{sesion.id}/close", headers=admin_headers)
    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert _del_escenario(r) == [], r.text

async def test_attendance_me_del_estudiante(client, admin_headers, db_session, escenario):
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()
    assert sesion is not None

    r = await client.post(
        f"{API}/sessions/{sesion.id}/manual-mark",
        headers=admin_headers,
        json={"student_id": esc["e1"], "status": "asistio"},
    )
    assert r.status_code == 201, r.text

    def _student_headers() -> dict[str, str]:
        from app.core.security import create_access_token

        return {
            "Authorization": f"Bearer {create_access_token(esc['e1'], 'estudiante')}",
        }

    r = await client.get(f"{API}/attendance/me", headers=admin_headers)
    assert r.status_code == 403

    r = await client.get(f"{API}/attendance/me", headers=_student_headers())
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) >= 1
    propia = next(f for f in filas if f["record_id"] == r.json()[0]["record_id"])
    assert propia["course_code"] == CURSO
    assert propia["status"] == "asistio"
    assert propia["group_code"] == "A"
    assert propia["method"] == "manual"

    r2 = await client.get(
        f"{API}/attendance/me?desde=2099-01-01&hasta=2099-12-31",
        headers=_student_headers(),
    )
    assert r2.status_code == 200 and r2.json() == []
