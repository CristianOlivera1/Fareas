"""Tests de calendario/parámetros/auditoría - RF-09, RF-10, RF-34, RF-32."""
import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.tables import Holiday, Justification, Room

pytestmark = pytest.mark.asyncio

API = "/api/v1"


@pytest.fixture(autouse=True)
async def _limpiar_calendario(db_session):
    """Limpia los registros temporales de estos tests antes y después."""
    await db_session.exec(delete(Holiday).where(Holiday.description == "Feriado de prueba B4"))  # type: ignore[arg-type]
    await db_session.exec(delete(Justification).where(Justification.reason == "Descanso médico de prueba B4"))  # type: ignore[arg-type]
    await db_session.exec(delete(Room).where(Room.code == "LAB 997"))  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.exec(delete(Holiday).where(Holiday.description == "Feriado de prueba B4"))  # type: ignore[arg-type]
    await db_session.exec(delete(Justification).where(Justification.reason == "Descanso médico de prueba B4"))  # type: ignore[arg-type]
    await db_session.exec(delete(Room).where(Room.code == "LAB 997"))  # type: ignore[attr-defined]
    await db_session.commit()


# ---------------------------------------------------------------------------
# Feriados - RF-09
# ---------------------------------------------------------------------------
async def test_feriados_crud(client: AsyncClient, admin_headers: dict):
    r = await client.post(f"{API}/holidays", headers=admin_headers,
                          json={"holiday_date": "2026-10-15", "description": "Feriado de prueba B4"})
    assert r.status_code == 201, r.text
    holiday = r.json()

    # Fecha duplicada → 409
    r = await client.post(f"{API}/holidays", headers=admin_headers,
                          json={"holiday_date": "2026-10-15", "description": "Repetido"})
    assert r.status_code == 409

    # Listado
    r = await client.get(f"{API}/holidays", headers=admin_headers)
    assert any(h["id"] == holiday["id"] for h in r.json())

    # Eliminar + verificar
    r = await client.delete(f"{API}/holidays/{holiday['id']}", headers=admin_headers)
    assert r.status_code == 200
    r = await client.get(f"{API}/holidays", headers=admin_headers)
    assert all(h["id"] != holiday["id"] for h in r.json())


# ---------------------------------------------------------------------------
# Justificaciones - RF-10
# ---------------------------------------------------------------------------
async def test_justificaciones_flujo(client: AsyncClient, admin_headers: dict, db_session):
    # Estudiante del seed (código 221181)
    students = (await client.get(f"{API}/students", headers=admin_headers, params={"q": "221181"})).json()
    student_id = students["items"][0]["id"]
    courses = (await client.get(f"{API}/courses", headers=admin_headers)).json()
    course_id = courses["items"][0]["id"]

    # Rango inválido → 422
    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "start_date": "2026-10-10",
                                "end_date": "2026-10-05", "reason": "Rango invertido"})
    assert r.status_code == 422

    # Válida, aplicable a todos los cursos (course_id NULL)
    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "start_date": "2026-10-06",
                                "end_date": "2026-10-08", "reason": "Descanso médico de prueba B4"})
    assert r.status_code == 201, r.text
    just = r.json()
    assert just["course_id"] is None and just["student_id"] == student_id

    # Válida con curso específico
    r = await client.post(f"{API}/justifications", headers=admin_headers,
                          json={"student_id": student_id, "course_id": course_id,
                                "start_date": "2026-10-20", "end_date": "2026-10-21",
                                "reason": "Otra prueba B4 con curso"})
    assert r.status_code == 201

    # Filtro por estudiante
    r = await client.get(f"{API}/justifications", headers=admin_headers, params={"student_id": student_id})
    assert r.status_code == 200
    assert any(j["id"] == just["id"] for j in r.json())


# ---------------------------------------------------------------------------
# Parámetros - RF-34
# ---------------------------------------------------------------------------
async def test_parametros_lectura_y_update(client: AsyncClient, admin_headers: dict):
    r = await client.get(f"{API}/settings", headers=admin_headers)
    assert r.status_code == 200, r.text
    original = r.json()
    assert original["semester_label"]  # existe y es no vacío (el seed trae '2026-I')

    # Update de tolerancia de tardanza
    r = await client.patch(f"{API}/settings", headers=admin_headers, json={"late_tolerance_minutes": 15})
    assert r.status_code == 200
    assert r.json()["late_tolerance_minutes"] == 15

    # Restaurar
    r = await client.patch(f"{API}/settings", headers=admin_headers,
                           json={"late_tolerance_minutes": original["late_tolerance_minutes"]})
    assert r.status_code == 200

    # Horario inválido (inicio >= fin) → 422
    r = await client.patch(f"{API}/settings", headers=admin_headers,
                           json={"attendance_hour_start": "21:00", "attendance_hour_end": "07:00"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Bitácora - RF-32 (lectura admin; las acciones anteriores deben quedar)
# ---------------------------------------------------------------------------
async def test_auditoria_registra_acciones(client: AsyncClient, admin_headers: dict, temp_student):
    # Genera acciones auditadas con el flujo normal de la API
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
    assert entry["actor_name"] == "Admin Fareas"  # admin del seed

    # Filtro por entidad y paginación coherente
    r = await client.get(
        f"{API}/audit-log", headers=admin_headers, params={"entity": "room", "page_size": 2, "page": 1}
    )
    data = r.json()
    assert len(data["items"]) <= 2
    assert data["total"] >= 1

    # Filtro por actor (admin del seed)
    admin_me = (await client.get(f"{API}/auth/me", headers=admin_headers)).json()
    r = await client.get(f"{API}/audit-log", headers=admin_headers, params={"actor_id": admin_me["id"]})
    assert r.status_code == 200
    assert all(e["actor_id"] == admin_me["id"] for e in r.json()["items"])


async def test_auditoria_solo_admin(client: AsyncClient, docente_headers: dict):
    doc_headers = docente_headers  # docente de PRUEBA (no depende del seed)
    assert (await client.get(f"{API}/audit-log", headers=doc_headers)).status_code == 403
    assert (await client.get(f"{API}/audit-log")).status_code == 401
