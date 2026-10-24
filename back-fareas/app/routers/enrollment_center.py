from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip
from app.services.audit import audit
from app.services.enrollment_bulk import (
    MAX_GROUPS,
    MAX_STUDENTS,
    PairResult,
    courses_without_groups,
    create_missing_default_groups,
    enroll_many,
    is_default_letter,
    package_groups,
    package_letters,
    resolve_students,
)
from app.tables import AppUser, Course, CourseGroup, UserRole

router = APIRouter(prefix="/enrollment", tags=["enrollment-center"])


class BlockInfo(BaseModel):
    weekday: int
    start_time: str
    end_time: str
    room_code: str | None


class PackageCourseOut(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    group_id: int | None
    group_code: str
    teacher_name: str | None
    capacity: int
    enrolled: int
    free: int
    blocks: list[BlockInfo]


class MissingCourseOut(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    will_create_group: bool = False


class PackageOut(BaseModel):
    period: str
    cycle: int
    group_code: str
    courses: list[PackageCourseOut]
    missing: list[MissingCourseOut]


class LetterOut(BaseModel):
    group_code: str
    courses_covered: int
    courses_total: int


class StudentRefIn(BaseModel):
    student_ids: list[int] = Field(default_factory=list, max_length=MAX_STUDENTS)
    student_codes: list[str] = Field(default_factory=list, max_length=MAX_STUDENTS)


class BulkIn(StudentRefIn):
    group_ids: list[int] = Field(min_length=1, max_length=MAX_GROUPS)


class PackageIn(StudentRefIn):
    cycle: int = Field(ge=1, le=10)
    group_code: str = Field(min_length=1, max_length=5)

    @field_validator("group_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


class ResolveIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=MAX_STUDENTS)


class ResolvedStudentOut(BaseModel):
    id: int
    code: str | None
    full_name: str
    semester: int | None


class ResolveOut(BaseModel):
    found: list[ResolvedStudentOut]
    unknown: list[str]


class PairOut(BaseModel):
    student_id: int
    student_code: str | None
    student_name: str
    group_id: int
    course_code: str
    group_code: str
    status: str
    reason: str | None


class BulkOut(BaseModel):
    students: int
    groups: int
    ok: int
    skipped: int
    failed: int
    unknown: list[str]
    missing: list[MissingCourseOut]
    created_groups: list[str] = Field(default_factory=list)
    results: list[PairOut]


def _pair_out(result: PairResult) -> PairOut:
    return PairOut(
        student_id=result.student_id, student_code=result.student_code, student_name=result.student_name,
        group_id=result.group_id, course_code=result.course_code, group_code=result.group_code,
        status=result.status, reason=result.reason,
    )


async def build_package_out(db, cycle: int, group_code: str) -> PackageOut:
    from app.services.settings import semestre_vigente
    from app.tables import AppUser, Room, ScheduleBlock

    found, missing = await package_groups(db, cycle, group_code)
    without_groups = {course.id for course in await courses_without_groups(db, cycle)}
    group_ids = [item.group.id for item in found]
    blocks_by_group: dict[int, list[BlockInfo]] = {}
    teachers: dict[int, str] = {}
    if group_ids:
        rows = (
            await db.exec(
                select(ScheduleBlock, Room)
                .outerjoin(Room, Room.id == ScheduleBlock.room_id)
                .where(ScheduleBlock.group_id.in_(group_ids))
                .order_by(ScheduleBlock.weekday, ScheduleBlock.start_time)
            )
        ).all()
        for block, room in rows:
            blocks_by_group.setdefault(block.group_id, []).append(
                BlockInfo(
                    weekday=block.weekday,
                    start_time=block.start_time.isoformat(timespec="minutes"),
                    end_time=block.end_time.isoformat(timespec="minutes"),
                    room_code=room.code if room is not None else None,
                )
            )
        teacher_ids = {item.group.teacher_id for item in found if item.group.teacher_id}
        if teacher_ids:
            people = (await db.exec(select(AppUser).where(AppUser.id.in_(teacher_ids)))).all()
            teachers = {person.id: person.full_name for person in people}

    return PackageOut(
        period=await semestre_vigente(db),
        cycle=cycle,
        group_code=group_code,
        courses=[
            PackageCourseOut(
                course_id=item.course.id, course_code=item.course.code, course_name=item.course.name,
                group_id=item.group.id, group_code=item.group.group_code,
                teacher_name=teachers.get(item.group.teacher_id),
                capacity=item.group.capacity, enrolled=item.enrolled,
                free=max(0, item.group.capacity - item.enrolled),
                blocks=blocks_by_group.get(item.group.id, []),
            )
            for item in found
        ],
        missing=[
            MissingCourseOut(
                course_id=course.id, course_code=course.code, course_name=course.name,
                will_create_group=is_default_letter(group_code) and course.id in without_groups,
            )
            for course in missing
        ],
    )


@router.get("/package-letters", response_model=list[LetterOut])
async def letters(
    db: DbSession, _admin: RequireRole(UserRole.ADMIN), cycle: int = Query(ge=1, le=10)
) -> list[LetterOut]:
    return [LetterOut(**item) for item in await package_letters(db, cycle)]


@router.get("/package", response_model=PackageOut)
async def package_preview(
    db: DbSession,
    _admin: RequireRole(UserRole.ADMIN),
    cycle: int = Query(ge=1, le=10),
    group_code: str = Query(min_length=1, max_length=5),
) -> PackageOut:
    return await build_package_out(db, cycle, group_code.strip().upper())


@router.post("/resolve-students", response_model=ResolveOut)
async def resolve(body: ResolveIn, db: DbSession, _admin: RequireRole(UserRole.ADMIN)) -> ResolveOut:
    students, unknown = await resolve_students(db, [], body.codes)
    return ResolveOut(
        found=[
            ResolvedStudentOut(id=s.id, code=s.code, full_name=s.full_name, semester=s.semester)
            for s in students
        ],
        unknown=unknown,
    )


async def _run(
    db, admin, request: Request, body: StudentRefIn, groups, missing, action: str, detail: dict,
    created_groups: list[str] | None = None,
) -> BulkOut:
    students, unknown = await resolve_students(db, body.student_ids, body.student_codes)
    if not students:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se encontró ningún estudiante activo para matricular"
            + (f" (no encontrados: {', '.join(unknown[:10])})" if unknown else ""),
        )
    ip = _client_ip(request)
    admin_id = admin.id
    results = await enroll_many(db, admin, students, groups, ip)
    admin = await db.get(AppUser, admin_id)
    summary = {
        "ok": sum(1 for r in results if r.status == "ok"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "failed": sum(1 for r in results if r.status == "failed"),
    }
    await audit(
        db, admin, action=action, entity="enrollment",
        new_value={**detail, **summary, "estudiantes": len(students), "grupos": len(groups)},
        ip_address=ip,
    )
    await db.commit()
    return BulkOut(
        students=len(students), groups=len(groups), unknown=unknown, missing=missing,
        created_groups=created_groups or [],
        results=[_pair_out(r) for r in results], **summary,
    )


@router.post("/bulk", response_model=BulkOut)
async def bulk_enroll(body: BulkIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)) -> BulkOut:
    rows = (
        await db.exec(
            select(CourseGroup, Course)
            .join(Course, Course.id == CourseGroup.course_id)
            .where(CourseGroup.id.in_(set(body.group_ids)))
        )
    ).all()
    if len(rows) != len(set(body.group_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alguno de los grupos no existe")
    return await _run(db, admin, request, body, [(g, c) for g, c in rows], [], "matricula_masiva",
                      {"group_ids": sorted(set(body.group_ids))})


@router.post("/package", response_model=BulkOut)
async def package_enroll(body: PackageIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)) -> BulkOut:
    created = await create_missing_default_groups(db, body.cycle) if is_default_letter(body.group_code) else []
    found, missing = await package_groups(db, body.cycle, body.group_code)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No hay grupos «{body.group_code}» en el ciclo {body.cycle} del periodo vigente",
        )
    return await _run(
        db, admin, request, body, [(item.group, item.course) for item in found],
        [MissingCourseOut(course_id=c.id, course_code=c.code, course_name=c.name) for c in missing],
        "matricula_por_ciclo", {"cycle": body.cycle, "group_code": body.group_code},
        created_groups=created,
    )
