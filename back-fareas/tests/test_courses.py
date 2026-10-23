from datetime import date

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select

from app.tables import (
    AppUser,
    AttendanceSession,
    AuditLog,
    Course,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
)

pytestmark = pytest.mark.asyncio

API = "/api/v1"

CURSO = {"code": "TST901", "name": "Curso de Pruebas Bloque 4", "cycle": 9}


async def _cleanup_course(db_session) -> None:
    course = (await db_session.exec(select(Course).where(Course.code == CURSO["code"]))).first()
    if course is not None:
        group_ids = (
            await db_session.exec(select(CourseGroup.id).where(CourseGroup.course_id == course.id))
        ).all()
        if group_ids:
            await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))
            await db_session.exec(delete(Enrollment).where(Enrollment.group_id.in_(group_ids)))
            await db_session.exec(delete(CourseGroup).where(CourseGroup.id.in_(group_ids)))
        await db_session.delete(course)
        await db_session.commit()

@pytest.fixture
async def curso(db_session):
    await _cleanup_course(db_session)
    r = None
    yield r
    await _cleanup_course(db_session)

async def _ids_base(client: AsyncClient, admin_headers: dict) -> tuple[int, int]:
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers)).json()
    return teachers["items"][0]["id"], rooms["items"][0]["id"]

async def test_crear_y_listar_cursos(client: AsyncClient, admin_headers: dict, curso):
    r = await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)
    assert r.status_code == 201, r.text
    course = r.json()
    assert course["code"] == "TST901"
    assert course["cycle"] == 9

    r = await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)
    assert r.status_code == 409

    r = await client.post(f"{API}/courses", headers=admin_headers,
                          json={"code": "   ", "name": "Curso Vacío", "cycle": 9})
    assert r.status_code == 422

    r = await client.get(f"{API}/courses", headers=admin_headers, params={"q": "TST"})
    assert r.status_code == 200
    assert any(c["id"] == course["id"] for c in r.json()["items"])

async def test_editar_curso(client: AsyncClient, admin_headers: dict, db_session, curso):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()

    r = await client.patch(f"{API}/courses/{course['id']}", headers=admin_headers,
                           json={"name": "Curso de Pruebas Editado", "cycle": 8})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Curso de Pruebas Editado"
    assert r.json()["cycle"] == 8
    assert r.json()["code"] == CURSO["code"]

    r = await client.patch(f"{API}/courses/{course['id']}", headers=admin_headers,
                           json={"name": "   "})
    assert r.status_code == 422

    courses = (
        await client.get(f"{API}/courses", headers=admin_headers, params={"page_size": 100})
    ).json()["items"]
    otro = next(c for c in courses if c["id"] != course["id"])
    r = await client.patch(f"{API}/courses/{course['id']}", headers=admin_headers,
                           json={"code": otro["code"]})
    assert r.status_code == 409

    r = await client.patch(f"{API}/courses/999999", headers=admin_headers,
                           json={"name": "Curso Inexistente"})
    assert r.status_code == 404

async def test_eliminar_curso_sin_grupos(client: AsyncClient, admin_headers: dict, db_session, curso):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()

    r = await client.delete(f"{API}/courses/{course['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "eliminado" in r.json()["message"].lower()

    listado = (
        await client.get(f"{API}/courses", headers=admin_headers,
                         params={"q": CURSO["code"]})
    ).json()
    assert all(c["id"] != course["id"] for c in listado["items"])

    r = await client.delete(f"{API}/courses/{course['id']}", headers=admin_headers)
    assert r.status_code == 404

    r = await client.get(f"{API}/audit-log", headers=admin_headers,
                         params={"action": "curso_eliminado", "page_size": 5})
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1

async def test_no_eliminar_curso_con_grupos(client: AsyncClient, admin_headers: dict, db_session, curso):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, _room_id = await _ids_base(client, admin_headers)
    group = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                               json={"group_code": "A", "teacher_id": teacher_id})).json()

    r = await client.delete(f"{API}/courses/{course['id']}", headers=admin_headers)
    assert r.status_code == 409
    assert "grupo" in r.json()["detail"].lower()

    r = await client.delete(f"{API}/groups/{group['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    r = await client.delete(f"{API}/courses/{course['id']}", headers=admin_headers)
    assert r.status_code == 409

async def test_grupo_y_docente_invalido(client: AsyncClient, admin_headers: dict, db_session):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, _room_id = await _ids_base(client, admin_headers)

    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": 999999})
    assert r.status_code == 404

    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id})
    assert r.status_code == 201, r.text
    group = r.json()
    assert group["course_code"] == "TST901" and group["group_code"] == "A"
    assert "room_id" not in group and "room_code" not in group

    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id})
    assert r.status_code == 409

    students = (await client.get(f"{API}/students", headers=admin_headers)).json()
    student_id = students["items"][0]["id"]
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "B", "teacher_id": student_id})
    assert r.status_code == 422

