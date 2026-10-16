"""API de asistencia (Bloque 6): marca manual, cierre y rectificación RF-15."""
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


async def test_sessions_today(client, admin_headers, db_session, escenario):
    """F3: el listado de sesiones de hoy alimenta el modal RF-21."""
    esc = escenario
    # Antes de abrir la sesión: vacío (la del horario del test aún no existe)
    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []

    # Se abre la sesión LUN 08:00-10:00. El escenario B6 usa el próximo
    # lunes: si HOY no es lunes, se ancla la sesión a la fecha actual para
    # ejercitar la semántica real del endpoint (sesiones abiertas de HOY).
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()
    assert sesion is not None
    from datetime import timezone, timedelta

    peru_hoy = datetime.now(timezone(timedelta(hours=-5))).date()
    if sesion.session_date != peru_hoy:
        sesion.session_date = peru_hoy
        db_session.add(sesion)
        await db_session.commit()

    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) == 1
    s = filas[0]
    assert s["session_id"] == sesion.id
    assert s["status"] == "abierta"
    assert s["room_code"] == AULA
    assert s["course_code"] == CURSO
    assert s["group_code"] == "A"
    assert s["start_time"] == "08:00:00" and s["end_time"] == "10:00:00"

    # Cerrada: DESAPARECE del listado (solo sesiones abiertas de hoy)
    await client.post(f"{API}/sessions/{sesion.id}/close", headers=admin_headers)
    r = await client.get(f"{API}/attendance/sessions-today", headers=admin_headers)
    assert r.json() == [], r.text


async def test_attendance_me_del_estudiante(client, admin_headers, db_session, escenario):
    """GET /attendance/me: historial del estudiante autenticado (nuevo alcance:
    el rol ESTUDIANTE SÍ entra a la app con su vista personal)."""
    esc = escenario
    sesion, _ = await resolver_sesion(db_session, esc["aula_id"], now=h(esc["lunes"], "08:15"))
    await db_session.commit()
    assert sesion is not None

    # Marca manual para e1 (asistio); e2 queda sin marca en esta sesión
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

    # Admin/docente NO usan /attendance/me (403): su vista es la del panel
    r = await client.get(f"{API}/attendance/me", headers=admin_headers)
    assert r.status_code == 403

    # Historial del e1: su marca denomin 'asistio' con curso TST601
    r = await client.get(f"{API}/attendance/me", headers=_student_headers())
    assert r.status_code == 200, r.text
    filas = r.json()
    assert len(filas) >= 1
    propia = next(f for f in filas if f["record_id"] == r.json()[0]["record_id"])
    assert propia["course_code"] == CURSO
    assert propia["status"] == "asistio"
    assert propia["group_code"] == "A"
    assert propia["method"] == "manual"

    # Filtro por rango: solo exactamente este rango lo incluye
    r2 = await client.get(
        f"{API}/attendance/me?desde=2099-01-01&hasta=2099-12-31",
        headers=_student_headers(),
    )
    assert r2.status_code == 200 and r2.json() == []
