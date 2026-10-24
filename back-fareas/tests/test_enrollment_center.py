from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlmodel import delete, select

from app.core.security import create_access_token
from app.services.attendance_engine import ahora_peru
from app.tables import (
    AppSettings,
    AppUser,
    AuditLog,
    Course,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
    UserRole,
)

API = "/api/v1"
COURSES = ("TSTCEN1", "TSTCEN2", "TSTCEN3", "TSTCEN4")
ROOM = "TST-CEN-ROOM"
EMAILS = [f"temp.center{n}@unamba.edu.pe" for n in (1, 2, 3)]
TEACHER = "temp.center.teacher@unamba.edu.pe"
CYCLE = 2


def _time(value: str):
    return datetime.strptime(value, "%H:%M").time()


async def _purge(db) -> None:
    course_ids = [c.id for c in (await db.exec(select(Course).where(Course.code.in_(COURSES)))).all()]
    group_ids = (
        [g.id for g in (await db.exec(select(CourseGroup).where(CourseGroup.course_id.in_(course_ids)))).all()]
        if course_ids
        else []
    )
    if group_ids:
        await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(group_ids)))
        await db.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))
        await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(group_ids)))
    if course_ids:
        await db.exec(delete(Course).where(Course.id.in_(course_ids)))
    await db.exec(delete(Room).where(Room.code == ROOM))
    users = (await db.exec(select(AppUser).where(AppUser.email.in_([*EMAILS, TEACHER])))).all()
    for user in users:
        await db.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
        await db.exec(delete(AppUser).where(AppUser.id == user.id))
    await db.exec(
        update(AppSettings).where(AppSettings.id == 1).values(enrollment_start=None, enrollment_end=None)
    )
    await db.commit()


@pytest.fixture
async def world(db_session):
    await _purge(db_session)
    settings = await db_session.get(AppSettings, 1)
    period = settings.semester_label

    room = Room(code=ROOM, name="Aula centro de matrícula")
    teacher = AppUser(
        role=UserRole.DOCENTE, email=TEACHER, full_name="Docente Centro", password_hash="x" * 20,
        must_change_password=False, dni="74440001",
    )
    students = [
        AppUser(
            role=UserRole.ESTUDIANTE, email=email, code=str(990100 + index), full_name=f"Alumno Centro {index}",
            password_hash="x" * 20, must_change_password=False, semester=CYCLE,
        )
        for index, email in enumerate(EMAILS, start=1)
    ]
    courses = [
        Course(code="TSTCEN1", name="Curso centro uno", cycle=CYCLE),
        Course(code="TSTCEN2", name="Curso centro dos", cycle=CYCLE),
        Course(code="TSTCEN3", name="Curso centro tres", cycle=CYCLE),
        Course(code="TSTCEN4", name="Curso centro cuatro", cycle=CYCLE + 1),
    ]
    db_session.add_all([room, teacher, *students, *courses])
    await db_session.flush()

    def group(course: Course, letter: str, capacity: int = 40) -> CourseGroup:
        return CourseGroup(
            course_id=course.id, group_code=letter, teacher_id=teacher.id, semester_label=period, capacity=capacity,
        )

    groups = SimpleNamespace(
        c1a=group(courses[0], "A"),
        c1b=group(courses[0], "B"),
        c2a=group(courses[1], "A", capacity=2),
        c3b=group(courses[2], "B"),
        c4a=group(courses[3], "A"),
    )
    db_session.add_all(vars(groups).values())
    await db_session.flush()
    blocks = [
        (groups.c1a, 1, "08:00", "10:00"),
        (groups.c1b, 3, "08:00", "10:00"),
        (groups.c2a, 2, "08:00", "10:00"),
        (groups.c3b, 4, "08:00", "10:00"),
        (groups.c4a, 1, "09:00", "11:00"),
    ]
    db_session.add_all(
        ScheduleBlock(group_id=g.id, room_id=room.id, weekday=w, start_time=_time(a), end_time=_time(b))
        for g, w, a, b in blocks
    )
    await db_session.commit()
    for obj in (*students, teacher, *vars(groups).values()):
        await db_session.refresh(obj)
    yield SimpleNamespace(students=students, groups=groups, teacher=teacher)
    await _purge(db_session)


