import pytest
from sqlmodel import delete, select

from app.core.security import create_access_token
from app.tables import AppUser, AuditLog, UserRole

API = "/api/v1"
STUDENT_EMAIL = "temp.matrix.student@unamba.edu.pe"

ADMIN, TEACHER, STUDENT = "admin", "docente", "estudiante"
STAFF = {ADMIN, TEACHER}

READ_ENDPOINTS: dict[str, set[str]] = {
    "/rooms": STAFF,
    "/devices": STAFF,
    "/teachers": STAFF,
    "/students": STAFF,
    "/courses": STAFF,
    "/groups": STAFF,
    "/schedule": STAFF,
    "/holidays": STAFF,
    "/justifications": STAFF,
    "/settings": STAFF,
    "/settings/semesters": STAFF,
    "/audit-log": {ADMIN},
    "/dpi/at-risk": STAFF,
    "/attendance/today": STAFF,
    "/attendance/sessions-today": STAFF,
    "/attendance/sessions-review": STAFF,
    "/attendance/me": {STUDENT},
    "/attendance/me/dpi": {STUDENT},
    "/dashboard/summary": STAFF,
    "/stats/hourly": STAFF,
    "/stats/distribution": STAFF,
    "/me/schedule": {STUDENT},
    "/me/courses": {STUDENT},
    "/me/justifications": {STUDENT},
    "/reports/dpi-risk.xlsx": STAFF,
    "/enrollment/package-letters?cycle=1": {ADMIN},
    "/enrollment/package?cycle=1&group_code=A": {ADMIN},
    "/me/enrollment": {STUDENT},
    "/me/enrollment/offer": {STUDENT},
}


@pytest.fixture
async def headers_by_role(db_session, admin_headers, docente_headers):
    await db_session.exec(delete(AppUser).where(AppUser.email == STUDENT_EMAIL))
    await db_session.commit()
    student = AppUser(
        role=UserRole.ESTUDIANTE,
        email=STUDENT_EMAIL,
        code="991001",
        full_name="Estudiante Matriz",
        password_hash="x" * 20,
        must_change_password=False,
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    yield {
        ADMIN: admin_headers,
        TEACHER: docente_headers,
        STUDENT: {"Authorization": f"Bearer {create_access_token(student.id, 'estudiante')}"},
    }
    await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == student.id))
    await db_session.exec(delete(AppUser).where(AppUser.id == student.id))
    await db_session.commit()


@pytest.mark.parametrize("path", sorted(READ_ENDPOINTS))
async def test_every_read_endpoint_enforces_its_roles(client, headers_by_role, path):
    allowed = READ_ENDPOINTS[path]
    for role, headers in headers_by_role.items():
        response = await client.get(f"{API}{path}", headers=headers)
        if role in allowed:
            assert response.status_code not in (401, 403), f"{role} should reach {path}: {response.text}"
        else:
            assert response.status_code == 403, f"{role} must not reach {path}: {response.status_code}"


@pytest.mark.parametrize("path", sorted(READ_ENDPOINTS))
async def test_every_read_endpoint_requires_a_token(client, path):
    response = await client.get(f"{API}{path}")
    assert response.status_code == 401


async def test_student_account_exists_only_for_the_test(db_session, headers_by_role):
    stored = (await db_session.exec(select(AppUser).where(AppUser.email == STUDENT_EMAIL))).first()
    assert stored is not None
