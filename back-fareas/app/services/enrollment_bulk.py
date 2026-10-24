from dataclasses import dataclass
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
from app.services.course_groups import DEFAULT_GROUP_CODE, active_groups, ensure_default_group
from app.services.enrollments import matricular
from app.services.settings import get_settings_row, semestre_vigente
from app.tables import AppSettings, AppUser, Course, CourseGroup, Enrollment, UserRole

MAX_STUDENTS = 300
MAX_GROUPS = 20


@dataclass(slots=True)
class WindowState:
    open: bool
    start: date | None
    end: date | None
    message: str


@dataclass(slots=True)
class PairResult:
    student_id: int
    student_code: str | None
    student_name: str
    group_id: int
    course_code: str
    group_code: str
    status: str
    reason: str | None


@dataclass(slots=True)
class PackageGroup:
    course: Course
    group: CourseGroup | None
    enrolled: int


def window_state(settings: AppSettings, today: date) -> WindowState:
    start, end = settings.enrollment_start, settings.enrollment_end
    if start is None or end is None:
        return WindowState(False, start, end, "La matrícula no está habilitada; consulta con la administración.")
    if today < start:
        return WindowState(False, start, end, f"La matrícula abre el {start:%d/%m/%Y}.")
    if today > end:
        return WindowState(False, start, end, f"La matrícula cerró el {end:%d/%m/%Y}.")
    return WindowState(True, start, end, f"Matrícula abierta hasta el {end:%d/%m/%Y}.")


async def require_open_window(db: SQLModelAsyncSession, today: date) -> None:
    state = window_state(await get_settings_row(db), today)
    if not state.open:
        raise PermissionError(state.message)


async def resolve_students(
    db: SQLModelAsyncSession, ids: list[int], codes: list[str]
) -> tuple[list[AppUser], list[str]]:
    wanted_codes = list(dict.fromkeys(code.strip() for code in codes if code.strip()))
    found: dict[int, AppUser] = {}
    if ids:
        rows = (
            await db.exec(
                select(AppUser).where(
                    AppUser.id.in_(set(ids)), AppUser.role == UserRole.ESTUDIANTE, AppUser.is_active
                )
            )
        ).all()
        found.update({user.id: user for user in rows})
    unknown: list[str] = [f"#{student_id}" for student_id in dict.fromkeys(ids) if student_id not in found]
    if wanted_codes:
        rows = (
            await db.exec(
                select(AppUser).where(
                    AppUser.code.in_(wanted_codes), AppUser.role == UserRole.ESTUDIANTE, AppUser.is_active
                )
            )
        ).all()
        by_code = {user.code: user for user in rows}
        for code in wanted_codes:
            user = by_code.get(code)
            if user is None:
                unknown.append(code)
            else:
                found[user.id] = user
    ordered = sorted(found.values(), key=lambda user: (user.code or "", user.full_name))
    return ordered, unknown


async def package_groups(
    db: SQLModelAsyncSession, cycle: int, group_code: str
) -> tuple[list[PackageGroup], list[Course]]:
    period = await semestre_vigente(db)
    courses = (await db.exec(select(Course).where(Course.cycle == cycle).order_by(Course.code))).all()
    wanted = group_code.strip().upper()
    groups = (
        await db.exec(
            select(CourseGroup).where(
                CourseGroup.semester_label == period,
                CourseGroup.is_active,
                CourseGroup.course_id.in_([course.id for course in courses] or [0]),
            )
        )
    ).all()
    by_course = {group.course_id: group for group in groups if group.group_code.upper() == wanted}
    counts = await _active_counts(db, [group.id for group in by_course.values()])

    found: list[PackageGroup] = []
    missing: list[Course] = []
    for course in courses:
        group = by_course.get(course.id)
        if group is None:
            missing.append(course)
        else:
            found.append(PackageGroup(course, group, counts.get(group.id, 0)))
    return found, missing


async def _active_counts(db: SQLModelAsyncSession, group_ids: list[int]) -> dict[int, int]:
    if not group_ids:
        return {}
    rows = (
        await db.exec(
            select(Enrollment.group_id).where(
                Enrollment.group_id.in_(group_ids), Enrollment.withdrawn_at.is_(None)
            )
        )
    ).all()
    counts: dict[int, int] = {}
    for row in rows:
        group_id = row[0] if isinstance(row, tuple) else row
        counts[group_id] = counts.get(group_id, 0) + 1
    return counts


