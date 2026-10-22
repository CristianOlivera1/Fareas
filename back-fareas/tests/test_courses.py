"""Tests de cursos/grupos/bloques/matrículas - RF-06, RF-22 (y auditoría RF-32)."""
import pytest
from httpx import AsyncClient
from sqlmodel import delete, select

from app.tables import AppUser, AuditLog, Course, CourseGroup, Enrollment, Room, ScheduleBlock

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
    teacher_id, _room_id = await _ids_base(client, admin_headers)

    # Docente inexistente → 404
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": 999999})
    assert r.status_code == 404

    # Grupo válido → 201 (el grupo no lleva aula: R9 la pone cada bloque)
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id})
    assert r.status_code == 201, r.text
    group = r.json()
    assert group["course_code"] == "TST901" and group["group_code"] == "A"
    assert "room_id" not in group and "room_code" not in group

    # Duplicado → 409
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "A", "teacher_id": teacher_id})
    assert r.status_code == 409

    # Estudiante como docente → 422
    students = (await client.get(f"{API}/students", headers=admin_headers)).json()
    student_id = students["items"][0]["id"]
    r = await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                          json={"group_code": "B", "teacher_id": student_id})
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
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    # Grupo B: otra aula, pero el MISMO docente (para provocar choque por docente)
    g_b = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "B", "teacher_id": teacher_id})).json()

    # Franja 16:00-19:00: libre en el seed (evita colisiones con ISA901…ISA906)
    # A: Lun 16:00-18:00 OK (cada bloque declara su aula)
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text
    bloque = r.json()

    # B: Lun 17:00-19:00 en aula distinta pero MISMO docente → 409 (choque docente)
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "17:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 409
    assert "Choque" in r.json()["detail"]

    # C: Lun 16:00-18:00 con OTRO docente pero misma aula → 409 (choque aula)
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers)).json()
    otro_docente = next(t["id"] for t in teachers["items"] if t["id"] != teacher_id)
    g_c = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "C", "teacher_id": otro_docente})).json()
    r = await client.post(f"{API}/groups/{g_c['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 409

    # D: Lun 16:00-18:00, otra aula y otro docente → OK (grupos paralelos válidos)
    g_d = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "D", "teacher_id": otro_docente})).json()
    r = await client.post(f"{API}/groups/{g_d['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text

    # Rango inválido → 422
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "18:00", "end_time": "17:00",
                                "room_id": room_a})
    assert r.status_code == 422

    # PATCH del bloque A a un rango libre → OK; verificación con listado
    r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                           json={"weekday": 5, "start_time": "18:00", "end_time": "20:00"})
    assert r.status_code == 200
    bloques = (await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)).json()
    assert any(b["id"] == bloque["id"] and b["weekday"] == 5 for b in bloques)


# ---------------------------------------------------------------------------
# Aula por BLOQUE (R9) - el grupo solo la sugiere
# ---------------------------------------------------------------------------
async def _aulas(client: AsyncClient, admin_headers: dict) -> dict[int, str]:
    rooms = (await client.get(f"{API}/rooms", headers=admin_headers, params={"page_size": 100})).json()
    return {r["id"]: r["code"] for r in rooms["items"]}


