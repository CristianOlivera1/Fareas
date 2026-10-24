from datetime import timedelta
from types import SimpleNamespace

import pytest
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
PREFIX = "TSTSC"
ROOMS = [f"{PREFIX}-R{n}" for n in (1, 2, 3)]
TEACHER_EMAILS = [f"temp.sc.teacher{n}@unamba.edu.pe" for n in (1, 2)]
STUDENT_EMAILS = [f"temp.sc.student{n}@unamba.edu.pe" for n in (1, 2)]


async def _purge(db) -> None:
    courses = (await db.exec(select(Course).where(Course.code.like(f"{PREFIX}%")))).all()
    course_ids = [course.id for course in courses]
    group_ids: list[int] = []
    if course_ids:
        group_ids = [
            g.id for g in (await db.exec(select(CourseGroup).where(CourseGroup.course_id.in_(course_ids)))).all()
        ]
    if group_ids:
        await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(group_ids)))
        await db.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))
        await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(group_ids)))
    if course_ids:
        await db.exec(delete(Course).where(Course.id.in_(course_ids)))
    await db.exec(delete(Room).where(Room.code.in_(ROOMS)))
    users = (await db.exec(select(AppUser).where(AppUser.email.in_([*TEACHER_EMAILS, *STUDENT_EMAILS])))).all()
    for user in users:
        await db.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
        await db.exec(delete(AppUser).where(AppUser.id == user.id))
    await db.commit()


@pytest.fixture
async def world(db_session):
    await _purge(db_session)
    settings = await db_session.get(AppSettings, 1)
    rooms = [Room(code=code, name=code) for code in ROOMS]
    teachers = [
        AppUser(
            role=UserRole.DOCENTE, email=email, full_name=f"Docente SC {index}",
            password_hash="x" * 20, must_change_password=False, dni=f"7666000{index}",
        )
        for index, email in enumerate(TEACHER_EMAILS, start=1)
    ]
    students = [
        AppUser(
            role=UserRole.ESTUDIANTE, email=email, code=f"98800{index}", full_name=f"Alumno SC {index}",
            password_hash="x" * 20, must_change_password=False, semester=2,
        )
        for index, email in enumerate(STUDENT_EMAILS, start=1)
    ]
    db_session.add_all([*rooms, *teachers, *students])
    await db_session.commit()
    for item in [*rooms, *teachers, *students]:
        await db_session.refresh(item)
    yield SimpleNamespace(
        period=settings.semester_label, rooms=rooms, teachers=teachers, students=students, db=db_session
    )
    await _purge(db_session)


async def _group(world, suffix: str, *, cycle: int = 2, letter: str = "A", teacher=None, course=None) -> CourseGroup:
    db = world.db
    if course is None:
        course = Course(code=f"{PREFIX}{suffix}", name=f"Curso SC {suffix}", cycle=cycle)
        db.add(course)
        await db.flush()
    group = CourseGroup(
        course_id=course.id, group_code=letter, semester_label=world.period,
        teacher_id=teacher.id if teacher else None,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


async def _block(client, headers, group, weekday, start, end, room=None, teacher_id=None):
    body = {"weekday": weekday, "start_time": start, "end_time": end,
            "room_id": room.id if room else None}
    if teacher_id is not None:
        body["teacher_id"] = teacher_id
    return await client.post(f"{API}/groups/{group.id}/blocks", headers=headers, json=body)


async def _enroll(client, headers, group, student):
    return await client.post(f"{API}/groups/{group.id}/students", headers=headers,
                             json={"student_id": student.id})


def _student_headers(student) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(student.id, 'estudiante')}"}


async def test_room_conflict_blocks_overlap_but_allows_touching_boundaries(client, admin_headers, world):
    first = await _group(world, "01")
    second = await _group(world, "02")
    room = world.rooms[0]
    assert (await _block(client, admin_headers, first, 1, "08:00", "10:00", room)).status_code == 201

    overlap = await _block(client, admin_headers, second, 1, "09:00", "11:00", room)
    assert overlap.status_code == 409 and "aula" in overlap.json()["detail"].lower()
    inside = await _block(client, admin_headers, second, 1, "08:00", "09:00", room)
    assert inside.status_code == 409
    assert (await _block(client, admin_headers, second, 1, "10:00", "11:00", room)).status_code == 201
    assert (await _block(client, admin_headers, second, 2, "08:00", "10:00", room)).status_code == 201
    assert (await _block(client, admin_headers, second, 3, "08:00", "10:00", world.rooms[1])).status_code == 201


async def test_teacher_cannot_teach_two_groups_at_once_even_across_cycles(client, admin_headers, world):
    teacher = world.teachers[0]
    first = await _group(world, "03", cycle=1, teacher=teacher)
    second = await _group(world, "04", cycle=7, teacher=teacher)
    assert (await _block(client, admin_headers, first, 2, "08:00", "10:00", world.rooms[0])).status_code == 201

    clash = await _block(client, admin_headers, second, 2, "09:00", "10:00", world.rooms[1])
    assert clash.status_code == 409 and "docente" in clash.json()["detail"].lower()
    assert (await _block(client, admin_headers, second, 2, "10:00", "11:00", world.rooms[1])).status_code == 201


