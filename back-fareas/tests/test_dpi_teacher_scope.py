from datetime import date, datetime, timedelta

import pytest
from sqlmodel import delete, select

from app.core.security import create_access_token
from app.tables import (
    AppSettings,
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    CourseGroup,
    SessionStatus,
    UserRole,
)
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
OTHER_TEACHER = "temp.docente.scope@unamba.edu.pe"


@pytest.fixture
async def scenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)

    other = AppUser(
        role=UserRole.DOCENTE,
        email=OTHER_TEACHER,
        full_name="Docente Otro Grupo",
        password_hash="x" * 20,
        must_change_password=False,
        dni="74444009",
    )
    db_session.add(other)
    await db_session.flush()
    semester = (await db_session.get(AppSettings, 1)).semester_label
    course_id = (await db_session.get(CourseGroup, esc["grupo_id"])).course_id
    db_session.add(CourseGroup(course_id=course_id, group_code="B", teacher_id=other.id, semester_label=semester))

    today = date.today()
    for offset in range(1, 5):
        session = AttendanceSession(
            block_id=esc["bloque_id"],
            session_date=today + timedelta(days=offset),
            status=SessionStatus.CERRADA,
            needs_review=False,
            closed_at=datetime.now(),
        )
        db_session.add(session)
        await db_session.flush()
        absent = offset <= 2
        db_session.add(
            AttendanceRecord(
                session_id=session.id,
                student_id=esc["e2"],
                status="falta" if absent else "asistio",
                marked_at=None if absent else datetime.now(),
                method="facial",
            )
        )
    await db_session.commit()
    esc["other_teacher_id"] = other.id
    yield esc

    await limpiar(db_session)
    await db_session.exec(delete(AppUser).where(AppUser.email == OTHER_TEACHER))
    await db_session.commit()


def _headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, 'docente')}"}


async def _at_risk_ids(client, user_id: int) -> set[int]:
    r = await client.get(f"{API}/dpi/at-risk?level=limite", headers=_headers(user_id))
    assert r.status_code == 200, r.text
    return {row["student_id"] for row in r.json()}


async def test_teacher_sees_students_of_their_own_group(client, scenario):
    assert scenario["e2"] in await _at_risk_ids(client, scenario["docente_id"])


async def test_teacher_of_another_group_of_the_same_course_does_not(client, scenario):
    assert scenario["e2"] not in await _at_risk_ids(client, scenario["other_teacher_id"])


async def test_dashboard_counts_follow_the_same_scope(client, scenario, db_session):
    own = await client.get(f"{API}/dashboard/summary", headers=_headers(scenario["docente_id"]))
    other = await client.get(f"{API}/dashboard/summary", headers=_headers(scenario["other_teacher_id"]))
    assert own.json()["alertas_dpi"] >= 1
    assert other.json()["alertas_dpi"] == 0

    stored = (await db_session.exec(select(AppUser).where(AppUser.email == OTHER_TEACHER))).first()
    assert stored is not None
