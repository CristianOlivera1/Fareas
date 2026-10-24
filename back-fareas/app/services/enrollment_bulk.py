from dataclasses import dataclass
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.services import errors
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
    return [
        {"group_code": letter, "courses_covered": len(ids), "courses_total": len(courses)}
        for letter, ids in sorted(covered.items())
    ]


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