async def test_aula_por_bloque_es_obligatoria(client: AsyncClient, admin_headers: dict, db_session):
    """R9: el aula vive SOLO en el bloque. Sin room_id se rechaza con 422 (el
    grupo ya no la sugiere) y el mismo grupo puede dictar en labs distintos
    (ISA901 en LAB 401 y LAB 306)."""
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    codigos = await _aulas(client, admin_headers)
    room_b = next(r for r in codigos if r != room_a)

    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    assert "room_code" not in g_a  # el grupo no guarda aula

    # 1) Sin room_id → 422: el aula es obligatoria en cada bloque
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00"})
    assert r.status_code == 422, r.text
    assert "aula" in r.json()["detail"].lower()

    # 1b) Con room_id → el bloque se crea con ESA aula
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text
    assert r.json()["room_id"] == room_a and r.json()["room_code"] == codigos[room_a]
    bloque_a = r.json()

    # 2) Con room_id → el MISMO grupo dicta en otro laboratorio
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "18:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text
    assert r.json()["room_code"] == codigos[room_b]

    # 3) El listado devuelve el aula de CADA bloque (la usa la tabla de horario)
    bloques = (await client.get(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers)).json()
    assert {b["room_code"] for b in bloques} == {codigos[room_a], codigos[room_b]}

    # 4) PATCH del aula de un bloque → cambia y se audita
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
    """R9/RF-06: el choque se calcula con el aula DEL BLOQUE. Dos grupos del
    mismo semestre chocan si ponen un bloque en la MISMA aula."""
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, room_a = await _ids_base(client, admin_headers)
    teachers = (await client.get(f"{API}/teachers", headers=admin_headers, params={"page_size": 100})).json()
    otro = next(t["id"] for t in teachers["items"] if t["id"] != teacher_id)
    codigos = await _aulas(client, admin_headers)
    room_b = next(r for r in codigos if r != room_a)

    # A: su bloque de Lun 16:00-18:00 va a room_b
    g_a = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "A", "teacher_id": teacher_id})).json()
    r = await client.post(f"{API}/groups/{g_a['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_b})
    assert r.status_code == 201, r.text

    # B: el MISMO aula en el bloque 17:00-19:00 → 409 por aula
    g_b = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                             json={"group_code": "B", "teacher_id": otro})).json()
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 1, "start_time": "17:00", "end_time": "19:00",
                                "room_id": room_b})
    assert r.status_code == 409, r.text
    assert codigos[room_b] in r.json()["detail"] and "aula" in r.json()["detail"]

    # C: mismo rango pero en OTRA aula y OTRO docente → 201 (grupos paralelos válidos)
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "16:00", "end_time": "18:00",
                                "room_id": room_a})
    assert r.status_code == 201, r.text

    # D: aula inexistente → 404
    r = await client.post(f"{API}/groups/{g_b['id']}/blocks", headers=admin_headers,
                          json={"weekday": 2, "start_time": "18:00", "end_time": "19:00",
                                "room_id": 999999})
    assert r.status_code == 404


async def test_semana_lectiva_lunes_a_viernes(client: AsyncClient, admin_headers: dict, db_session):
    """La semana lectiva es Lun-Vie: sábado y domingo se rechazan con 422 (la BD
    lleva el CHECK como red de seguridad, la API explica el porqué)."""
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


# ---------------------------------------------------------------------------
# Horario general del semestre (una sola consulta para la rejilla completa)
# ---------------------------------------------------------------------------
async def test_horario_general_por_semestre_y_filtros(
    client: AsyncClient, admin_headers: dict, db_session
):
    """GET /schedule: un semestre a la vez (por defecto el vigente), con filtros
    de aula/docente/curso y sin los grupos inactivos salvo que se pidan."""
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

    # Por defecto: semestre vigente y solo activos
    filas = (await client.get(f"{API}/schedule", headers=admin_headers)).json()
    propia = next(f for f in filas if f["group_id"] == g_a["id"])
    assert propia["semester_label"] == semestre
    assert propia["room_id"] == room_a and propia["course_code"] == CURSO["code"]
    assert propia["teacher_name"] and propia["group_code"] == "A"

    # Filtros: aula propia / aula inexistente y semestre sin grupos
    assert any(f["group_id"] == g_a["id"] for f in (
        await client.get(f"{API}/schedule", headers=admin_headers, params={"room_id": room_a})
    ).json())
    assert (await client.get(f"{API}/schedule", headers=admin_headers,
                             params={"room_id": 999999})).json() == []
    assert (await client.get(f"{API}/schedule", headers=admin_headers,
                             params={"semester": "1900-X"})).json() == []

    # Un grupo inactivo desaparece por defecto y vuelve con include_inactive
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


# ---------------------------------------------------------------------------
# Franja de clases (RF-01) y reactivación del grupo
# ---------------------------------------------------------------------------
DOCENTE_TEMP_EMAIL = "temp.docente.horario@unamba.edu.pe"
AULA_TEMP = "LAB 990"


async def _limpiar_propios(db_session) -> None:
    """Borra el docente y el aula que crean estos dos tests (idempotencia)."""
    room = (await db_session.exec(select(Room).where(Room.code == AULA_TEMP))).first()
    if room is not None:
        await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.room_id == room.id))  # type: ignore[attr-defined]
        await db_session.delete(room)
    user = (await db_session.exec(select(AppUser).where(AppUser.email == DOCENTE_TEMP_EMAIL))).first()
    if user is not None:
        await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))  # type: ignore[attr-defined]
        await db_session.delete(user)
    await db_session.commit()


