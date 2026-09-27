"""Tests de cursos/grupos/bloques/matrículas - RF-06, RF-22 (y auditoría RF-32)."""
import pytest
from httpx import AsyncClient
from sqlmodel import delete, select

from app.tables import Course, CourseGroup, Enrollment, ScheduleBlock

pytestmark = pytest.mark.asyncio

API = "/api/v1"

CURSO = {"code": "TST901", "name": "Curso de Pruebas Bloque 4"}


async def _cleanup_course(db_session) -> None:
    """Elimina el curso de pruebas y todo lo que cuelga de él (FK cascade)."""
    course = (await db_session.exec(select(Course).where(Course.code == CURSO["code"]))).first()
    if course is not None:
        group_ids = (
            await db_session.exec(select(CourseGroup.id).where(CourseGroup.course_id == course.id))
        ).all()
        if group_ids:
            await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))  # type: ignore[attr-defined]
            await db_session.exec(delete(Enrollment).where(Enrollment.group_id.in_(group_ids)))  # type: ignore[attr-defined]
            await db_session.exec(delete(CourseGroup).where(CourseGroup.id.in_(group_ids)))  # type: ignore[attr-defined]
        await db_session.delete(course)
        await db_session.commit()


@pytest.fixture
async def curso(db_session):
    await _cleanup_course(db_session)
    r = None  # el curso lo crea la API en el primer test que lo necesite
    yield r
    await _cleanup_course(db_session)


async def _ids_base(client: AsyncClient, admin_headers: dict) -> tuple[int, int]:
    """Devuelve (teacher_id, room_id) de referencia del seed."""
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers)).json()
    return teachers["items"][0]["id"], rooms["items"][0]["id"]


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------
async def test_crear_y_listar_cursos(client: AsyncClient, admin_headers: dict, curso):
    r = await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)
    assert r.status_code == 201, r.text
    course = r.json()
    assert course["code"] == "TST901"

    # Duplicado → 409
    r = await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)
    assert r.status_code == 409

    # Listado con filtro
    r = await client.get(f"{API}/courses", headers=admin_headers, params={"q": "TST"})
    assert r.status_code == 200
    assert any(c["id"] == course["id"] for c in r.json()["items"])


async def test_grupo_y_docente_invalido(client: AsyncClient, admin_headers: dict, db_session):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_id = await _ids_base(client, admin_headers)

    # Docente inexistente → 404
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": 999999, "room_id": room_id})
    assert r.status_code == 404

    # Grupo válido → 201
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id, "room_id": room_id})
    assert r.status_code == 201, r.text
    group = r.json()
    assert group["course_code"] == "TST901" and group["group_code"] == "A"

    # Duplicado → 409
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id, "room_id": room_id})
    assert r.status_code == 409

    # Estudiante como docente → 422
    students = (await client.get(f"{API}/students", headers=admin_headers)).json()
    student_id = students["items"][0]["id"]
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "B", "teacher_id": student_id, "room_id": room_id})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Bloques + choques (RF-06) - el corazón del bloque
# ---------------------------------------------------------------------------
async def test_choques_misma_aula_y_mismo_docente(client: AsyncClient, admin_headers: dict, db_session):
    """Dos grupos paralelos: el choque se detecta por aula O por docente."""
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers)).json()
    room_b = next(r["id"] for r in rooms["items"] if r["id"] != room_a)

    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id, "room_id": room_a})).json()
    # Grupo B: otra aula, pero el MISMO docente (para provocar choque por docente)
    g_b = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "B", "teacher_id": teacher_id, "room_id": room_b})).json()

    # Franja 16:00-19:00: libre en el seed (evita colisiones con ISA901…ISA906)
    # A: Lun 16:00-18:00 OK
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00"})
    assert r.status_code == 201, r.text
    bloque = r.json()

    # B: Lun 17:00-19:00 en aula distinta pero MISMO docente → 409 (choque docente)
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "17:00", "end_time": "19:00"})
    assert r.status_code == 409
    assert "Choque" in r.json()["detail"]

    # C: Lun 16:00-18:00 con OTRO docente pero misma aula → 409 (choque aula)
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    otro_docente = next(t["id"] for t in teachers["items"] if t["id"] != teacher_id)
    g_c = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "C", "teacher_id": otro_docente, "room_id": room_a})).json()
    r = await client.post(f"{API}/groups/{g_c['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00"})
    assert r.status_code == 409

    # D: Lun 16:00-18:00, otra aula y otro docente → OK (grupos paralelos válidos)
    g_d = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "D", "teacher_id": otro_docente, "room_id": room_b})).json()
    r = await client.post(f"{API}/groups/{g_d['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00"})
    assert r.status_code == 201, r.text

    # Rango inválido → 422
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "18:00", "end_time": "17:00"})
    assert r.status_code == 422

    # PATCH del bloque A a un rango libre → OK; verificación con listado
    r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                           json={"weekday": 5, "start_time": "18:00", "end_time": "20:00"})
    assert r.status_code == 200
    bloques = (await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)).json()
    assert any(b["id"] == bloque["id"] and b["weekday"] == 5 for b in bloques)


# ---------------------------------------------------------------------------
# Matrículas - RF-22
# ---------------------------------------------------------------------------
async def test_matricula_flujo(client: AsyncClient, admin_headers: dict, db_session, temp_student):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_id = await _ids_base(client, admin_headers)
    group = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                               json={"group_code": "A", "teacher_id": teacher_id, "room_id": room_id})).json()

    # Listado vacío
    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert r.status_code == 200 and r.json() == []

    # Matricular
    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 201, r.text

    # Duplicada → 409
    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 409

    # Listado con el estudiante
    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert any(s["id"] == temp_student.id for s in r.json())

    # Desmatricular + verificar
    r = await client.delete(f"{API}/groups/{group['id']}/students/{temp_student.id}", headers=admin_headers)
    assert r.status_code == 200
    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert r.json() == []

    # No matricular a un docente → 422
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": teachers["items"][0]["id"]})
    assert r.status_code == 422
