from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip, _get_or_404
from app.routers.courses import BlockIn, BlockOut, GroupOut, _block_out, _group_out
from app.services import errors
from app.services.audit import audit
from app.services.course_groups import (
    count_active_enrollments,
    create_next_group,
    full_courses,
    resolve_group_for_course,
)
from app.services.schedule import _docente_valido, _raise_if_teacher_conflict, add_block
from app.services.settings import semestre_vigente
from app.tables import AppUser, Course, CourseGroup, UserRole

router = APIRouter(tags=["courses"])


class CourseBlockIn(BlockIn):
    group_id: int | None = Field(default=None, description="Solo si el curso tiene varios grupos")
    new_group: bool = Field(default=False, description="Crea el siguiente grupo del curso (B, C…)")


class CourseBlockOut(BlockOut):
    group_code: str
    group_created: bool


class GroupUpdate(BaseModel):
    teacher_id: int | None = Field(default=None, description="null quita al docente")
    capacity: int | None = Field(default=None, gt=0)


class FullCourseOut(BaseModel):
    course_id: int
    code: str
    name: str
    cycle: int
    groups: int
    enrolled: int
    capacity: int


@router.get("/courses/overflow", response_model=list[FullCourseOut])
async def overflow_courses(db: DbSession, _admin: RequireRole(UserRole.ADMIN)) -> list[FullCourseOut]:
    return [
        FullCourseOut(**{key: item[key] for key in FullCourseOut.model_fields})
        for item in await full_courses(db)
    ]


@router.post("/courses/{course_id}/blocks", response_model=CourseBlockOut, status_code=201)
async def create_course_block(
    course_id: int, body: CourseBlockIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> CourseBlockOut:
    course = await _get_or_404(db, Course, course_id, "Curso")
    if body.new_group and body.group_id is not None:
        raise errors.DomainError("Indica un grupo existente o pide uno nuevo, no ambos")
    if body.new_group:
        group = await create_next_group(db, course, await semestre_vigente(db))
        created = True
    else:
        group, created = await resolve_group_for_course(db, course, body.group_id)
    block = await add_block(
        db, admin, group_id=group.id, weekday=body.weekday, start_time=body.start_time,
        end_time=body.end_time, room_id=body.room_id, teacher_id=body.teacher_id,
        ip=_client_ip(request), commit=False,
    )
    if created:
        await audit(
            db, admin, action="grupo_creado", entity="course_group", entity_id=group.id,
            new_value={"course": course.code, "group": group.group_code, "implicito": True},
            ip_address=_client_ip(request),
        )
    await db.commit()
    base = await _block_out(db, block)
    return CourseBlockOut(**base.model_dump(), group_code=group.group_code, group_created=created)


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int, body: GroupUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> GroupOut:
    group = await _get_or_404(db, CourseGroup, group_id, "Grupo")
    course = await db.get(Course, group.course_id)
    data = body.model_dump(exclude_unset=True)
    old = {"teacher_id": group.teacher_id, "capacity": group.capacity}

    if "teacher_id" in data:
        new_teacher = data["teacher_id"]
        if new_teacher is not None and new_teacher != group.teacher_id:
            await _docente_valido(db, new_teacher)
            await _raise_if_teacher_conflict(db, group, new_teacher)
        group.teacher_id = new_teacher
    if data.get("capacity") is not None:
        enrolled = await count_active_enrollments(db, group.id)
        if data["capacity"] < enrolled:
            raise errors.DomainError(f"El grupo ya tiene {enrolled} alumnos matriculados; el cupo no puede ser menor")
        group.capacity = data["capacity"]

    db.add(group)
    await audit(
        db, admin, action="grupo_actualizado", entity="course_group", entity_id=group.id,
        old_value=old, new_value={"teacher_id": group.teacher_id, "capacity": group.capacity},
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(group)
    teacher = await db.get(AppUser, group.teacher_id) if group.teacher_id else None
    return await _group_out(db, group, course, teacher)
