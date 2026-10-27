from types import SimpleNamespace

import pytest
from sqlmodel import delete, select

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
CODES = ("TSTIMP1", "TSTIMP2", "TSTIMP3")
ROOM_A, ROOM_B = "TST-IMP-A", "TST-IMP-B"
TEACHERS = ["temp.imp.t1@unamba.edu.pe", "temp.imp.t2@unamba.edu.pe"]
STUDENTS = ["temp.imp.s1@unamba.edu.pe", "temp.imp.s2@unamba.edu.pe"]
CYCLE = 4


async def _purge(db) -> None:
    course_ids = [c.id for c in (await db.exec(select(Course).where(Course.code.in_(CODES)))).all()]
    if course_ids:
        group_ids = [
            g.id for g in (await db.exec(select(CourseGroup).where(CourseGroup.course_id.in_(course_ids)))).all()
        ]
        if group_ids:
            await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(group_ids)))
            await db.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))
            await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(group_ids)))
        await db.exec(delete(Course).where(Course.id.in_(course_ids)))
    await db.exec(delete(Room).where(Room.code.in_([ROOM_A, ROOM_B])))
    for user in (await db.exec(select(AppUser).where(AppUser.email.in_([*TEACHERS, *STUDENTS])))).all():
        await db.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
        await db.exec(delete(AppUser).where(AppUser.id == user.id))
    await db.commit()


@pytest.fixture
async def world(db_session):
    await _purge(db_session)
    rooms = [Room(code=ROOM_A, name="Aula A"), Room(code=ROOM_B, name="Aula B")]
    teachers = [
        AppUser(
            role=UserRole.DOCENTE, email=email, full_name=f"Docente Imp {i}", password_hash="x" * 20,
            must_change_password=False, dni=f"7444100{i}",
        )
        for i, email in enumerate(TEACHERS, start=1)
    ]
    students = [
        AppUser(
            role=UserRole.ESTUDIANTE, email=email, code=f"98810{i}", full_name=f"Alumno Imp {i}",
            password_hash="x" * 20, must_change_password=False, semester=CYCLE,
        )
        for i, email in enumerate(STUDENTS, start=1)
    ]
    courses = [Course(code=code, name=f"Curso implícito {i}", cycle=CYCLE) for i, code in enumerate(CODES, start=1)]
    db_session.add_all([*rooms, *teachers, *students, *courses])
    await db_session.commit()
    for obj in (*rooms, *teachers, *students, *courses):
        await db_session.refresh(obj)
    yield SimpleNamespace(rooms=rooms, teachers=teachers, students=students, courses=courses)
    await _purge(db_session)


def _block(room: Room, weekday: int = 1, start: str = "08:00", end: str = "10:00", **extra) -> dict:
    return {"weekday": weekday, "start_time": start, "end_time": end, "room_id": room.id, **extra}


async def _groups(db, course: Course) -> list[CourseGroup]:
    rows = await db.exec(select(CourseGroup).where(CourseGroup.course_id == course.id).order_by(CourseGroup.group_code))
    return list(rows.all())


async def test_a_block_creates_the_initial_group_without_teacher(client, admin_headers, db_session, world):
    course = world.courses[0]

    r = await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))

    assert r.status_code == 201, r.text
    assert r.json()["group_code"] == "A" and r.json()["group_created"] is True and r.json()["teacher_id"] is None
    groups = await _groups(db_session, course)
    assert [(g.group_code, g.teacher_id, g.capacity) for g in groups] == [("A", None, 40)]

    again = await client.post(
        f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0], weekday=3)
    )
    assert again.status_code == 201 and again.json()["group_created"] is False
    assert len(await _groups(db_session, course)) == 1


async def test_the_teacher_is_optional_and_can_come_with_the_block(client, admin_headers, db_session, world):
    course = world.courses[0]

    r = await client.post(
        f"{API}/courses/{course.id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[0], teacher_id=world.teachers[0].id),
    )

    assert r.status_code == 201, r.text
    assert (await _groups(db_session, course))[0].teacher_id == world.teachers[0].id


async def test_a_failed_block_does_not_leave_an_empty_group(client, admin_headers, db_session, world):
    first, second = world.courses[0], world.courses[1]
    await client.post(f"{API}/courses/{first.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))

    clash = await client.post(f"{API}/courses/{second.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))

    assert clash.status_code == 409, clash.text
    assert await _groups(db_session, second) == []


async def test_with_several_groups_the_group_must_be_chosen(client, admin_headers, db_session, world):
    course = world.courses[0]
    await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))
    created = await client.post(f"{API}/courses/{course.id}/groups", headers=admin_headers, json={"group_code": "B"})
    assert created.status_code == 201, created.text
    assert created.json()["teacher_id"] is None
    group_b = created.json()["id"]

    ambiguous = await client.post(
        f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[1], weekday=2)
    )
    assert ambiguous.status_code == 422 and "varios grupos" in ambiguous.json()["detail"]

    chosen = await client.post(
        f"{API}/courses/{course.id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[1], weekday=2, group_id=group_b),
    )
    assert chosen.status_code == 201 and chosen.json()["group_code"] == "B"

    foreign = await client.post(
        f"{API}/courses/{world.courses[1].id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[1], weekday=4, group_id=group_b),
    )
    assert foreign.status_code == 404