async def test_choques_misma_aula_y_mismo_docente(client: AsyncClient, admin_headers: dict, db_session):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers)).json()
    room_b = next(r["id"] for r in rooms["items"] if r["id"] != room_a)

    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    g_b = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "B", "teacher_id": teacher_id})).json()

    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text
    bloque = r.json()

    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "17:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 409
    assert "Choque" in r.json()["detail"]

    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    otro_docente = next(t["id"] for t in teachers["items"] if t["id"] != teacher_id)
    g_c = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "C", "teacher_id": otro_docente})).json()
    r = await client.post(f"{API}/groups/{g_c['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 409

    g_d = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "D", "teacher_id": otro_docente})).json()
    r = await client.post(f"{API}/groups/{g_d['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "18:00", "end_time": "17:00",
                                "room_id": room_a})
    assert r.status_code == 422

    r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                           json={"weekday": 5, "start_time": "18:00", "end_time": "20:00"})
    assert r.status_code == 200
    bloques = (await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)).json()
    assert any(b["id"] == bloque["id"] and b["weekday"] == 5 for b in bloques)

async def _aulas(client: AsyncClient, admin_headers: dict) -> dict[int, str]:
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers, params={"page_size": 100})).json()
    return {r["id"]: r["code"] for r in rooms["items"]}

async def test_aula_por_bloque_es_obligatoria(client: AsyncClient, admin_headers: dict, db_session):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    codigos = await _aulas(client, admin_headers)
    room_b = next(r for r in codigos if r != room_a)

    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    assert "room_code" not in g_a

    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00"})
    assert r.status_code == 422, r.text
    assert "aula" in r.json()["detail"].lower()

    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text
    assert r.json()["room_id"] == room_a and r.json()["room_code"] == codigos[room_a]
    bloque_a = r.json()

    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "18:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text
    assert r.json()["room_code"] == codigos[room_b]

    bloques = (await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)).json()
    assert {b["room_code"] for b in bloques} == {codigos[room_a], codigos[room_b]}

    r = await client.patch(f"{API}/blocks/{bloque_a['id']}", headers=admin_headers,
                           json={"room_id": room_b})
    assert r.status_code == 200, r.text
    assert r.json()["room_id"] == room_b and r.json()["room_code"] == codigos[room_b]
    r = await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)
    moves = next(b for b in r.json() if b["id"] == bloque_a["id"])
    assert moves["room_code"] == codigos[room_b]

async def test_choque_por_aula_del_bloque(
    client: AsyncClient, admin_headers: dict, db_session
):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers, params={"page_size": 100})).json()
    otro = next(t["id"] for t in teachers["items"] if t["id"] != teacher_id)
    codigos = await _aulas(client, admin_headers)
    room_b = next(r for r in codigos if r != room_a)

    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text

    g_b = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "B", "teacher_id": otro})).json()
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "17:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 409, r.text
    assert codigos[room_b] in r.json()["detail"] and "aula" in r.json()["detail"]

    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "18:00", "end_time": "19:00",
                                "room_id": 999999})
    assert r.status_code == 404

async def test_semana_lectiva_lunes_a_viernes(client: AsyncClient, admin_headers: dict, db_session):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()

    for dia in (6, 7):
        r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                              json={"weekday": dia, "start_time": "16:00", "end_time": "18:00",
                                    "room_id": room_a})
        assert r.status_code == 422, f"weekday {dia} debería ser inválido"

    bloque = (await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                                json={"weekday": 5, "start_time": "16:00", "end_time": "18:00",
                                      "room_id": room_a})).json()
    r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers, json={"weekday": 6})
    assert r.status_code == 422

