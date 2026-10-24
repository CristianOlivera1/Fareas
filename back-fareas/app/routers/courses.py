import asyncio
from datetime import time
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from app.core.deps import DbSession, RequireRole
from app.core.pagination import PageParamsDep
from app.routers.catalog import _client_ip, _get_or_404
from app.schemas.common import Page
from app.services import errors
from app.services.audit import audit
from app.services.avatars import avatar_url
from app.services.enrollments import matricular, retirar, transferir
from app.services.import_matching import (
    Coincidencia,
    emparejar_aula,
    emparejar_docente,
    sugerir_curso,
)
from app.services.ocr_extract import MAX_PESO_ARCHIVO, leer_documento_async
from app.services.ocr_schedule import BloqueExtraido, extraer_horarios_documento
from app.services.schedule import add_block, update_block, validar_reactivacion
from app.services.settings import semestre_vigente
from app.tables import (
    AppUser,
    AttendanceSession,
    Course,
    CourseGroup,
    Enrollment,
    Room,
    ScheduleBlock,
    UserRole,
)

router = APIRouter(tags=["courses"])


class CourseIn(BaseModel):
    code: str = Field(min_length=3, max_length=20, examples=["ISA903"])
    name: str = Field(min_length=3, max_length=160, examples=["Inteligencia Artificial I"])
    cycle: int = Field(ge=1, le=10, description="Ciclo de la malla (1-10)")

class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=3, max_length=20, examples=["ISA903"])
    name: str | None = Field(default=None, min_length=3, max_length=160,
                             examples=["Inteligencia Artificial I"])
    cycle: int | None = Field(default=None, ge=1, le=10, description="Ciclo de la malla (1-10)")

class CourseOut(BaseModel):
    id: int
    code: str
    name: str
    cycle: int

@router.get("/courses", response_model=Page[CourseOut])
async def list_courses(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    q: str | None = Query(None, max_length=80, description="Filtra por código o nombre"),
    cycle: int | None = Query(None, ge=1, le=10, description="Filtra por ciclo (1-10)"),
) -> Page[CourseOut]:
    stmt = select(Course)
    count_stmt = select(func.count()).select_from(Course)
    if q:
        like = f"%{q}%"
        cond = Course.code.ilike(like) | Course.name.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if cycle is not None:
        stmt = stmt.where(Course.cycle == cycle)
        count_stmt = count_stmt.where(Course.cycle == cycle)
    total = (await db.exec(count_stmt)).one()
    courses = (
        await db.exec(
            stmt.order_by(Course.created_at.desc().nullslast(), Course.id.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
    ).all()
    return Page(
        items=[CourseOut(id=c.id, code=c.code, name=c.name, cycle=c.cycle) for c in courses],
        total=total, page=page.page, page_size=page.page_size,
    )

@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(body: CourseIn, db: DbSession, _admin: RequireRole(UserRole.ADMIN)) -> CourseOut:
    code = body.code.strip().upper()
    name = body.name.strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El código del curso no puede quedar vacío")
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El nombre del curso no puede quedar vacío")
    if (await db.exec(select(Course).where(Course.code == code))).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El curso '{code}' ya existe")
    course = Course(code=code, name=name, cycle=body.cycle)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return CourseOut(id=course.id, code=course.code, name=course.name, cycle=course.cycle)

@router.patch("/courses/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: int, body: CourseUpdate, request: Request, db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> CourseOut:
    course = await _get_or_404(db, Course, course_id, "Curso")
    old = {"code": course.code, "name": course.name, "cycle": course.cycle}
    data = body.model_dump(exclude_unset=True)

    if data.get("code") is not None:
        code = data["code"].strip().upper()
        if not code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="El código del curso no puede quedar vacío")
        if code != course.code and (
            await db.exec(select(Course).where(Course.code == code))
        ).first() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"El curso '{code}' ya existe")
        course.code = code

    if data.get("name") is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="El nombre del curso no puede quedar vacío")
        course.name = name

    if data.get("cycle") is not None:
        course.cycle = data["cycle"]

    new = {"code": course.code, "name": course.name, "cycle": course.cycle}
    if new != old:
        db.add(course)
        await audit(db, admin, action="curso_actualizado", entity="course", entity_id=course.id,
                    old_value=old, new_value=new, ip_address=_client_ip(request))
        await db.commit()
        await db.refresh(course)

    return CourseOut(id=course.id, code=course.code, name=course.name, cycle=course.cycle)

