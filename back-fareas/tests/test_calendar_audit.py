import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.tables import Holiday, Justification, Room

pytestmark = pytest.mark.asyncio

API = "/api/v1"


@pytest.fixture(autouse=True)
async def _limpiar_calendario(db_session):
    from datetime import date

    await db_session.exec(delete(Holiday).where(Holiday.description == "Feriado de prueba B4"))
    await db_session.exec(delete(Holiday).where(Holiday.holiday_date >= date(2027, 1, 1)))
    await db_session.exec(delete(Justification).where(Justification.reason == "Descanso médico de prueba B4"))
    await db_session.exec(delete(Justification).where(Justification.reason.like("Otra prueba B4%")))
    await db_session.exec(delete(Room).where(Room.code == "LAB 997"))
    await db_session.commit()
    yield
    await db_session.exec(delete(Holiday).where(Holiday.description == "Feriado de prueba B4"))
    await db_session.exec(delete(Holiday).where(Holiday.holiday_date >= date(2027, 1, 1)))
    await db_session.exec(delete(Justification).where(Justification.reason == "Descanso médico de prueba B4"))
    await db_session.exec(delete(Justification).where(Justification.reason.like("Otra prueba B4%")))
    await db_session.exec(delete(Room).where(Room.code == "LAB 997"))
    await db_session.commit()

async def test_feriados_crud(client: AsyncClient, admin_headers: dict):
    r = await client.post(f"{API}/holidays", headers=admin_headers,
                          json={"holiday_date": "2026-10-15", "description": "Feriado de prueba B4"})
    assert r.status_code == 201, r.text
    holiday = r.json()

    r = await client.post(f"{API}/holidays", headers=admin_headers,
                          json={"holiday_date": "2026-10-15", "description": "Repetido"})
    assert r.status_code == 409

    r = await client.get(f"{API}/holidays", headers=admin_headers)
    assert any(h["id"] == holiday["id"] for h in r.json())

    r = await client.delete(f"{API}/holidays/{holiday['id']}", headers=admin_headers)
    assert r.status_code == 200
    r = await client.get(f"{API}/holidays", headers=admin_headers)
    assert all(h["id"] != holiday["id"] for h in r.json())

async def test_feriados_por_rango_y_nacionales(client: AsyncClient, admin_headers: dict, db_session):
    from datetime import date

    from sqlmodel import delete

    from app.tables import Holiday

    r = await client.post(f"{API}/holidays/range", headers=admin_headers,
                          json={"desde": "2027-01-04", "hasta": "2027-01-10",
                                "descripcion": "Paro de prueba B11"})
    assert r.status_code == 201, r.text
    assert r.json()["creados"] == 5

    r = await client.post(f"{API}/holidays/range", headers=admin_headers,
                          json={"desde": "2027-01-04", "hasta": "2027-01-10",
                                "descripcion": "Paro de prueba B11"})
    assert r.json()["creados"] == 0 and r.json()["omitidos"] == 5

    r = await client.post(f"{API}/holidays/national", headers=admin_headers, json={"year": 2027})
    assert r.status_code == 201, r.text
    assert r.json()["creados"] == 16
    r = await client.get(f"{API}/holidays", headers=admin_headers)
    fechas = {h["holiday_date"] for h in r.json()}
    assert "2027-03-25" in fechas and "2027-12-25" in fechas

    await db_session.exec(delete(Holiday).where(Holiday.holiday_date >= date(2027, 1, 1)))
    await db_session.commit()

async def test_justificaciones_flujo(client: AsyncClient, admin_headers: dict, db_session):
    students = (await client.get(f"{API}/students", headers=admin_headers, params={"q": "221181"})).json()
    student_id = students["items"][0]["id"]
    courses = (await client.get(f"{API}/courses", headers=admin_headers)).json()
    course_id = courses["items"][0]["id"]

    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "start_date": "2026-10-10",
                                "end_date": "2026-10-05", "reason": "Rango invertido"})
    assert r.status_code == 422

    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "start_date": "2026-10-06",
                                "end_date": "2026-10-08", "reason": "Descanso médico de prueba B4"})
    assert r.status_code == 201, r.text
    just = r.json()
    assert just["course_id"] is None and just["student_id"] == student_id

    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "course_id": course_id,
                                "start_date": "2026-10-20", "end_date": "2026-10-21",
                                "reason": "Otra prueba B4 con curso"})
    assert r.status_code == 201

    r = await client.get(f"{API}/justifications", headers=admin_headers, params={"student_id": student_id})
    assert r.status_code == 200
    assert any(j["id"] == just["id"] for j in r.json())

async def test_parametros_lectura_y_update(client: AsyncClient, admin_headers: dict):
    r = await client.get(f"{API}/settings", headers=admin_headers)
    assert r.status_code == 200, r.text
    original = r.json()
    assert original["semester_label"]

    r = await client.patch(f"{API}/settings", headers=admin_headers, json={"late_tolerance_minutes": 15})
    assert r.status_code == 200
    assert r.json()["late_tolerance_minutes"] == 15

    r = await client.patch(f"{API}/settings", headers=admin_headers,
                           json={"late_tolerance_minutes": original["late_tolerance_minutes"]})
    assert r.status_code == 200

    r = await client.patch(f"{API}/settings", headers=admin_headers,
                           json={"attendance_hour_start": "21:00", "attendance_hour_end": "07:00"})
    assert r.status_code == 422

async def test_auditoria_registra_acciones(client: AsyncClient, admin_headers: dict, temp_student):
    room = (await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 997"})).json()
    assert room["id"] > 0

    r = await client.get(
        f"{API}/audit-log", headers=admin_headers,
        params={"action": "feriado_creado", "page_size": 5},
    )
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] >= 1
    entry = page["items"][0]
    assert entry["action"] == "feriado_creado"
    assert entry["entity"] == "holiday"
    assert entry["actor_name"] == "Admin Fareas"

    r = await client.get(
        f"{API}/audit-log", headers=admin_headers, params={"entity": "room", "page_size": 2, "page": 1}
    )
    data = r.json()
    assert len(data["items"]) <= 2
    assert data["total"] >= 1

    admin_me = (await client.get(f"{API}/auth/me", headers=admin_headers)).json()
    r = await client.get(f"{API}/audit-log", headers=admin_headers, params={"actor_id": admin_me["id"]})
    assert r.status_code == 200
    assert all(e["actor_id"] == admin_me["id"] for e in r.json()["items"])

async def test_auditoria_solo_admin(client: AsyncClient, docente_headers: dict):
    doc_headers = docente_headers
    assert (await client.get(f"{API}/audit-log", headers=doc_headers)).status_code == 403
    assert (await client.get(f"{API}/audit-log")).status_code == 401


async def test_aula_del_dashboard_se_configura_y_valida(client: AsyncClient, admin_headers: dict):
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers, params={"page_size": 1})).json()
    room_id = rooms["items"][0]["id"]
    try:
        r = await client.patch(f"{API}/settings", headers=admin_headers, json={"live_room_id": room_id})
        assert r.status_code == 200, r.text
        assert r.json()["live_room_id"] == room_id
        assert (await client.get(f"{API}/settings", headers=admin_headers)).json()["live_room_id"] == room_id

        inexistente = await client.patch(f"{API}/settings", headers=admin_headers, json={"live_room_id": 999999})
        assert inexistente.status_code == 422
    finally:
        limpiar = await client.patch(f"{API}/settings", headers=admin_headers, json={"live_room_id": None})
        assert limpiar.json()["live_room_id"] is None
