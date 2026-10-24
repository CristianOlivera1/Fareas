from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip
from app.routers.enrollment_center import BlockInfo, BulkOut, MissingCourseOut, PairOut
from app.services.attendance_engine import ahora_peru
from app.services.enrollment_bulk import enroll_many, package_groups, window_state
from app.services.enrollments import matricular as enroll_one
from app.services.enrollments import retirar, transferir
from app.services.settings import get_settings_row, semestre_vigente
from app.tables import (
    AppUser,
    Course,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
    UserRole,
)

router = APIRouter(prefix="/me/enrollment", tags=["self-enrollment"])


class WindowOut(BaseModel):
    open: bool
    start: str | None
    end: str | None
    message: str


class EnrollmentStatusOut(BaseModel):
    period: str
    student_cycle: int | None
    window: WindowOut
    enrolled_groups: int


class OfferGroupOut(BaseModel):
    group_id: int
    course_id: int
    course_code: str
    course_name: str
    cycle: int
    group_code: str
    teacher_name: str | None
    capacity: int
    enrolled: int
    free: int
    full: bool
    blocks: list[BlockInfo]
    mine: bool
    current_group_code: str | None
    conflict: str | None


class GroupBody(BaseModel):
    group_id: int


class TransferBody(BaseModel):
    destino_group_id: int


class SelfPackageIn(BaseModel):
    cycle: int = Field(ge=1, le=10)
    group_code: str = Field(min_length=1, max_length=5)

    @field_validator("group_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


def _today() -> date:
    return ahora_peru().date()


async def _ensure_open(db) -> None:
    state = window_state(await get_settings_row(db), _today())
    if not state.open:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=state.message)


def _overlap(a: tuple[int, object, object], b: tuple[int, object, object]) -> bool:
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


@router.get("", response_model=EnrollmentStatusOut)
async def my_enrollment_status(db: DbSession, student: RequireRole(UserRole.ESTUDIANTE)) -> EnrollmentStatusOut:
    settings = await get_settings_row(db)
    state = window_state(settings, _today())
    period = settings.semester_label
    active = (
        await db.exec(
            select(Enrollment.id)
            .join(CourseGroup, CourseGroup.id == Enrollment.group_id)
            .where(
                Enrollment.student_id == student.id,
                Enrollment.withdrawn_at.is_(None),
                CourseGroup.is_active,
                CourseGroup.semester_label == period,
            )
        )
    ).all()
    return EnrollmentStatusOut(
        period=period,
        student_cycle=student.semester,
        window=WindowOut(
            open=state.open,
            start=str(state.start) if state.start else None,
            end=str(state.end) if state.end else None,
            message=state.message,
        ),
        enrolled_groups=len(active),
    )