async def test_horario_general_por_semestre_y_filtros(
    client: AsyncClient, admin_headers: dict, db_session
):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    semestre = (await client.get(f"{API}/settings", headers=admin_headers)).json()["semester_label"]
    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text

    filas = (await client.get(f"{API}/schedule", headers=admin_headers)).json()
    propia = next(f for f in filas if f["group_id"] == g_a["id"])
    assert propia["semester_label"] == semestre
    assert propia["cycle"] == CURSO["cycle"]
    assert propia["room_id"] == room_a and propia["course_code"] == CURSO["code"]
    assert propia["teacher_name"] and propia["group_code"] == "A"

    assert any(f["group_id"] == g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers, params={"room_id": room_a})
    ).json())
    assert (await client.get(f"{API}/schedule", headers=admin_headers,
                             params={"room_id": 999999})).json() == []
    assert (await client.get(f"{API}/schedule", headers=admin_headers,
                             params={"semester": "1900-X"})).json() == []
    assert any(f["group_id"] == g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers,
                         params={"cycle": CURSO["cycle"]})
    ).json())
    assert all(f["group_id"] != g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers, params={"cycle": 1})
    ).json())
    assert any(g["id"] == g_a["id"] for g in (
        await client.get(f"{API}/groups", headers=admin_headers,
                         params={"cycle": CURSO["cycle"]})
    ).json())
    assert all(g["id"] != g_a["id"] for g in (
        await client.get(f"{API}/groups", headers=admin_headers, params={"cycle": 1})
    ).json())

    r = await client.delete(f"{API}/groups/{g_a['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert all(f["group_id"] != g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers)
    ).json())
    assert any(f["group_id"] == g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers,
                         params={"include_inactive": True})
    ).json())
    await _cleanup_course(db_session)

DOCENTE_TEMP_EMAIL = "temp.docente.horario@unamba.edu.pe"
AULA_TEMP = "LAB 990"


async def _limpiar_propios(db_session) -> None:
    room = (await db_session.exec(select(Room).where(Room.code == AULA_TEMP))).first()
    if room is not None:
        await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.room_id == room.id))
        await db_session.delete(room)
    user = (await db_session.exec(select(AppUser).where(AppUser.email == DOCENTE_TEMP_EMAIL))).first()
    if user is not None:
        await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
        await db_session.delete(user)
    await db_session.commit()

async def _grupo_propio(client: AsyncClient, admin_headers: dict, db_session) -> dict:
    await _cleanup_course(db_session)
    await _limpiar_propios(db_session)
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Temp Horario", "email": DOCENTE_TEMP_EMAIL,
                                "dni": "71999000"})
    assert r.status_code == 201, r.text
    teacher_id = r.json()["id"]
    r = await client.post(f"{API}/rooms", headers=admin_headers, json={"code": AULA_TEMP})
    assert r.status_code == 201, r.text
    room_id = r.json()["id"]
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id})
    assert r.status_code == 201, r.text
    return {**r.json(), "room_id": room_id}

async def test_bloque_fuera_de_la_franja_de_clases(
    client: AsyncClient, admin_headers: dict, db_session
):
    grupo = await _grupo_propio(client, admin_headers, db_session)
    try:
        for inicio, fin in (("06:00", "08:00"), ("19:00", "21:00"), ("21:00", "22:00")):
            r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                                  json={"weekday": 2, "start_time": inicio, "end_time": fin,
                                        "room_id": grupo["room_id"]})
            assert r.status_code == 422, f"{inicio}-{fin} está fuera de la franja: {r.text}"
            assert "franja" in r.json()["detail"]

        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 2, "start_time": "07:00", "end_time": "09:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 201, r.text
        bloque = r.json()
        assert bloque["start_time"].startswith("07:00")
        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 3, "start_time": "18:00", "end_time": "20:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 201, r.text

        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 4, "start_time": "16:00", "end_time": "19:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 422, r.text
        assert "2 horas" in r.json()["detail"]

        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"start_time": "05:00"})
        assert r.status_code == 422, r.text
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"end_time": "22:00"})
        assert r.status_code == 422, r.text
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"end_time": "10:00"})
        assert r.status_code == 422, r.text
        assert "2 horas" in r.json()["detail"]
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"end_time": "09:00"})
        assert r.status_code == 200, r.text
    finally:
        await _cleanup_course(db_session)
        await _limpiar_propios(db_session)