async def test_the_teacher_can_be_assigned_and_removed_later(client, admin_headers, world):
    course = world.courses[0]
    block = await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))
    group_id = block.json()["group_id"]

    assigned = await client.patch(
        f"{API}/groups/{group_id}", headers=admin_headers, json={"teacher_id": world.teachers[0].id}
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["teacher_name"] == "Docente Imp 1"

    removed = await client.patch(f"{API}/groups/{group_id}", headers=admin_headers, json={"teacher_id": None})
    assert removed.json()["teacher_id"] is None


async def test_a_busy_teacher_cannot_be_assigned_to_an_overlapping_group(client, admin_headers, world):
    first, second = world.courses[0], world.courses[1]
    one = await client.post(
        f"{API}/courses/{first.id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[0], teacher_id=world.teachers[0].id),
    )
    two = await client.post(f"{API}/courses/{second.id}/blocks", headers=admin_headers, json=_block(world.rooms[1]))
    assert one.status_code == 201 and two.status_code == 201

    r = await client.patch(
        f"{API}/groups/{two.json()['group_id']}", headers=admin_headers, json={"teacher_id": world.teachers[0].id}
    )

    assert r.status_code == 409, r.text


async def test_capacity_cannot_drop_below_the_enrolled_students(client, admin_headers, db_session, world):
    course = world.courses[0]
    block = await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))
    group_id = block.json()["group_id"]
    db_session.add_all(Enrollment(student_id=s.id, group_id=group_id) for s in world.students)
    await db_session.commit()

    low = await client.patch(f"{API}/groups/{group_id}", headers=admin_headers, json={"capacity": 1})
    ok = await client.patch(f"{API}/groups/{group_id}", headers=admin_headers, json={"capacity": 2})

    assert low.status_code == 422 and ok.status_code == 200 and ok.json()["capacity"] == 2


async def test_full_courses_are_reported_until_another_group_has_room(client, admin_headers, db_session, world):
    course = world.courses[0]
    block = await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))
    group_id = block.json()["group_id"]
    await client.patch(f"{API}/groups/{group_id}", headers=admin_headers, json={"capacity": 2})
    db_session.add_all(Enrollment(student_id=s.id, group_id=group_id) for s in world.students)
    await db_session.commit()

    full = await client.get(f"{API}/courses/overflow", headers=admin_headers)
    assert course.code in {row["code"] for row in full.json()}
    summary = (await client.get(f"{API}/dashboard/summary", headers=admin_headers)).json()
    assert summary["cursos_llenos"] >= 1

    await client.post(f"{API}/courses/{course.id}/groups", headers=admin_headers, json={"group_code": "B"})
    after = await client.get(f"{API}/courses/overflow", headers=admin_headers)
    assert course.code not in {row["code"] for row in after.json()}


async def test_package_enrollment_creates_the_initial_group_only_for_letter_a(
    client, admin_headers, db_session, world
):
    refs = {"student_ids": [world.students[0].id], "cycle": CYCLE}

    b = await client.post(f"{API}/enrollment/package", headers=admin_headers, json={**refs, "group_code": "B"})
    assert b.status_code == 422
    for course in world.courses:
        assert await _groups(db_session, course) == []

    preview = await client.get(f"{API}/enrollment/package?cycle={CYCLE}&group_code=A", headers=admin_headers)
    mine = [row for row in preview.json()["missing"] if row["course_code"] in CODES]
    assert mine and all(row["will_create_group"] for row in mine)

    a = await client.post(f"{API}/enrollment/package", headers=admin_headers, json={**refs, "group_code": "A"})
    assert a.status_code == 200, a.text
    assert set(CODES) <= set(a.json()["created_groups"])
    settings = await db_session.get(AppSettings, 1)
    for course in world.courses:
        groups = await _groups(db_session, course)
        assert len(groups) == 1 and groups[0].semester_label == settings.semester_label


async def test_only_admins_manage_groups_and_course_blocks(client, docente_headers, world):
    course = world.courses[0]
    created = await client.post(
        f"{API}/courses/{course.id}/blocks", headers=docente_headers, json=_block(world.rooms[0])
    )
    assert created.status_code == 403
    assert (await client.patch(f"{API}/groups/1", headers=docente_headers, json={"capacity": 10})).status_code == 403
    assert (await client.get(f"{API}/courses/overflow", headers=docente_headers)).status_code == 403


async def test_new_group_flag_creates_the_next_parallel_group(client, admin_headers, db_session, world):
    course = world.courses[0]
    await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))

    parallel = await client.post(
        f"{API}/courses/{course.id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[1], new_group=True, teacher_id=world.teachers[0].id),
    )

    assert parallel.status_code == 201, parallel.text
    assert parallel.json()["group_code"] == "B" and parallel.json()["group_created"] is True
    groups = await _groups(db_session, course)
    assert [(g.group_code, g.teacher_id) for g in groups] == [("A", None), ("B", world.teachers[0].id)]


async def test_new_group_flag_with_a_clash_leaves_no_empty_group(client, admin_headers, db_session, world):
    course = world.courses[0]
    await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))

    clash = await client.post(
        f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0], new_group=True)
    )

    assert clash.status_code == 409, clash.text
    assert [g.group_code for g in await _groups(db_session, course)] == ["A"]


async def test_new_group_flag_and_group_id_are_mutually_exclusive(client, admin_headers, world):
    course = world.courses[0]
    first = await client.post(f"{API}/courses/{course.id}/blocks", headers=admin_headers, json=_block(world.rooms[0]))
    group_id = (await client.get(f"{API}/courses/{course.id}/groups", headers=admin_headers)).json()[0]["id"]
    assert first.status_code == 201

    both = await client.post(
        f"{API}/courses/{course.id}/blocks",
        headers=admin_headers,
        json=_block(world.rooms[1], new_group=True, group_id=group_id),
    )

    assert both.status_code in (400, 422), both.text