async def test_parallel_groups_of_same_course_may_share_the_slot(client, admin_headers, world):
    group_a = await _group(world, "05", letter="A", teacher=world.teachers[0])
    course = await world.db.get(Course, group_a.course_id)
    group_b = await _group(world, "05", letter="B", teacher=world.teachers[1], course=course)
    assert (await _block(client, admin_headers, group_a, 4, "08:00", "10:00", world.rooms[0])).status_code == 201
    assert (await _block(client, admin_headers, group_b, 4, "08:00", "10:00", world.rooms[1])).status_code == 201


async def test_a_group_cannot_have_two_overlapping_blocks(client, admin_headers, world):
    group = await _group(world, "06", teacher=world.teachers[0])
    assert (await _block(client, admin_headers, group, 1, "08:00", "10:00", world.rooms[0])).status_code == 201

    overlap = await _block(client, admin_headers, group, 1, "09:00", "11:00", world.rooms[1])
    assert overlap.status_code == 409
    assert (await _block(client, admin_headers, group, 1, "10:00", "11:00", world.rooms[1])).status_code == 201

    block_id = (await _block(client, admin_headers, group, 1, "13:00", "14:00", world.rooms[1])).json()["id"]
    moved = await client.patch(f"{API}/blocks/{block_id}", headers=admin_headers,
                               json={"start_time": "10:00", "end_time": "12:00"})
    assert moved.status_code == 409


async def test_block_limits_day_duration_and_order(client, admin_headers, world):
    group = await _group(world, "07", teacher=world.teachers[0])
    room = world.rooms[0]
    assert (await _block(client, admin_headers, group, 6, "08:00", "09:00", room)).status_code == 422
    assert (await _block(client, admin_headers, group, 1, "10:00", "09:00", room)).status_code in (409, 422)
    assert (await _block(client, admin_headers, group, 1, "08:00", "11:00", room)).status_code in (409, 422)
    assert (await _block(client, admin_headers, group, 1, "06:00", "08:00", room)).status_code in (409, 422)
    assert (await _block(client, admin_headers, group, 1, "19:00", "21:00", room)).status_code in (409, 422)
    assert (await _block(client, admin_headers, group, 1, "19:00", "20:00", room)).status_code == 201


async def test_student_cannot_enroll_in_overlapping_courses(client, admin_headers, world):
    student = world.students[0]
    first = await _group(world, "08", cycle=2)
    second = await _group(world, "09", cycle=5)
    third = await _group(world, "10", cycle=9)
    await _block(client, admin_headers, first, 1, "08:00", "10:00", world.rooms[0])
    await _block(client, admin_headers, second, 1, "09:00", "11:00", world.rooms[1])
    await _block(client, admin_headers, third, 1, "10:00", "11:00", world.rooms[2])
    assert (await _enroll(client, admin_headers, first, student)).status_code == 201

    clash = await _enroll(client, admin_headers, second, student)
    assert clash.status_code == 409 and "cruza" in clash.json()["detail"]
    assert (await _enroll(client, admin_headers, third, student)).status_code == 201


async def test_withdrawn_enrollment_and_inactive_group_do_not_block_the_student(client, admin_headers, world):
    student = world.students[0]
    first = await _group(world, "11")
    second = await _group(world, "12")
    await _block(client, admin_headers, first, 3, "08:00", "10:00", world.rooms[0])
    await _block(client, admin_headers, second, 3, "09:00", "10:00", world.rooms[1])
    assert (await _enroll(client, admin_headers, first, student)).status_code == 201
    assert (await _enroll(client, admin_headers, second, student)).status_code == 409

    assert (await client.delete(f"{API}/groups/{first.id}/students/{student.id}", headers=admin_headers)).status_code == 200
    assert (await _enroll(client, admin_headers, second, student)).status_code == 201


async def test_new_or_moved_block_cannot_clash_with_enrolled_students(client, admin_headers, world):
    student = world.students[0]
    first = await _group(world, "13")
    second = await _group(world, "14")
    await _block(client, admin_headers, first, 4, "08:00", "10:00", world.rooms[0])
    assert (await _enroll(client, admin_headers, first, student)).status_code == 201
    assert (await _enroll(client, admin_headers, second, student)).status_code == 201

    clash = await _block(client, admin_headers, second, 4, "09:00", "10:00", world.rooms[1])
    assert clash.status_code == 409 and "alumnos" in clash.json()["detail"]
    persisted = (await world.db.exec(select(ScheduleBlock).where(ScheduleBlock.group_id == second.id))).all()
    assert persisted == []

    ok = await _block(client, admin_headers, second, 4, "10:00", "11:00", world.rooms[1])
    assert ok.status_code == 201
    moved = await client.patch(f"{API}/blocks/{ok.json()['id']}", headers=admin_headers,
                               json={"start_time": "09:00", "end_time": "10:00"})
    assert moved.status_code == 409


