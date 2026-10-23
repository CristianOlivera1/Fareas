from datetime import time

import pytest
from sqlmodel import delete, select

from app.tables import AppSettings, Course, CourseGroup, Enrollment, ScheduleBlock
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
CURSO2 = "TST602"
CURSO3 = "TST603"


async def _limpiar_cursos_extra(db) -> None:
    from app.tables import AttendanceRecord, AttendanceSession

    for code in (CURSO2, CURSO3):
        curso = (await db.exec(select(Course).where(Course.code == code))).first()
        if curso is None:
            continue
        ids = [(i[0] if isinstance(i, tuple) else i)
               for i in (await db.exec(select(CourseGroup.id).where(CourseGroup.course_id == curso.id))).all()]
        if ids:
            bloques = [(b[0] if isinstance(b, tuple) else b)
                       for b in (await db.exec(select(ScheduleBlock.id).where(ScheduleBlock.group_id.in_(ids)))).all()]
            if bloques:
                sesiones = [(s[0] if isinstance(s, tuple) else s)
                            for s in (await db.exec(select(AttendanceSession.id).where(
                                AttendanceSession.block_id.in_(bloques)))).all()]
                if sesiones:
                    await db.exec(delete(AttendanceRecord).where(AttendanceRecord.session_id.in_(sesiones)))
                    await db.exec(delete(AttendanceSession).where(AttendanceSession.id.in_(sesiones)))
                await db.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(ids)))
            await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(ids)))
            await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(ids)))
        await db.delete(curso)
    await db.commit()

@pytest.fixture
async def escenario(db_session):
    await _limpiar_cursos_extra(db_session)
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await _limpiar_cursos_extra(db_session)
    await limpiar(db_session)

async def _semestre(db) -> str:
    cfg = await db.get(AppSettings, 1)
    assert cfg is not None
    return cfg.semester_label