@router.get("/offer", response_model=list[OfferGroupOut])
async def offer(
    db: DbSession,
    student: RequireRole(UserRole.ESTUDIANTE),
    cycle: int | None = Query(None, ge=1, le=10),
) -> list[OfferGroupOut]:
    period = await semestre_vigente(db)
    stmt = (
        select(CourseGroup, Course, AppUser)
        .join(Course, Course.id == CourseGroup.course_id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
        .where(CourseGroup.semester_label == period, CourseGroup.is_active)
        .order_by(Course.cycle, Course.code, CourseGroup.group_code)
    )
    if cycle is not None:
        stmt = stmt.where(Course.cycle == cycle)
    rows = (await db.exec(stmt)).all()

    mine_rows = (
        await db.exec(
            select(CourseGroup)
            .join(Enrollment, Enrollment.group_id == CourseGroup.id)
            .where(
                Enrollment.student_id == student.id,
                Enrollment.withdrawn_at.is_(None),
                CourseGroup.is_active,
                CourseGroup.semester_label == period,
            )
        )
    ).all()
    my_group_ids = {group.id for group in mine_rows}
    my_by_course = {group.course_id: group for group in mine_rows}

    all_group_ids = {group.id for group, _c, _t in rows} | my_group_ids
    blocks: dict[int, list[tuple[ScheduleBlock, Room | None]]] = {}
    counts: dict[int, int] = {}
    if all_group_ids:
        for block, room in (
            await db.exec(
                select(ScheduleBlock, Room)
                .outerjoin(Room, Room.id == ScheduleBlock.room_id)
                .where(ScheduleBlock.group_id.in_(all_group_ids))
                .order_by(ScheduleBlock.weekday, ScheduleBlock.start_time)
            )
        ).all():
            blocks.setdefault(block.group_id, []).append((block, room))
        for row in (
            await db.exec(
                select(Enrollment.group_id).where(
                    Enrollment.group_id.in_(all_group_ids), Enrollment.withdrawn_at.is_(None)
                )
            )
        ).all():
            group_id = row[0] if isinstance(row, tuple) else row
            counts[group_id] = counts.get(group_id, 0) + 1

    course_by_group = {group.id: course for group, course, _t in rows}
    my_course_codes: dict[int, str] = {}
    for group in mine_rows:
        course = course_by_group.get(group.id) or await db.get(Course, group.course_id)
        my_course_codes[group.id] = f"{course.code} (grupo {group.group_code})" if course else str(group.id)

    result: list[OfferGroupOut] = []
    for group, course, teacher in rows:
        enrolled = counts.get(group.id, 0)
        own_group = my_by_course.get(course.id)
        is_mine = group.id in my_group_ids
        conflict: str | None = None
        if not is_mine:
            candidate = [(b.weekday, b.start_time, b.end_time) for b, _r in blocks.get(group.id, [])]
            for other_id in my_group_ids:
                if own_group is not None and other_id == own_group.id:
                    continue
                for other in blocks.get(other_id, []):
                    mine_block = (other[0].weekday, other[0].start_time, other[0].end_time)
                    if any(_overlap(item, mine_block) for item in candidate):
                        conflict = my_course_codes.get(other_id)
                        break
                if conflict:
                    break
        result.append(
            OfferGroupOut(
                group_id=group.id, course_id=course.id, course_code=course.code, course_name=course.name,
                cycle=course.cycle, group_code=group.group_code,
                teacher_name=teacher.full_name if teacher is not None else None,
                capacity=group.capacity, enrolled=enrolled, free=max(0, group.capacity - enrolled),
                full=enrolled >= group.capacity,
                blocks=[
                    BlockInfo(
                        weekday=b.weekday,
                        start_time=b.start_time.isoformat(timespec="minutes"),
                        end_time=b.end_time.isoformat(timespec="minutes"),
                        room_code=r.code if r is not None else None,
                    )
                    for b, r in blocks.get(group.id, [])
                ],
                mine=is_mine,
                current_group_code=own_group.group_code if own_group is not None and not is_mine else None,
                conflict=conflict,
            )
        )
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def enroll_me(
    body: GroupBody, request: Request, db: DbSession, student: RequireRole(UserRole.ESTUDIANTE)
) -> dict:
    await _ensure_open(db)
    student_id = student.id
    await enroll_one(db, student, group_id=body.group_id, student_id=student_id, ip=_client_ip(request))
    return {"message": "Te matriculaste en el grupo"}


@router.delete("/{group_id}")
async def withdraw_me(
    group_id: int, request: Request, db: DbSession, student: RequireRole(UserRole.ESTUDIANTE)
) -> dict:
    await _ensure_open(db)
    result = await retirar(db, student, group_id=group_id, student_id=student.id, ip=_client_ip(request))
    return {"message": f"Matrícula {result['modo']}"}


@router.post("/{group_id}/transfer")
async def transfer_me(
    group_id: int,
    body: TransferBody,
    request: Request,
    db: DbSession,
    student: RequireRole(UserRole.ESTUDIANTE),
) -> dict:
    await _ensure_open(db)
    return await transferir(
        db, student, group_id=group_id, student_id=student.id,
        destino_group_id=body.destino_group_id, ip=_client_ip(request),
    )


@router.post("/package", response_model=BulkOut)
async def enroll_me_in_package(
    body: SelfPackageIn, request: Request, db: DbSession, student: RequireRole(UserRole.ESTUDIANTE)
) -> BulkOut:
    await _ensure_open(db)
    found, missing = await package_groups(db, body.cycle, body.group_code)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No hay grupos «{body.group_code}» en el ciclo {body.cycle} del periodo vigente",
        )
    groups_count = len(found)
    missing_out = [MissingCourseOut(course_id=c.id, course_code=c.code, course_name=c.name) for c in missing]
    results = await enroll_many(
        db, student, [student], [(item.group, item.course) for item in found], _client_ip(request)
    )
    return BulkOut(
        students=1,
        groups=groups_count,
        ok=sum(1 for r in results if r.status == "ok"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        failed=sum(1 for r in results if r.status == "failed"),
        unknown=[],
        missing=missing_out,
        results=[
            PairOut(
                student_id=r.student_id, student_code=r.student_code, student_name=r.student_name,
                group_id=r.group_id, course_code=r.course_code, group_code=r.group_code,
                status=r.status, reason=r.reason,
            )
            for r in results
        ],
    )
