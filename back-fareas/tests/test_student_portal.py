from datetime import date

import pytest

from app.core.security import create_access_token
from app.tables import Justification
from tests.helpers_b6 import CURSO, crear, limpiar

API = "/api/v1"


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


def _headers(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


async def test_my_schedule_lists_only_the_students_blocks(client, escenario):
    r = await client.get(f"{API}/me/schedule", headers=_headers(escenario["e1"], "estudiante"))
    assert r.status_code == 200, r.text
    rows = [row for row in r.json() if row["course_code"] == CURSO]
    assert len(rows) == 1
    assert rows[0]["weekday"] == 1
    assert rows[0]["start_time"] == "08:00:00"
    assert rows[0]["group_code"] == "A"


async def test_withdrawn_enrollment_disappears_from_my_schedule(client, escenario, db_session):
    from sqlmodel import select

    from app.tables import Enrollment

    enrollment = (
        await db_session.exec(select(Enrollment).where(Enrollment.student_id == escenario["e1"]))
    ).first()
    enrollment.withdrawn_at = date.today()
    db_session.add(enrollment)
    await db_session.commit()

    headers = _headers(escenario["e1"], "estudiante")
    schedule = (await client.get(f"{API}/me/schedule", headers=headers)).json()
    assert all(row["course_code"] != CURSO for row in schedule)


async def test_my_justifications_only_returns_own(client, escenario, db_session):
    for student_id, reason in ((escenario["e1"], "Cita médica"), (escenario["e2"], "Viaje")):
        db_session.add(
            Justification(
                student_id=student_id,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 2),
                reason=reason,
                created_by=escenario["docente_id"],
            )
        )
    await db_session.commit()

    r = await client.get(f"{API}/me/justifications", headers=_headers(escenario["e1"], "estudiante"))
    assert r.status_code == 200, r.text
    assert [j["reason"] for j in r.json()] == ["Cita médica"]
    assert r.json()[0]["created_by_name"] == "Docente B6"


@pytest.mark.parametrize("path", ["/me/schedule", "/me/justifications"])
async def test_student_portal_rejects_staff(client, admin_headers, path):
    r = await client.get(f"{API}{path}", headers=admin_headers)
    assert r.status_code == 403