async def test_transfer_between_parallel_groups_with_the_same_slot(client, admin_headers, world):
    student = world.students[0]
    group_a = await _group(world, "15", letter="A", teacher=world.teachers[0])
    course = await world.db.get(Course, group_a.course_id)
    group_b = await _group(world, "15", letter="B", teacher=world.teachers[1], course=course)
    await _block(client, admin_headers, group_a, 1, "08:00", "10:00", world.rooms[0])
    await _block(client, admin_headers, group_b, 1, "08:00", "10:00", world.rooms[1])
    assert (await _enroll(client, admin_headers, group_a, student)).status_code == 201

    moved = await client.post(
        f"{API}/groups/{group_a.id}/students/{student.id}/transfer",
        headers=admin_headers, json={"destino_group_id": group_b.id},
    )
    assert moved.status_code == 200, moved.text


async def test_transfer_is_rejected_when_destination_clashes_with_another_course(client, admin_headers, world):
    student = world.students[0]
    group_a = await _group(world, "16", letter="A", teacher=world.teachers[0])
    course = await world.db.get(Course, group_a.course_id)
    group_b = await _group(world, "16", letter="B", teacher=world.teachers[1], course=course)
    other = await _group(world, "17", cycle=6)
    await _block(client, admin_headers, group_a, 2, "08:00", "09:00", world.rooms[0])
    await _block(client, admin_headers, group_b, 2, "10:00", "12:00", world.rooms[1])
    await _block(client, admin_headers, other, 2, "11:00", "12:00", world.rooms[2])
    assert (await _enroll(client, admin_headers, group_a, student)).status_code == 201
    assert (await _enroll(client, admin_headers, other, student)).status_code == 201

    moved = await client.post(
        f"{API}/groups/{group_a.id}/students/{student.id}/transfer",
        headers=admin_headers, json={"destino_group_id": group_b.id},
    )
    assert moved.status_code == 409


async def test_reactivating_a_group_revalidates_room_teacher_and_students(client, admin_headers, world):
    teacher = world.teachers[0]
    student = world.students[0]
    old = await _group(world, "18", teacher=teacher)
    await _block(client, admin_headers, old, 5, "08:00", "10:00", world.rooms[0])
    await client.delete(f"{API}/groups/{old.id}", headers=admin_headers)

    rival = await _group(world, "19", teacher=world.teachers[1])
    await _block(client, admin_headers, rival, 5, "09:00", "10:00", world.rooms[0])
    room_clash = await client.post(f"{API}/groups/{old.id}/activate", headers=admin_headers)
    assert room_clash.status_code == 409

    await client.delete(f"{API}/groups/{rival.id}", headers=admin_headers)
    taught = await _group(world, "20", teacher=teacher)
    await _block(client, admin_headers, taught, 5, "09:00", "11:00", world.rooms[1])
    teacher_clash = await client.post(f"{API}/groups/{old.id}/activate", headers=admin_headers)
    assert teacher_clash.status_code == 409

    await client.delete(f"{API}/groups/{taught.id}", headers=admin_headers)
    assert (await client.post(f"{API}/groups/{old.id}/activate", headers=admin_headers)).status_code == 200
    assert student is not None


async def test_changing_group_teacher_checks_existing_blocks(client, admin_headers, world):
    busy = await _group(world, "21", teacher=world.teachers[1])
    mine = await _group(world, "22", teacher=world.teachers[0])
    await _block(client, admin_headers, busy, 1, "08:00", "10:00", world.rooms[0])
    await _block(client, admin_headers, mine, 1, "09:00", "10:00", world.rooms[1])

    clash = await client.patch(f"{API}/groups/{mine.id}", headers=admin_headers,
                               json={"teacher_id": world.teachers[1].id})
    assert clash.status_code == 409


async def test_self_enrollment_bulk_reports_overlap_and_offer_flags_it(client, admin_headers, world):
    today = ahora_peru().date()
    await client.patch(
        f"{API}/settings", headers=admin_headers,
        json={"enrollment_start": str(today - timedelta(days=1)), "enrollment_end": str(today + timedelta(days=3))},
    )
    try:
        student = world.students[1]
        first = await _group(world, "23", cycle=2)
        second = await _group(world, "24", cycle=2)
        await _block(client, admin_headers, first, 2, "08:00", "10:00", world.rooms[0])
        await _block(client, admin_headers, second, 2, "09:00", "10:00", world.rooms[1])
        headers = _student_headers(student)

        result = await client.post(
            f"{API}/me/enrollment/bulk", headers=headers,
            json={"items": [{"course_id": first.course_id}, {"course_id": second.course_id}]},
        )
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["ok"] == 1 and data["failed"] == 1
        failed = next(row for row in data["results"] if row["status"] == "failed")
        assert "cruza" in failed["reason"]

        offer = await client.get(f"{API}/me/enrollment/offer?cycle=2", headers=headers)
        flagged = {row["course_code"]: row["conflict"] for row in offer.json() if row["course_code"].startswith(PREFIX)}
        assert flagged[f"{PREFIX}24"] is not None and flagged[f"{PREFIX}23"] is None
    finally:
        await client.patch(
            f"{API}/settings", headers=admin_headers,
            json={"enrollment_start": None, "enrollment_end": None},
        )