async def test_cannot_delete_block_with_sessions(
    client: AsyncClient, admin_headers: dict, db_session
):
    group = await _grupo_propio(client, admin_headers, db_session)
    session = None
    try:
        r = await client.post(
            f"{API}/groups/{group['id']}/blocks",
            headers=admin_headers,
            json={"weekday": 4, "start_time": "08:00", "end_time": "10:00",
                  "room_id": group["room_id"]},
        )
        assert r.status_code == 201, r.text
        block = r.json()

        session = AttendanceSession(block_id=block["id"], session_date=date.today())
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        r = await client.delete(f"{API}/blocks/{block['id']}", headers=admin_headers)
        assert r.status_code == 409, r.text
        assert "sesion" in r.json()["detail"].lower()

        blocks = (
            await client.get(f"{API}/groups/{group['id']}/blocks", headers=admin_headers)
        ).json()
        assert any(item["id"] == block["id"] for item in blocks)

        await db_session.delete(session)
        await db_session.commit()
        session = None

        r = await client.delete(f"{API}/blocks/{block['id']}", headers=admin_headers)
        assert r.status_code == 200, r.text
    finally:
        if session is not None:
            await db_session.delete(session)
            await db_session.commit()
        await _cleanup_course(db_session)
        await _limpiar_propios(db_session)

async def test_reactivar_grupo(client: AsyncClient, admin_headers: dict, db_session):
    grupo = await _grupo_propio(client, admin_headers, db_session)
    try:
        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 4, "start_time": "08:00", "end_time": "10:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 201, r.text

        r = await client.delete(f"{API}/groups/{grupo['id']}", headers=admin_headers)
        assert r.status_code == 200, r.text
        grupos = (await client.get(f"{API}/courses/{grupo['course_id']}/groups",
                                   headers=admin_headers)).json()
        assert next(g for g in grupos if g["id"] == grupo["id"])["is_active"] is False

        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 5, "start_time": "08:00", "end_time": "10:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 404

        r = await client.post(f"{API}/groups/{grupo['id']}/activate", headers=admin_headers)
        assert r.status_code == 200, r.text
        grupos = (await client.get(f"{API}/courses/{grupo['course_id']}/groups",
                                   headers=admin_headers)).json()
        assert next(g for g in grupos if g["id"] == grupo["id"])["is_active"] is True
        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 5, "start_time": "08:00", "end_time": "10:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 201, r.text
        r = await client.get(f"{API}/audit-log", headers=admin_headers,
                             params={"action": "grupo_reactivado", "page_size": 5})
        assert r.status_code == 200, r.text
        assert r.json()["total"] >= 1, "la reactivación debe quedar auditada (RF-32)"

        r = await client.post(f"{API}/groups/{grupo['id']}/activate", headers=admin_headers)
        assert r.status_code == 422, r.text
    finally:
        await _cleanup_course(db_session)
        await _limpiar_propios(db_session)

async def test_matricula_flujo(client: AsyncClient, admin_headers: dict, db_session, temp_student):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, _room_id = await _ids_base(client, admin_headers)
    group = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                               json={"group_code": "A", "teacher_id": teacher_id})).json()

    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert r.status_code == 200 and r.json() == []

    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 409

    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert any(s["id"] == temp_student.id for s in r.json())

    r = await client.delete(f"{API}/groups/{group['id']}/students/{temp_student.id}", headers=admin_headers)
    assert r.status_code == 200
    r = await client.get(f"{API}/groups/{group['id']}/students", headers=admin_headers)
    assert r.json() == []

    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    r = await client.post(f"{API}/groups/{group['id']}/students", headers=admin_headers,
                          json={"student_id": teachers["items"][0]["id"]})
    assert r.status_code == 422

    await _cleanup_course(db_session)
