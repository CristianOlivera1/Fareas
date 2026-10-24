from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.schedule import validar_reactivacion
from app.services.settings import semestre_vigente
from app.tables import Course, CourseGroup, Enrollment

DEFAULT_GROUP_CODE = "A"
DEFAULT_CAPACITY = 40


async def active_groups(
    db: SQLModelAsyncSession, course_id: int, period: str
) -> list[CourseGroup]:
    return list(
        (
            await db.exec(
                select(CourseGroup)
                .where(
                    CourseGroup.course_id == course_id,
                    CourseGroup.semester_label == period,
                    CourseGroup.is_active,
                )
                .order_by(CourseGroup.group_code)
            )
        ).all()
    )


async def ensure_default_group(
    db: SQLModelAsyncSession, course: Course, period: str
) -> tuple[CourseGroup, bool]:
    groups = await active_groups(db, course.id, period)
    if groups:
        return groups[0], False

    existing = (
        await db.exec(
            select(CourseGroup).where(
                CourseGroup.course_id == course.id,
                CourseGroup.semester_label == period,
                CourseGroup.group_code == DEFAULT_GROUP_CODE,
            )
        )
    ).first()
    if existing is not None:
        await validar_reactivacion(db, existing)
        existing.is_active = True
        db.add(existing)
        await db.flush()
        return existing, False

    group = CourseGroup(
        course_id=course.id,
        group_code=DEFAULT_GROUP_CODE,
        teacher_id=None,
        semester_label=period,
        capacity=DEFAULT_CAPACITY,
    )
    db.add(group)
    await db.flush()
    return group, True


async def resolve_group_for_course(
    db: SQLModelAsyncSession, course: Course, group_id: int | None
) -> tuple[CourseGroup, bool]:
    period = await semestre_vigente(db)
    if group_id is not None:
        group = await db.get(CourseGroup, group_id)
        if group is None or group.course_id != course.id or not group.is_active:
            raise errors.NotFoundError("El grupo indicado no pertenece a este curso")
        return group, False

    groups = await active_groups(db, course.id, period)
    if len(groups) > 1:
        letters = ", ".join(group.group_code for group in groups)
        raise errors.DomainError(
            f"El curso {course.code} tiene varios grupos ({letters}); indica a cuál va el horario"
        )
    return await ensure_default_group(db, course, period)


async def count_active_enrollments(db: SQLModelAsyncSession, group_id: int) -> int:
    return (
        await db.exec(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.group_id == group_id, Enrollment.withdrawn_at.is_(None))
        )
    ).one()


async def full_courses(db: SQLModelAsyncSession) -> list[dict]:
    period = await semestre_vigente(db)
    rows = (
        await db.exec(
            select(CourseGroup, Course)
            .join(Course, Course.id == CourseGroup.course_id)
            .where(CourseGroup.semester_label == period, CourseGroup.is_active)
            .order_by(Course.cycle, Course.code, CourseGroup.group_code)
        )
    ).all()
    counts: dict[int, int] = {}
    if rows:
        enrolled = (
            await db.exec(
                select(Enrollment.group_id).where(
                    Enrollment.group_id.in_([group.id for group, _course in rows]),
                    Enrollment.withdrawn_at.is_(None),
                )
            )
        ).all()
        for row in enrolled:
            group_id = row[0] if isinstance(row, tuple) else row
            counts[group_id] = counts.get(group_id, 0) + 1

    by_course: dict[int, dict] = {}
    for group, course in rows:
        entry = by_course.setdefault(
            course.id,
            {"course_id": course.id, "code": course.code, "name": course.name, "cycle": course.cycle,
             "groups": 0, "enrolled": 0, "capacity": 0, "all_full": True},
        )
        enrolled_count = counts.get(group.id, 0)
        entry["groups"] += 1
        entry["enrolled"] += enrolled_count
        entry["capacity"] += group.capacity
        if enrolled_count < group.capacity:
            entry["all_full"] = False
    return [entry for entry in by_course.values() if entry["all_full"]]
