import pytest
from httpx import AsyncClient
from sqlmodel import delete, select

from app.tables import Course, CourseGroup, Enrollment, ScheduleBlock

pytestmark = pytest.mark.asyncio

API = "/api/v1"
CURSO_9 = "TSTC91"
CURSO_8 = "TSTC92"
CURSO_ANTIGUO = "TSTC93"


async def _limpiar(db_session) -> None:
    cursos = (
        await db_session.exec(
            select(Course).where(Course.code.in_([CURSO_9, CURSO_8, CURSO_ANTIGUO]))
        )
    ).all()
    ids = [c.id for c in cursos]
    if ids:
        grupos = (
            await db_session.exec(select(CourseGroup.id).where(CourseGroup.course_id.in_(ids)))
        ).all()
        gids = [g[0] if isinstance(g, tuple) else g for g in grupos]
        if gids:
            await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(gids)))
            await db_session.exec(delete(Enrollment).where(Enrollment.group_id.in_(gids)))
            await db_session.exec(delete(CourseGroup).where(CourseGroup.id.in_(gids)))
        await db_session.exec(delete(Course).where(Course.id.in_(ids)))
        await db_session.commit()


async def _curso(client: AsyncClient, headers: dict, code: str, cycle: int) -> dict:
    r = await client.post(
        f"{API}/courses",
        headers=headers,
        json={"code": code, "name": f"Curso de prueba {code}", "cycle": cycle},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _grupo(client: AsyncClient, headers: dict, course_id: int, teacher_id: int) -> dict:
    r = await client.post(
        f"{API}/courses/{course_id}/groups",
        headers=headers,
        json={"group_code": "A", "teacher_id": teacher_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _ids(client: AsyncClient, headers: dict) -> tuple[int, int, int]:
    teachers = (await client.get(f"{API}/teachers", headers=headers, params={"page_size": 100})).json()
    rooms = (await client.get(f"{API}/rooms", headers=headers, params={"page_size": 100})).json()
    assert len(teachers["items"]) >= 2
    return teachers["items"][0]["id"], teachers["items"][1]["id"], rooms["items"][0]["id"]


async def test_curso_ciclo_valido_y_filtros(client: AsyncClient, admin_headers: dict, db_session):
    await _limpiar(db_session)
    try:
        curso = await _curso(client, admin_headers, CURSO_9, 9)
        assert curso["cycle"] == 9

        for cycle in (0, 11):
            r = await client.post(
                f"{API}/courses",
                headers=admin_headers,
                json={"code": f"TSTC{cycle}", "name": "Ciclo inválido", "cycle": cycle},
            )
            assert r.status_code == 422, r.text

        r = await client.get(
            f"{API}/courses", headers=admin_headers, params={"q": CURSO_9, "cycle": 9}
        )
        assert any(c["id"] == curso["id"] for c in r.json()["items"])
        r = await client.get(
            f"{API}/courses", headers=admin_headers, params={"q": CURSO_9, "cycle": 8}
        )
        assert all(c["id"] != curso["id"] for c in r.json()["items"])

        teacher_id, _otro, room_id = await _ids(client, admin_headers)
        grupo = await _grupo(client, admin_headers, curso["id"], teacher_id)
        assert grupo["cycle"] == 9

        r = await client.post(
            f"{API}/groups/{grupo['id']}/blocks",
            headers=admin_headers,
            json={"weekday": 1, "start_time": "16:00", "end_time": "18:00", "room_id": room_id},
        )
        assert r.status_code == 201, r.text

        filas = (
            await client.get(f"{API}/schedule", headers=admin_headers, params={"cycle": 9})
        ).json()
        assert any(f["group_id"] == grupo["id"] and f["cycle"] == 9 for f in filas)
        filas = (
            await client.get(f"{API}/schedule", headers=admin_headers, params={"cycle": 8})
        ).json()
        assert all(f["group_id"] != grupo["id"] for f in filas)

        grupos = (
            await client.get(f"{API}/groups", headers=admin_headers, params={"cycle": 9})
        ).json()
        assert any(g["id"] == grupo["id"] and g["cycle"] == 9 for g in grupos)
        grupos = (
            await client.get(f"{API}/groups", headers=admin_headers, params={"cycle": 8})
        ).json()
        assert all(g["id"] != grupo["id"] for g in grupos)
    finally:
        await _limpiar(db_session)


async def test_choque_entre_ciclos_del_mismo_periodo(
    client: AsyncClient, admin_headers: dict, db_session
):
    await _limpiar(db_session)
    try:
        curso_8 = await _curso(client, admin_headers, CURSO_8, 8)
        curso_9 = await _curso(client, admin_headers, CURSO_9, 9)
        docente_8, docente_9, room_id = await _ids(client, admin_headers)
        grupo_8 = await _grupo(client, admin_headers, curso_8["id"], docente_8)
        grupo_9 = await _grupo(client, admin_headers, curso_9["id"], docente_9)

        r = await client.post(
            f"{API}/groups/{grupo_8['id']}/blocks",
            headers=admin_headers,
            json={"weekday": 2, "start_time": "16:00", "end_time": "18:00", "room_id": room_id},
        )
        assert r.status_code == 201, r.text

        r = await client.post(
            f"{API}/groups/{grupo_9['id']}/blocks",
            headers=admin_headers,
            json={"weekday": 2, "start_time": "17:00", "end_time": "19:00", "room_id": room_id},
        )
        assert r.status_code == 409, r.text
        assert "Choque" in r.json()["detail"]
    finally:
        await _limpiar(db_session)


async def test_bloque_de_periodo_antiguo_no_choca_con_el_vigente(
    client: AsyncClient, admin_headers: dict, db_session
):
    await _limpiar(db_session)
    try:
        curso = await _curso(client, admin_headers, CURSO_9, 9)
        teacher_id, _otro, room_id = await _ids(client, admin_headers)
        grupo = await _grupo(client, admin_headers, curso["id"], teacher_id)

        r = await client.post(
            f"{API}/groups/{grupo['id']}/blocks",
            headers=admin_headers,
            json={"weekday": 3, "start_time": "16:00", "end_time": "18:00", "room_id": room_id},
        )
        assert r.status_code == 201, r.text

        antiguo = Course(code=CURSO_ANTIGUO, name="Curso de periodo antiguo", cycle=8)
        db_session.add(antiguo)
        await db_session.flush()
        grupo_antiguo = CourseGroup(
            course_id=antiguo.id,
            group_code="A",
            teacher_id=teacher_id,
            semester_label="2020-I",
            capacity=40,
        )
        db_session.add(grupo_antiguo)
        await db_session.commit()

        r = await client.post(
            f"{API}/groups/{grupo_antiguo.id}/blocks",
            headers=admin_headers,
            json={"weekday": 3, "start_time": "17:00", "end_time": "19:00",
                  "room_id": room_id},
        )
        assert r.status_code == 201, r.text
    finally:
        await _limpiar(db_session)
