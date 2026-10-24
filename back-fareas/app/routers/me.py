from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.courses import ScheduleRowOut
from app.services.settings import semestre_vigente
from app.services.storage import get_storage
from app.tables import (
    AppUser,
    Course,
    CourseGroup,
    Enrollment,
    Justification,
    Room,
    ScheduleBlock,
    UserRole,
)

router = APIRouter(prefix="/me", tags=["student-portal"])


class MyJustificationOut(BaseModel):
    id: int
    course_code: str | None
    start_date: date
    end_date: date
    reason: str
    document_url: str | None
    created_by_name: str


@router.get("/schedule", response_model=list[ScheduleRowOut])
async def my_schedule(
    db: DbSession,
    student: RequireRole(UserRole.ESTUDIANTE),
    semester: str | None = Query(None, max_length=40, description="Default: periodo vigente"),
) -> list[ScheduleRowOut]:
    semester = semester or await semestre_vigente(db)
    stmt = (
        select(ScheduleBlock, CourseGroup, Course, AppUser, Room)
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
        .join(Course, Course.id == CourseGroup.course_id)
        .join(Enrollment, Enrollment.group_id == CourseGroup.id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
        .outerjoin(Room, Room.id == ScheduleBlock.room_id)
        .where(
            Enrollment.student_id == student.id,
            Enrollment.withdrawn_at.is_(None),
            CourseGroup.is_active,
            CourseGroup.semester_label == semester,
        )
        .order_by(ScheduleBlock.weekday, ScheduleBlock.start_time, Course.code)
    )
    rows = (await db.exec(stmt)).all()
    return [
        ScheduleRowOut(
            id=b.id,
            group_id=g.id,
            course_id=c.id,
            course_code=c.code,
            course_name=c.name,
            group_code=g.group_code,
            teacher_id=t.id if t is not None else None,
            teacher_name=t.full_name if t is not None else None,
            room_id=r.id if r is not None else None,
            room_code=r.code if r is not None else None,
            semester_label=g.semester_label,
            cycle=c.cycle,
            weekday=b.weekday,
            start_time=b.start_time,
            end_time=b.end_time,
        )
        for b, g, c, t, r in rows
    ]


@router.get("/justifications", response_model=list[MyJustificationOut])
async def my_justifications(
    db: DbSession,
    student: RequireRole(UserRole.ESTUDIANTE),
) -> list[MyJustificationOut]:
    rows = (
        await db.exec(
            select(Justification, Course, AppUser)
            .outerjoin(Course, Course.id == Justification.course_id)
            .join(AppUser, AppUser.id == Justification.created_by)
            .where(Justification.student_id == student.id)
            .order_by(
                Justification.created_at.desc().nullslast(),
                Justification.id.desc(),
            )
        )
    ).all()
    storage = get_storage()
    return [
        MyJustificationOut(
            id=j.id,
            course_code=course.code if course is not None else None,
            start_date=j.start_date,
            end_date=j.end_date,
            reason=j.reason,
            document_url=await storage.url(j.document_key) if j.document_key else j.document_url,
            created_by_name=creator.full_name,
        )
        for j, course, creator in rows
    ]