def _student_headers(student: AppUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(student.id, 'estudiante')}"}


def _by_course(result: dict) -> dict[tuple[str, str], dict]:
    return {(row["student_code"], row["course_code"]): row for row in result["results"] if row["course_code"].startswith("TSTCEN")}


async def _open_window(client, admin_headers) -> None:
    today = ahora_peru().date()
    r = await client.patch(
        f"{API}/settings",
        headers=admin_headers,
        json={"enrollment_start": str(today - timedelta(days=1)), "enrollment_end": str(today + timedelta(days=5))},
    )
    assert r.status_code == 200, r.text


async def test_letters_and_package_preview_show_free_seats_and_missing_courses(client, admin_headers, world):
    letters = await client.get(f"{API}/enrollment/package-letters?cycle={CYCLE}", headers=admin_headers)
    assert {"A", "B"} <= {row["group_code"] for row in letters.json()}

    r = await client.get(f"{API}/enrollment/package?cycle={CYCLE}&group_code=a", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    courses = {row["course_code"]: row for row in data["courses"]}
    assert courses["TSTCEN1"]["free"] == 40 and courses["TSTCEN2"]["capacity"] == 2
    assert courses["TSTCEN1"]["blocks"][0]["weekday"] == 1
    assert "TSTCEN3" in {row["course_code"] for row in data["missing"]}


async def test_package_enrollment_reports_each_pair_and_full_groups(client, admin_headers, world):
    body = {"student_ids": [s.id for s in world.students], "cycle": CYCLE, "group_code": "A"}
    r = await client.post(f"{API}/enrollment/package", headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = _by_course(data)

    assert rows[("990101", "TSTCEN1")]["status"] == "ok", rows[("990101", "TSTCEN1")]
    assert rows[("990102", "TSTCEN2")]["status"] == "ok", rows[("990102", "TSTCEN2")]
    assert rows[("990103", "TSTCEN1")]["status"] == "ok", rows[("990103", "TSTCEN1")]
    assert rows[("990103", "TSTCEN2")]["status"] == "failed" and "lleno" in rows[("990103", "TSTCEN2")]["reason"]
    assert "TSTCEN3" in {row["course_code"] for row in data["missing"]}

    again = await client.post(f"{API}/enrollment/package", headers=admin_headers, json=body)
    assert _by_course(again.json())[("990101", "TSTCEN1")]["status"] == "skipped"


async def test_bulk_by_codes_reports_unknown_codes_and_schedule_conflicts(client, admin_headers, world):
    await client.post(
        f"{API}/enrollment/package",
        headers=admin_headers,
        json={"student_codes": ["990101"], "cycle": CYCLE, "group_code": "A"},
    )

    r = await client.post(
        f"{API}/enrollment/bulk",
        headers=admin_headers,
        json={"student_codes": ["990101", "000000"], "group_ids": [world.groups.c4a.id]},
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["unknown"] == ["000000"]
    assert data["failed"] == 1 and "se cruza" in data["results"][0]["reason"]


async def test_bulk_validations_and_permissions(client, admin_headers, docente_headers, world):
    payload = {"student_ids": [world.students[0].id], "group_ids": [world.groups.c1a.id]}
    assert (await client.post(f"{API}/enrollment/bulk", headers=docente_headers, json=payload)).status_code == 403
    assert (await client.post(f"{API}/enrollment/bulk", headers=_student_headers(world.students[0]), json=payload)).status_code == 403

    missing_group = await client.post(
        f"{API}/enrollment/bulk", headers=admin_headers, json={**payload, "group_ids": [999999999]}
    )
    assert missing_group.status_code == 404
    no_students = await client.post(
        f"{API}/enrollment/bulk", headers=admin_headers, json={"student_codes": ["000000"], "group_ids": [world.groups.c1a.id]}
    )
    assert no_students.status_code == 422

    resolved = await client.post(f"{API}/enrollment/resolve-students", headers=admin_headers, json={"codes": ["990102", "000000"]})
    assert [row["code"] for row in resolved.json()["found"]] == ["990102"] and resolved.json()["unknown"] == ["000000"]


async def test_the_window_is_closed_by_default_for_students(client, world):
    student = world.students[0]
    status_ = await client.get(f"{API}/me/enrollment", headers=_student_headers(student))
    assert status_.status_code == 200 and status_.json()["window"]["open"] is False

    r = await client.post(f"{API}/me/enrollment", headers=_student_headers(student), json={"group_id": world.groups.c1a.id})
    assert r.status_code == 403 and "matrícula" in r.json()["detail"].lower()


async def test_student_enrolls_switches_and_withdraws_within_the_window(client, admin_headers, world):
    await _open_window(client, admin_headers)
    student = world.students[0]
    headers = _student_headers(student)

    assert (await client.get(f"{API}/me/enrollment", headers=headers)).json()["window"]["open"] is True

    enrolled = await client.post(f"{API}/me/enrollment", headers=headers, json={"group_id": world.groups.c1a.id})
    assert enrolled.status_code == 201, enrolled.text

    offer = await client.get(f"{API}/me/enrollment/offer", headers=headers)
    rows = {(row["course_code"], row["group_code"]): row for row in offer.json() if row["course_code"].startswith("TSTCEN")}
    assert rows[("TSTCEN1", "A")]["mine"] is True
    assert rows[("TSTCEN1", "B")]["current_group_code"] == "A" and rows[("TSTCEN1", "B")]["conflict"] is None
    assert rows[("TSTCEN4", "A")]["conflict"] == "TSTCEN1 (grupo A)"

    switched = await client.post(
        f"{API}/me/enrollment/{world.groups.c1a.id}/transfer", headers=headers, json={"destino_group_id": world.groups.c1b.id}
    )
    assert switched.status_code == 200, switched.text

    withdrawn = await client.delete(f"{API}/me/enrollment/{world.groups.c1b.id}", headers=headers)
    assert withdrawn.status_code == 200, withdrawn.text


async def test_student_package_and_rule_errors_are_reported(client, admin_headers, world):
    await _open_window(client, admin_headers)
    first, second = world.students[0], world.students[1]
    await client.post(f"{API}/enrollment/package", headers=admin_headers, json={"student_ids": [second.id], "cycle": CYCLE, "group_code": "A"})
    await client.post(f"{API}/enrollment/package", headers=admin_headers, json={"student_ids": [world.students[2].id], "cycle": CYCLE, "group_code": "A"})

    r = await client.post(f"{API}/me/enrollment/package", headers=_student_headers(first), json={"cycle": CYCLE, "group_code": "A"})

    assert r.status_code == 200, r.text
    rows = _by_course(r.json())
    assert rows[("990101", "TSTCEN1")]["status"] == "ok"
    assert rows[("990101", "TSTCEN2")]["status"] == "failed" and "lleno" in rows[("990101", "TSTCEN2")]["reason"]

    full = await client.get(f"{API}/me/enrollment/offer?cycle={CYCLE}", headers=_student_headers(first))
    assert next(row for row in full.json() if row["course_code"] == "TSTCEN2")["full"] is True


async def test_students_cannot_use_admin_endpoints_or_other_roles_the_portal(client, admin_headers, world):
    assert (await client.get(f"{API}/enrollment/package?cycle={CYCLE}&group_code=A", headers=_student_headers(world.students[0]))).status_code == 403
    assert (await client.get(f"{API}/me/enrollment", headers=admin_headers)).status_code == 403


async def test_settings_reject_an_inverted_enrollment_window(client, admin_headers, world):
    today = ahora_peru().date()
    r = await client.patch(
        f"{API}/settings",
        headers=admin_headers,
        json={"enrollment_start": str(today + timedelta(days=3)), "enrollment_end": str(today)},
    )
    assert r.status_code == 422