@router.delete("/courses/{course_id}", response_model=dict)
async def delete_course(
    course_id: int, request: Request, db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    course = await _get_or_404(db, Course, course_id, "Curso")
    groups = (
        await db.exec(
            select(func.count()).select_from(CourseGroup)
            .where(CourseGroup.course_id == course_id)
        )
    ).one()
    if groups:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"El curso '{course.code}' tiene {groups} grupo(s) asociado(s) y no se "
                    "puede eliminar: conserva el historial académico. Desactiva los grupos "
                    "si ya no se dictan."),
        )
    old = {"code": course.code, "name": course.name, "cycle": course.cycle}
    await db.delete(course)
    await audit(db, admin, action="curso_eliminado", entity="course", entity_id=course_id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Curso '{old['code']}' eliminado"}

class GroupIn(BaseModel):
    group_code: str = Field(min_length=1, max_length=5, examples=["A"])
    teacher_id: int | None = Field(default=None, description="Docente del grupo; se puede asignar después")
    capacity: int = Field(default=40, gt=0, description="Cupo del grupo (40 por defecto, R8)")

class GroupOut(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_name: str
    group_code: str
    teacher_id: int | None
    teacher_name: str | None
    semester_label: str
    cycle: int
    capacity: int
    enrolled_count: int
    is_active: bool

async def _group_out(db, g: CourseGroup, course: Course, teacher: AppUser | None) -> GroupOut:
    activos = (
        await db.exec(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.group_id == g.id, Enrollment.withdrawn_at.is_(None))
        )
    ).one()
    return GroupOut(
        id=g.id,
        course_id=course.id,
        course_code=course.code,
        course_name=course.name,
        group_code=g.group_code,
        teacher_id=teacher.id if teacher is not None else None,
        teacher_name=teacher.full_name if teacher is not None else None,
        semester_label=g.semester_label,
        cycle=course.cycle,
        capacity=g.capacity,
        enrolled_count=activos,
        is_active=g.is_active,
    )

async def _group_rows(db, *, group_id: int | None = None, course_id: int | None = None,
                      teacher_id: int | None = None, active_only: bool = False,
                      semester: str | None = None, cycle: int | None = None):
    stmt = (
        select(CourseGroup, Course, AppUser)
        .join(Course, Course.id == CourseGroup.course_id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
    )
    if group_id is not None:
        stmt = stmt.where(CourseGroup.id == group_id)
    if course_id is not None:
        stmt = stmt.where(CourseGroup.course_id == course_id)
    if teacher_id is not None:
        stmt = stmt.where(CourseGroup.teacher_id == teacher_id)
    if active_only:
        stmt = stmt.where(CourseGroup.is_active)
    if semester is not None:
        stmt = stmt.where(CourseGroup.semester_label == semester)
    if cycle is not None:
        stmt = stmt.where(Course.cycle == cycle)
    return (await db.exec(stmt.order_by(Course.cycle, Course.code, CourseGroup.group_code))).all()

@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = None,
    teacher_id: int | None = None,
    include_inactive: bool = False,
    semester: str | None = Query(None, max_length=40, description="Default: todos"),
    cycle: int | None = Query(None, ge=1, le=10, description="Filtra por ciclo (1-10)"),
) -> list[GroupOut]:
    rows = await _group_rows(db, course_id=course_id, teacher_id=teacher_id,
                             active_only=not include_inactive, semester=semester, cycle=cycle)
    return [await _group_out(db, g, c, t) for g, c, t in rows]

@router.get("/courses/{course_id}/groups", response_model=list[GroupOut])
async def list_course_groups(
    course_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    semester: str | None = Query(None, max_length=40, description="Default: semestre vigente (R1)"),
) -> list[GroupOut]:
    await _get_or_404(db, Course, course_id, "Curso")
    if semester is None:
        semester = await semestre_vigente(db)
    rows = await _group_rows(db, course_id=course_id, semester=semester)
    return [await _group_out(db, g, c, t) for g, c, t in rows]

@router.post("/courses/{course_id}/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    course_id: int, body: GroupIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> GroupOut:
    course = await _get_or_404(db, Course, course_id, "Curso")
    group_code = body.group_code.strip().upper()
    semester = await semestre_vigente(db)
    if (await db.exec(
        select(CourseGroup).where(
            CourseGroup.course_id == course_id,
            CourseGroup.group_code == group_code,
            CourseGroup.semester_label == semester,
        )
    )).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El curso {course.code} ya tiene un grupo '{group_code}' en {semester}",
        )
    teacher = None
    if body.teacher_id is not None:
        teacher = await _get_or_404(db, AppUser, body.teacher_id, "Docente")
        if teacher.role is not UserRole.DOCENTE or not teacher.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="El usuario asignado debe ser un docente activo")

    group = CourseGroup(course_id=course_id, group_code=group_code,
                        teacher_id=body.teacher_id,
                        semester_label=semester, capacity=body.capacity)
    db.add(group)
    await db.flush()
    await audit(db, admin, action="grupo_creado", entity="course_group", entity_id=group.id,
                new_value={"course": course.code, "group": group_code, "semester": semester,
                           "teacher_id": body.teacher_id, "capacity": body.capacity},
                ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(group)
    return await _group_out(db, group, course, teacher)

@router.delete("/groups/{group_id}", response_model=dict)
async def deactivate_group(
    group_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    group = await _get_or_404(db, CourseGroup, group_id, "Grupo")
    if not group.is_active:
        raise errors.DomainError("El grupo ya está inactivo")
    group.is_active = False
    db.add(group)
    await audit(db, admin, action="grupo_desactivado", entity="course_group", entity_id=group.id,
                ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Grupo #{group_id} desactivado"}

@router.post("/groups/{group_id}/activate", response_model=dict)
async def activate_group(
    group_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    group = await _get_or_404(db, CourseGroup, group_id, "Grupo")
    if group.is_active:
        raise errors.DomainError("El grupo ya está activo")
    await validar_reactivacion(db, group)
    group.is_active = True
    db.add(group)
    await audit(db, admin, action="grupo_reactivado", entity="course_group", entity_id=group.id,
                ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Grupo #{group_id} reactivado"}

class BlockIn(BaseModel):
    weekday: int = Field(ge=1, le=5, description="1=Lunes … 5=Viernes")
    start_time: time
    end_time: time
    room_id: int | None = Field(default=None, description="Aula donde se dicta ESTE bloque (R9)")
    teacher_id: int | None = Field(default=None, description="Docente del grupo (opcional)")

class BlockUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=5)
    start_time: time | None = None
    end_time: time | None = None
    room_id: int | None = None
    teacher_id: int | None = None

class BlockOut(BaseModel):
    id: int
    group_id: int
    room_id: int | None
    room_code: str | None
    teacher_id: int | None
    teacher_name: str | None
    weekday: int
    start_time: time
    end_time: time

async def _block_out(db, b: ScheduleBlock) -> BlockOut:
    room = await db.get(Room, b.room_id) if b.room_id is not None else None
    group = await db.get(CourseGroup, b.group_id)
    teacher = await db.get(AppUser, group.teacher_id) if group and group.teacher_id else None
    return BlockOut(
        id=b.id, group_id=b.group_id,
        room_id=room.id if room is not None else None,
        room_code=room.code if room is not None else None,
        teacher_id=teacher.id if teacher is not None else None,
        teacher_name=teacher.full_name if teacher is not None else None,
        weekday=b.weekday, start_time=b.start_time, end_time=b.end_time,
    )

@router.get("/groups/{group_id}/blocks", response_model=list[BlockOut])
async def list_blocks(
    group_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> list[BlockOut]:
    await _get_or_404(db, CourseGroup, group_id, "Grupo")
    blocks = (
        await db.exec(
            select(ScheduleBlock)
            .where(ScheduleBlock.group_id == group_id)
            .order_by(ScheduleBlock.weekday, ScheduleBlock.start_time)
        )
    ).all()
    return [await _block_out(db, b) for b in blocks]

@router.post("/groups/{group_id}/blocks", response_model=BlockOut, status_code=status.HTTP_201_CREATED)
async def create_block(
    group_id: int, body: BlockIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> BlockOut:
    block = await add_block(
        db, admin, group_id=group_id, weekday=body.weekday,
        start_time=body.start_time, end_time=body.end_time, room_id=body.room_id,
        teacher_id=body.teacher_id, ip=_client_ip(request),
    )
    return await _block_out(db, block)

@router.patch("/blocks/{block_id}", response_model=BlockOut)
async def patch_block(
    block_id: int, body: BlockUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> BlockOut:
    block = await update_block(db, admin, block_id=block_id,
                               data=body.model_dump(exclude_unset=True), ip=_client_ip(request))
    return await _block_out(db, block)

@router.delete("/blocks/{block_id}", response_model=dict)
async def delete_block(
    block_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    block = await _get_or_404(db, ScheduleBlock, block_id, "Bloque horario")
    session_id = (
        await db.exec(
            select(AttendanceSession.id)
            .where(AttendanceSession.block_id == block_id)
            .limit(1)
        )
    ).first()
    if session_id is not None:
        raise errors.ConflictError(
            "No se puede eliminar un bloque con sesiones de asistencia registradas"
        )

    old = {"group_id": block.group_id, "room_id": block.room_id, "weekday": block.weekday,
           "start_time": str(block.start_time), "end_time": str(block.end_time)}
    await db.delete(block)
    await audit(db, admin, action="bloque_eliminado", entity="schedule_block", entity_id=block_id,
                old_value=old, ip_address=_client_ip(request))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23503":
            raise errors.ConflictError(
                "No se puede eliminar un bloque con sesiones de asistencia registradas"
            ) from exc
        raise
    return {"message": f"Bloque #{block_id} eliminado"}

class ScheduleRowOut(BaseModel):
    id: int
    group_id: int
    course_id: int
    course_code: str
    course_name: str
    group_code: str
    teacher_id: int | None
    teacher_name: str | None
    room_id: int | None
    room_code: str | None
    semester_label: str
    cycle: int
    weekday: int
    start_time: time
    end_time: time

@router.get("/schedule", response_model=list[ScheduleRowOut])
async def general_schedule(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    semester: str | None = Query(None, max_length=40, description="Default: semestre vigente (R1)"),
    cycle: int | None = Query(None, ge=1, le=10, description="Filtra por ciclo (1-10)"),
    course_id: int | None = None,
    teacher_id: int | None = None,
    room_id: int | None = None,
    include_inactive: bool = Query(False, description="Incluye grupos desactivados"),
) -> list[ScheduleRowOut]:
    if semester is None:
        semester = await semestre_vigente(db)
    stmt = (
        select(ScheduleBlock, CourseGroup, Course, AppUser, Room)
        .join(CourseGroup, CourseGroup.id == ScheduleBlock.group_id)
        .join(Course, Course.id == CourseGroup.course_id)
        .outerjoin(AppUser, AppUser.id == CourseGroup.teacher_id)
        .outerjoin(Room, Room.id == ScheduleBlock.room_id)
        .where(CourseGroup.semester_label == semester)
        .order_by(Course.cycle, ScheduleBlock.weekday, ScheduleBlock.start_time, Course.code)
    )
    if not include_inactive:
        stmt = stmt.where(CourseGroup.is_active)
    if cycle is not None:
        stmt = stmt.where(Course.cycle == cycle)
    if course_id is not None:
        stmt = stmt.where(CourseGroup.course_id == course_id)
    if teacher_id is not None:
        stmt = stmt.where(CourseGroup.teacher_id == teacher_id)
    if room_id is not None:
        stmt = stmt.where(ScheduleBlock.room_id == room_id)
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

class EnrollIn(BaseModel):
    student_id: int

class EnrolledStudentOut(BaseModel):
    id: int
    code: str | None
    full_name: str
    email: str
    semester: int | None
    enrolled_at: str | None
    withdrawn_at: str | None = None
    has_face: bool | None = None
    avatar_url: str | None = None

@router.get("/groups/{group_id}/students", response_model=list[EnrolledStudentOut])
async def list_enrolled(
    group_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    with_face: bool = Query(False, description="Incluye has_face (rostro vigente RF-04)"),
) -> list[EnrolledStudentOut]:
    await _get_or_404(db, CourseGroup, group_id, "Grupo")
    rows = (
        await db.exec(
            select(AppUser, Enrollment.enrolled_at, Enrollment.withdrawn_at)
            .join(Enrollment, Enrollment.student_id == AppUser.id)
            .where(Enrollment.group_id == group_id)
            .order_by(
                Enrollment.withdrawn_at.is_(None).desc(),
                func.coalesce(Enrollment.withdrawn_at, Enrollment.enrolled_at)
                .desc()
                .nullslast(),
                Enrollment.id.desc(),
            )
        )
    ).all()
    con_rostro: set[int] = set()
    if with_face and rows:
        from app.tables import FaceEmbedding

        ids = [u.id for u, _e, _w in rows]
        filas = (
            await db.exec(
                select(FaceEmbedding.student_id).where(
                    FaceEmbedding.student_id.in_(ids),
                    FaceEmbedding.is_current,
                )
            )
        ).all()
        con_rostro = {r[0] if isinstance(r, tuple) else r for r in filas}
    avatar_urls = await asyncio.gather(*(avatar_url(user.avatar_key) for user, _, _ in rows))
    return [
        EnrolledStudentOut(
            id=u.id, code=u.code, full_name=u.full_name, email=u.email, semester=u.semester,
            enrolled_at=ea.isoformat(timespec="seconds") if ea else None,
            withdrawn_at=w.isoformat(timespec="seconds") if w else None,
            has_face=(u.id in con_rostro) if with_face else None,
            avatar_url=photo_url,
        )
        for (u, ea, w), photo_url in zip(rows, avatar_urls, strict=True)
    ]

@router.post("/groups/{group_id}/students", status_code=status.HTTP_201_CREATED)
async def enroll_student(
    group_id: int, body: EnrollIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    enrollment = await matricular(
        db, admin, group_id=group_id, student_id=body.student_id, ip=_client_ip(request)
    )
    student = await _get_or_404(db, AppUser, body.student_id, "Estudiante")
    return {"message": f"{student.full_name} matriculado en el grupo #{enrollment.group_id}"}

@router.delete("/groups/{group_id}/students/{student_id}", response_model=dict)
async def unenroll_student(
    group_id: int, student_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    resultado = await retirar(db, admin, group_id=group_id, student_id=student_id,
                              ip=_client_ip(request))
    return {"message": f"Matrícula {resultado['modo']}"}

@router.post("/groups/{group_id}/students/{student_id}/transfer")
async def transfer_student(
    group_id: int, student_id: int, body: dict, request: Request, db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    destino = body.get("destino_group_id")
    if not isinstance(destino, int):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Falta 'destino_group_id' (int)")
    return await transferir(
        db, admin, group_id=group_id, student_id=student_id,
        destino_group_id=destino, ip=_client_ip(request),
    )

class CursoSugeridoOut(BaseModel):
    id: int
    code: str
    name: str
    cycle: int
    score: float
    motivo: str

class BloquePreviewOut(BloqueExtraido):
    teacher_id: int | None = None
    room_id: int | None = None
    curso_sugerido: CursoSugeridoOut | None = None

class ImportPreviewOut(BaseModel):
    tipo: str
    paginas: int
    total: int
    confiables: int
    ambiguousos: int
    bloques: list[BloquePreviewOut]

def _id_de_coincidencia(coincidencia: Coincidencia | None) -> int | None:
    if coincidencia is None:
        return None
    return getattr(coincidencia.valor, "id", None)

def _curso_sugerido_out(coincidencia: Coincidencia | None) -> CursoSugeridoOut | None:
    if coincidencia is None or not isinstance(coincidencia.valor, Course):
        return None
    curso = coincidencia.valor
    return CursoSugeridoOut(
        id=curso.id, code=curso.code, name=curso.name, cycle=curso.cycle,
        score=coincidencia.puntaje, motivo=coincidencia.motivo,
    )

@router.post("/courses/import-pdf", response_model=ImportPreviewOut)
async def import_pdf_preview(
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
    file: Annotated[UploadFile, File(description="Horario en PDF, JPG, PNG o WEBP")],
) -> ImportPreviewOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El archivo está vacío")
    if len(raw) > MAX_PESO_ARCHIVO:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="El archivo supera el máximo de 10 MB")
    try:
        documento = await leer_documento_async(raw, file.filename)
        bloques = extraer_horarios_documento(documento)
        if not bloques and documento.tipo == "pdf_texto":
            documento = await leer_documento_async(raw, file.filename, forzar_ocr=True)
            bloques = extraer_horarios_documento(documento)
    except ValueError as exc:
        detalle = str(exc)
        codigo = (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
                  if detalle.startswith("Formato no soportado") else
                  status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(status_code=codigo, detail=detalle) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="No se pudo leer el archivo; ¿es un horario válido?") from exc
    if documento.paginas == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El documento no tiene páginas legibles")
    if not bloques:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=("No se reconocieron bloques de horario. Revisa que la foto sea de un "
                    "horario impreso, recto y con buena luz, o corrige el archivo a mano."),
        )
    cursos = (await db.exec(select(Course))).all()
    docentes = (
        await db.exec(
            select(AppUser).where(
                AppUser.role == UserRole.DOCENTE,
                AppUser.is_active,
            )
        )
    ).all()
    aulas = (await db.exec(select(Room).where(Room.is_active))).all()
    preview: list[BloquePreviewOut] = []
    for bloque in bloques:
        sugerencia = (
            sugerir_curso(bloque.course_code, bloque.course_name, cursos)
            if bloque.course_code else None
        )
        docente = emparejar_docente(bloque.teacher_name, docentes)
        aula = emparejar_aula(bloque.room_code, aulas)
        preview.append(
            BloquePreviewOut(
                **bloque.model_dump(),
                teacher_id=_id_de_coincidencia(docente),
                room_id=_id_de_coincidencia(aula),
                curso_sugerido=_curso_sugerido_out(sugerencia),
            )
        )

    await audit(db, admin, action="importacion_preview", entity="schedule_block",
                new_value={"archivo": file.filename, "tipo": documento.tipo,
                           "paginas": documento.paginas, "bloques": len(preview)},
                ip_address=_client_ip(request))
    await db.commit()
    return ImportPreviewOut(
        tipo=documento.tipo,
        paginas=documento.paginas,
        total=len(preview),
        confiables=sum(1 for b in preview if b.confiable),
        ambiguousos=sum(1 for b in preview if not b.confiable),
        bloques=preview,
    )

class BloqueConfirmado(BaseModel):
    course_code: str = Field(min_length=3, max_length=20)
    course_name: str | None = Field(default=None, max_length=160)
    group_code: str = Field(min_length=1, max_length=5)
    weekday: int = Field(ge=1, le=5, description="1=Lunes … 5=Viernes")
    start_time: time
    end_time: time
    teacher_id: int | None = Field(default=None, description="Docente del grupo (por defecto, el del import)")
    room_id: int | None = Field(default=None, description="Aula del bloque; por defecto, la del import")

    @field_validator("course_code", "group_code")
    @classmethod
    def _mayusculas(cls, v: str) -> str:
        return v.strip().upper()

class ImportConfirmIn(BaseModel):
    teacher_id: int | None = Field(default=None, description="Docente por defecto de los grupos creados")
    room_id: int | None = Field(default=None, description="Aula por defecto de los bloques importados")
    cycle: int = Field(ge=1, le=10, description="Ciclo de los cursos nuevos (1-10)")
    semester_label: str | None = Field(default=None, max_length=20,
                                       description="Periodo de los grupos; por defecto, el vigente")
    bloques: list[BloqueConfirmado] = Field(min_length=1, max_length=200)

class ImportConfirmOut(BaseModel):
    cursos_creados: list[str]
    grupos_creados: list[str]
    bloques_creados: int
    omitidos: int
    total_bloques: int

@router.post("/courses/import-pdf/confirm", response_model=ImportConfirmOut,
             status_code=status.HTTP_201_CREATED)
async def import_pdf_confirm(
    body: ImportConfirmIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> ImportConfirmOut:
    if body.teacher_id is not None and (await _docente_valido(db, body.teacher_id)) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El docente asignado no existe o no está activo")
    if body.room_id is not None:
        await _get_or_404(db, Room, body.room_id, "Aula")
    periodo = ((body.semester_label or "").strip() or await semestre_vigente(db)).upper()
    cursos_nuevos: list[str] = []
    grupos_nuevos: list[str] = []
    bloques_creados = 0
    omitidos = 0
    vistos: set[tuple[str, str]] = set()
    grupos_en_sesion: dict[tuple[str, str], CourseGroup] = {}
    docentes_grupo: dict[tuple[str, str], int | None] = {}

    try:
        for b in body.bloques:
            curso = (await db.exec(select(Course).where(Course.code == b.course_code))).first()
            if curso is None:
                curso = Course(code=b.course_code,
                               name=b.course_name or f"Curso {b.course_code}",
                               cycle=body.cycle)
                db.add(curso)
                await db.flush()
                cursos_nuevos.append(curso.code)
            elif (curso.name is None or curso.name.startswith("Curso ")) and b.course_name:
                curso.name = b.course_name
                db.add(curso)

            docente_id = b.teacher_id or body.teacher_id
            if docente_id is not None and (await _docente_valido(db, docente_id)) is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f"El docente {docente_id} del bloque no existe o no está activo")

            clave = (b.course_code, b.group_code)
            if clave in vistos:
                grupo = grupos_en_sesion[clave]
                docente_actual = docentes_grupo[clave]
                if docente_id is not None and docente_actual is None:
                    grupo.teacher_id = docente_id
                    db.add(grupo)
                    docentes_grupo[clave] = docente_id
                elif docente_id is not None and docente_actual != docente_id:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                        detail=("Un grupo tiene un solo docente; revisa las filas de "
                                                f"{curso.code} grupo {b.group_code}"))
            else:
                grupo = (await db.exec(
                    select(CourseGroup).where(
                        CourseGroup.course_id == curso.id,
                        CourseGroup.group_code == b.group_code,
                        CourseGroup.semester_label == periodo,
                    )
                )).first()
                if grupo is None:
                    grupo = CourseGroup(course_id=curso.id, group_code=b.group_code,
                                        teacher_id=docente_id,
                                        semester_label=periodo, capacity=40)
                    db.add(grupo)
                    await db.flush()
                    grupos_nuevos.append(f"{curso.code}-{b.group_code}")
                elif not grupo.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(f"El grupo {curso.code}-{b.group_code} está inactivo; "
                                "reactívalo antes de importar"),
                    )
                elif docente_id is not None and grupo.teacher_id is None:
                    grupo.teacher_id = docente_id
                    db.add(grupo)
                elif docente_id is not None and grupo.teacher_id != docente_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(f"El grupo {curso.code}-{b.group_code} ya tiene otro docente; "
                                "no se reasigna desde la importación"),
                    )
                grupos_en_sesion[clave] = grupo
                docentes_grupo[clave] = grupo.teacher_id
                vistos.add(clave)

            existente = (await db.exec(
                select(ScheduleBlock).where(
                    ScheduleBlock.group_id == grupo.id,
                    ScheduleBlock.weekday == b.weekday,
                    ScheduleBlock.start_time == b.start_time,
                    ScheduleBlock.end_time == b.end_time,
                )
            )).first()
            if existente is not None:
                omitidos += 1
                continue

            await add_block(
                db, admin, group_id=grupo.id, weekday=b.weekday,
                start_time=b.start_time, end_time=b.end_time,
                room_id=b.room_id or body.room_id,
                teacher_id=docente_id,
                ip=_client_ip(request), commit=False,
            )
            bloques_creados += 1
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    await audit(db, admin, action="importacion_confirmada", entity="schedule_block",
                new_value={"cursos": cursos_nuevos, "grupos": grupos_nuevos,
                           "bloques": bloques_creados, "omitidos": omitidos,
                           "periodo": periodo},
                ip_address=_client_ip(request))
    await db.commit()
    return ImportConfirmOut(
        cursos_creados=cursos_nuevos, grupos_creados=grupos_nuevos,
        bloques_creados=bloques_creados, omitidos=omitidos,
        total_bloques=len(body.bloques),
    )


async def _docente_valido(db: DbSession, teacher_id: int) -> AppUser | None:
    docente = await db.get(AppUser, teacher_id)
    if docente is None or docente.role is not UserRole.DOCENTE or not docente.is_active:
        return None
    return docente