async def _grupo_propio(client: AsyncClient, admin_headers: dict, db_session) -> dict:
    """Curso + grupo con docente y aula PROPIOS del test.

    La BD demo la edita el usuario mientras se desarrolla: con el docente o el
    aula del seed, la hora que prueba el test podía estar ya ocupada por bloques
    ajenos (409) y el fallo no tendría nada que ver con la regla bajo prueba.
    """
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
    # El aula NO va en el grupo (R9): se devuelve aparte para los bloques.
    return {**r.json(), "room_id": room_id}


async def test_bloque_fuera_de_la_franja_de_clases(
    client: AsyncClient, admin_headers: dict, db_session
):
    """RF-01: la franja de clases es 07:00-20:00 (app_settings; editable en
    Parámetros). Un bloque que empiece antes o termine después se rechaza con
    422, tanto al crear como al editar; los bordes exactos sí se aceptan."""
    grupo = await _grupo_propio(client, admin_headers, db_session)
    try:
        for inicio, fin in (("06:00", "08:00"), ("19:00", "21:00"), ("21:00", "22:00")):
            r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                                  json={"weekday": 2, "start_time": inicio, "end_time": fin,
                                        "room_id": grupo["room_id"]})
            assert r.status_code == 422, f"{inicio}-{fin} está fuera de la franja: {r.text}"
            assert "franja" in r.json()["detail"]

        # Bordes exactos: la primera clase del día y la última
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

        # Editar un bloque tampoco puede sacarlo de la franja
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"start_time": "05:00"})
        assert r.status_code == 422, r.text
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"end_time": "22:00"})
        assert r.status_code == 422, r.text
        r = await client.patch(f"{API}/blocks/{bloque['id']}", headers=admin_headers,
                               json={"end_time": "10:00"})
        assert r.status_code == 200, r.text
    finally:
        await _cleanup_course(db_session)
        await _limpiar_propios(db_session)


async def test_reactivar_grupo(client: AsyncClient, admin_headers: dict, db_session):
    """La baja del grupo es LÓGICA: el grupo sigue en el listado (como
    "Inactivo") y se puede reactivar para volver a abrir sesiones con sus
    bloques de siempre."""
    grupo = await _grupo_propio(client, admin_headers, db_session)
    try:
        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 4, "start_time": "08:00", "end_time": "10:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 201, r.text

        # Baja lógica: sigue listado (la pantalla lo muestra como "Inactivo")
        r = await client.delete(f"{API}/groups/{grupo['id']}", headers=admin_headers)
        assert r.status_code == 200, r.text
        grupos = (await client.get(f"{API}/courses/{grupo['course_id']}/groups",
                                   headers=admin_headers)).json()
        assert next(g for g in grupos if g["id"] == grupo["id"])["is_active"] is False

        # Un grupo inactivo no acepta bloques nuevos: primero se reactiva
        r = await client.post(f"{API}/groups/{grupo['id']}/blocks", headers=admin_headers,
                              json={"weekday": 5, "start_time": "08:00", "end_time": "10:00",
                                    "room_id": grupo["room_id"]})
        assert r.status_code == 404

        # Reactivar → vuelve a estar activo, a aceptar bloques y queda en la bitácora
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

        # Reactivar algo que ya está activo → 422 (no-op, no un cambio silencioso)
        r = await client.post(f"{API}/groups/{grupo['id']}/activate", headers=admin_headers)
        assert r.status_code == 422, r.text
    finally:
        await _cleanup_course(db_session)
        await _limpiar_propios(db_session)


# ---------------------------------------------------------------------------
# Matrículas - RF-22
# ---------------------------------------------------------------------------
async def test_matricula_flujo(client: AsyncClient, admin_headers: dict, db_session, temp_student):
    await _cleanup_course(db_session)
    course = (await client.post(f"{API}/courses", headers=admin_headers, json=CURSO)).json()
    teacher_id, _room_id = await _ids_base(client, admin_headers)
    group = (await client.post(f"{API}/courses/{course['id']}/groups", headers=admin_headers,
                               json={"group_code": "A", "teacher_id": teacher_id})).json()

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

    # Limpieza final (este test no usa el fixture `curso`)
    await _cleanup_course(db_session)