async def package_letters(db: SQLModelAsyncSession, cycle: int) -> list[dict]:
    period = await semestre_vigente(db)
    courses = (await db.exec(select(Course).where(Course.cycle == cycle))).all()
    groups = (
        await db.exec(
            select(CourseGroup).where(
                CourseGroup.semester_label == period,
                CourseGroup.is_active,
                CourseGroup.course_id.in_([course.id for course in courses] or [0]),
            )
        )
    ).all()
    covered: dict[str, set[int]] = {}
    for group in groups:
        covered.setdefault(group.group_code.upper(), set()).add(group.course_id)
    with_groups = {group.course_id for group in groups}
    without_groups = {course.id for course in courses} - with_groups
    if without_groups:
        covered.setdefault(DEFAULT_GROUP_CODE, set()).update(without_groups)
    return [
        {"group_code": letter, "courses_covered": len(ids), "courses_total": len(courses)}
        for letter, ids in sorted(covered.items())
    ]


async def enroll_courses_for_student(
    db: SQLModelAsyncSession,
    student: AppUser,
    items: list[tuple[int, int | None]],
    ip: str | None = None,
) -> list[dict]:
    student_id = student.id
    period = await semestre_vigente(db)
    results: list[dict] = []
    for course_id, group_id in items:
        course = await db.get(Course, course_id)
        base = {"course_id": course_id, "course_code": course.code if course else str(course_id)}
        if course is None:
            results.append({**base, "group_id": None, "group_code": None, "status": "failed", "reason": "El curso no existe"})
            continue
        base["course_code"] = course.code
        try:
            if group_id is not None:
                group = await db.get(CourseGroup, group_id)
                if group is None or group.course_id != course_id or not group.is_active or group.semester_label != period:
                    raise errors.NotFoundError("El grupo elegido no pertenece a este curso en el periodo vigente")
            else:
                groups = await active_groups(db, course_id, period)
                if len(groups) > 1:
                    raise errors.DomainError("Este curso tiene varios grupos: elige uno")
                group = groups[0] if groups else (await ensure_default_group(db, course, period))[0]
            group_info = (group.id, group.group_code)
            already = (
                await db.exec(
                    select(Enrollment).where(
                        Enrollment.student_id == student_id,
                        Enrollment.group_id == group.id,
                        Enrollment.withdrawn_at.is_(None),
                    )
                )
            ).first()
            if already is not None:
                results.append({**base, "group_id": group_info[0], "group_code": group_info[1], "status": "skipped", "reason": "Ya estabas matriculado"})
                continue
            await matricular(db, student, group_id=group.id, student_id=student_id, ip=ip)
            results.append({**base, "group_id": group_info[0], "group_code": group_info[1], "status": "ok", "reason": None})
        except errors.DomainError as exc:
            await db.rollback()
            student = await db.get(AppUser, student_id)
            results.append({**base, "group_id": group_id, "group_code": None, "status": "failed", "reason": str(exc)})
    return results


async def enroll_many(
    db: SQLModelAsyncSession,
    actor: AppUser,
    students: list[AppUser],
    groups: list[tuple[CourseGroup, Course]],
    ip: str | None = None,
) -> list[PairResult]:
    actor_id = actor.id
    student_info = [(s.id, s.code, s.full_name) for s in students]
    group_info = [(g.id, c.code, g.group_code) for g, c in groups]
    group_ids = [group_id for group_id, _code, _letter in group_info]

    active = {
        (row.student_id, row.group_id)
        for row in (
            await db.exec(
                select(Enrollment).where(
                    Enrollment.student_id.in_([info[0] for info in student_info] or [0]),
                    Enrollment.group_id.in_(group_ids or [0]),
                    Enrollment.withdrawn_at.is_(None),
                )
            )
        ).all()
    }

    results: list[PairResult] = []
    for student_id, student_code, student_name in student_info:
        for group_id, course_code, letter in group_info:
            base = (student_id, student_code, student_name, group_id, course_code, letter)
            if (student_id, group_id) in active:
                results.append(PairResult(*base, "skipped", "Ya estaba matriculado"))
                continue
            try:
                await matricular(db, actor, group_id=group_id, student_id=student_id, ip=ip)
                results.append(PairResult(*base, "ok", None))
            except errors.DomainError as exc:
                await db.rollback()
                actor = await db.get(AppUser, actor_id)
                results.append(PairResult(*base, "failed", str(exc)))
    return results


async def courses_without_groups(db: SQLModelAsyncSession, cycle: int) -> list[Course]:
    period = await semestre_vigente(db)
    courses = (await db.exec(select(Course).where(Course.cycle == cycle).order_by(Course.code))).all()
    return [course for course in courses if not await active_groups(db, course.id, period)]


async def create_missing_default_groups(db: SQLModelAsyncSession, cycle: int) -> list[str]:
    period = await semestre_vigente(db)
    created: list[str] = []
    for course in await courses_without_groups(db, cycle):
        _group, was_created = await ensure_default_group(db, course, period)
        created.append(course.code)
        _ = was_created
    if created:
        await db.commit()
    return created


def is_default_letter(group_code: str) -> bool:
    return group_code.strip().upper() == DEFAULT_GROUP_CODE