async def test_cupo_lleno_409(client, admin_headers, db_session, escenario, temp_student):
    esc = escenario
    grupo = await db_session.get(CourseGroup, esc["grupo_id"])
    assert grupo.capacity == 40

    grupo.capacity = 2
    db_session.add(grupo)
    await db_session.commit()
    r = await client.post(f"{API}/groups/{esc['grupo_id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 409
    assert "lleno" in r.json()["detail"].lower() and "2/2" in r.json()["detail"]

    r = await client.get(f"{API}/courses/{esc['curso_id']}/groups", headers=admin_headers)
    assert r.status_code == 200
    fila = next(g for g in r.json() if g["id"] == esc["grupo_id"])
    assert fila["capacity"] == 2 and fila["enrolled_count"] == 2
    assert fila["semester_label"] == await _semestre(db_session)

async def test_un_grupo_activo_por_curso_transferencia_y_retiro(
    client, admin_headers, db_session, escenario, temp_student
):
    esc = escenario
    semestre = await _semestre(db_session)
    grupo = await db_session.get(CourseGroup, esc["grupo_id"])
    grupo.capacity = 40
    db_session.add(grupo)

    grupo_b = CourseGroup(course_id=esc["curso_id"], group_code="B",
                          teacher_id=esc["docente_id"], semester_label=semestre)
    db_session.add(grupo_b)
    await db_session.commit()

    r = await client.post(f"{API}/groups/{grupo_b.id}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/groups/{esc['grupo_id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 409 and "grupo B" in r.json()["detail"]

    r = await client.post(
        f"{API}/groups/{grupo_b.id}/students/{temp_student.id}/transfer",
        headers=admin_headers, json={"destino_group_id": esc["grupo_id"]},
    )
    assert r.status_code == 200, r.text
    r = await client.get(f"{API}/groups/{grupo_b.id}/students", headers=admin_headers)
    fila = next(s for s in r.json() if s["id"] == temp_student.id)
    assert fila["withdrawn_at"] is not None
    r = await client.get(f"{API}/groups/{esc['grupo_id']}/students", headers=admin_headers)
    fila = next(s for s in r.json() if s["id"] == temp_student.id)
    assert fila["withdrawn_at"] is None

    otro = Course(code=CURSO3, name="Otro curso de prueba B11", cycle=9)
    db_session.add(otro)
    await db_session.flush()
    grupo_c = CourseGroup(course_id=otro.id, group_code="A", teacher_id=esc["docente_id"],
                          semester_label=semestre)
    db_session.add(grupo_c)
    await db_session.commit()
    r = await client.post(
        f"{API}/groups/{esc['grupo_id']}/students/{temp_student.id}/transfer",
        headers=admin_headers, json={"destino_group_id": grupo_c.id},
    )
    assert r.status_code == 422

    r = await client.delete(
        f"{API}/groups/{esc['grupo_id']}/students/{temp_student.id}", headers=admin_headers
    )
    assert r.status_code == 200
    assert (await db_session.exec(
        select(Enrollment).where(Enrollment.student_id == temp_student.id,
                                 Enrollment.group_id == esc["grupo_id"])
    )).first() is None

    ids = [(i[0] if isinstance(i, tuple) else i)
           for i in (await db_session.exec(select(CourseGroup.id).where(CourseGroup.course_id == otro.id))).all()]
    await db_session.exec(delete(Enrollment).where(Enrollment.group_id.in_(ids)))
    await db_session.exec(delete(CourseGroup).where(CourseGroup.course_id == otro.id))
    await db_session.delete(otro)
    await db_session.commit()

async def test_cruce_de_horario_del_alumno(client, admin_headers, db_session, escenario, temp_student):
    esc = escenario
    semestre = await _semestre(db_session)

    r = await client.post(f"{API}/groups/{esc['grupo_id']}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 201, r.text

    curso2 = Course(code=CURSO2, name="Curso cruzado de prueba B11", cycle=9)
    db_session.add(curso2)
    await db_session.flush()
    grupo2 = CourseGroup(course_id=curso2.id, group_code="A", teacher_id=esc["docente_id"],
                         semester_label=semestre)
    db_session.add(grupo2)
    await db_session.flush()
    db_session.add(ScheduleBlock(group_id=grupo2.id, room_id=esc["aula_id"], weekday=1,
                                 start_time=time(9, 30), end_time=time(11, 30)))
    await db_session.commit()

    r = await client.post(f"{API}/groups/{grupo2.id}/students", headers=admin_headers,
                          json={"student_id": temp_student.id})
    assert r.status_code == 409
    assert "se cruza" in r.json()["detail"]

    await db_session.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id == grupo2.id))
    await db_session.exec(delete(Enrollment).where(Enrollment.group_id == grupo2.id))
    await db_session.exec(delete(CourseGroup).where(CourseGroup.id == grupo2.id))
    await db_session.delete(curso2)
    await db_session.exec(delete(Enrollment).where(
        Enrollment.group_id == esc["grupo_id"], Enrollment.student_id == temp_student.id))
    await db_session.commit()

async def test_grupo_con_cupo_personalizado(client, admin_headers, db_session, escenario):
    esc = escenario
    r = await client.get(f"{API}/teachers", headers=admin_headers)
    teacher_id = r.json()["items"][0]["id"]
    r = await client.get(f"{API}/rooms", headers=admin_headers)
    room_id = r.json()["items"][0]["id"]

    r = await client.post(f"{API}/courses/{esc['curso_id']}/groups", headers=admin_headers,
                          json={"group_code": "C", "teacher_id": teacher_id, "room_id": room_id,
                                "capacity": 45})
    assert r.status_code == 201, r.text
    grupo = r.json()
    assert grupo["capacity"] == 45 and grupo["enrolled_count"] == 0
    assert grupo["semester_label"] == await _semestre(db_session)

    await db_session.exec(delete(CourseGroup).where(CourseGroup.id == grupo["id"]))
    await db_session.commit()
