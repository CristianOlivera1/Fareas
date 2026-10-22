from datetime import time

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import func, select

from app.core.deps import DbSession, RequireRole
from app.core.pagination import PageParamsDep
from app.routers.catalog import _client_ip, _get_or_404
from app.schemas.common import Page
from app.services import errors
from app.services.audit import audit
from app.services.enrollments import matricular, retirar, transferir
from app.services.schedule import add_block, update_block
from app.services.settings import semestre_vigente, semesters_con_grupos
from app.tables import AppUser, Course, CourseGroup, Enrollment, Room, ScheduleBlock, UserRole

router = APIRouter(tags=["courses"])


class CourseIn(BaseModel):
    code: str = Field(min_length=3, max_length=20, examples=["ISA903"])
    name: str = Field(min_length=3, max_length=160, examples=["Inteligencia Artificial I"])

class CourseOut(BaseModel):
    id: int
    code: str
    name: str

@router.get("/courses", response_model=Page[CourseOut])
async def list_courses(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    q: str | None = Query(None, max_length=80, description="Filtra por código o nombre"),
) -> Page[CourseOut]:
    stmt = select(Course)
    count_stmt = select(func.count()).select_from(Course)
    if q:
        like = f"%{q}%"
        cond = Course.code.ilike(like) | Course.name.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await db.exec(count_stmt)).one()
    courses = (await db.exec(stmt.order_by(Course.code).offset(page.offset).limit(page.limit))).all()
    return Page(
        items=[CourseOut(id=c.id, code=c.code, name=c.name) for c in courses],
        total=total, page=page.page, page_size=page.page_size,
    )

@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(body: CourseIn, db: DbSession, _admin: RequireRole(UserRole.ADMIN)) -> CourseOut:
    code = body.code.strip().upper()
    if (await db.exec(select(Course).where(Course.code == code))).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El curso '{code}' ya existe")
    course = Course(code=code, name=body.name.strip())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return CourseOut(id=course.id, code=course.code, name=course.name)

class GroupIn(BaseModel):
    group_code: str = Field(min_length=1, max_length=5, examples=["A"])
    teacher_id: int
    capacity: int = Field(default=40, gt=0, description="Cupo del grupo (40 por defecto, R8)")

class GroupOut(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_name: str
    group_code: str
    teacher_id: int
    teacher_name: str
    semester_label: str
    capacity: int
    enrolled_count: int
    is_active: bool

async def _group_out(db, g: CourseGroup, course: Course, teacher: AppUser) -> GroupOut:
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
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        semester_label=g.semester_label,
        capacity=g.capacity,
        enrolled_count=activos,
        is_active=g.is_active,
    )

async def _group_rows(db, *, group_id: int | None = None, course_id: int | None = None,
                      teacher_id: int | None = None, active_only: bool = False,
                      semester: str | None = None):
    stmt = (
        select(CourseGroup, Course, AppUser)
        .join(Course, Course.id == CourseGroup.course_id)
        .join(AppUser, AppUser.id == CourseGroup.teacher_id)
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
    return (await db.exec(stmt.order_by(Course.code, CourseGroup.group_code))).all()

@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = None,
    teacher_id: int | None = None,
    include_inactive: bool = False,
    semester: str | None = Query(None, max_length=40, description="Default: todos"),
) -> list[GroupOut]:
    rows = await _group_rows(db, course_id=course_id, teacher_id=teacher_id,
                             active_only=not include_inactive, semester=semester)
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

class BlockUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=5)
    start_time: time | None = None
    end_time: time | None = None
    room_id: int | None = None

class BlockOut(BaseModel):
    id: int
    group_id: int
    room_id: int
    room_code: str
    weekday: int
    start_time: time
    end_time: time

async def _block_out(db, b: ScheduleBlock) -> BlockOut:
    room = await db.get(Room, b.room_id)
    return BlockOut(id=b.id, group_id=b.group_id, room_id=b.room_id,
                    room_code=room.code if room is not None else "",
                    weekday=b.weekday, start_time=b.start_time, end_time=b.end_time)

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
        ip=_client_ip(request),
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
    old = {"group_id": block.group_id, "room_id": block.room_id, "weekday": block.weekday,
           "start_time": str(block.start_time), "end_time": str(block.end_time)}
    await db.delete(block)
    await audit(db, admin, action="bloque_eliminado", entity="schedule_block", entity_id=block_id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Bloque #{block_id} eliminado"}

class ScheduleRowOut(BaseModel):
    id: int
    group_id: int
    course_id: int
    course_code: str
    course_name: str
    group_code: str
    teacher_id: int
    teacher_name: str
    room_id: int
    room_code: str
    semester_label: str
    weekday: int
    start_time: time
    end_time: time

@router.get("/schedule", response_model=list[ScheduleRowOut])
async def general_schedule(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    semester: str | None = Query(None, max_length=40, description="Default: semestre vigente (R1)"),
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
        .join(AppUser, AppUser.id == CourseGroup.teacher_id)
        .join(Room, Room.id == ScheduleBlock.room_id)
        .where(CourseGroup.semester_label == semester)
        .order_by(ScheduleBlock.weekday, ScheduleBlock.start_time, Course.code)
    )
    if not include_inactive:
        stmt = stmt.where(CourseGroup.is_active)
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
            teacher_id=t.id,
            teacher_name=t.full_name,
            room_id=r.id,
            room_code=r.code,
            semester_label=g.semester_label,
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
            .order_by(Enrollment.withdrawn_at.is_(None).desc(), AppUser.full_name)
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
    return [
        EnrolledStudentOut(
            id=u.id, code=u.code, full_name=u.full_name, email=u.email, semester=u.semester,
            enrolled_at=ea.isoformat(timespec="seconds") if ea else None,
            withdrawn_at=w.isoformat(timespec="seconds") if w else None,
            has_face=(u.id in con_rostro) if with_face else None,
        )
        for u, ea, w in rows
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

from fastapi import File, UploadFile
from pydantic import field_validator

from app.services.ocr_schedule import (
    MAX_PESO_PDF,
    BloqueExtraido,
    extraer_horarios,
)


class ImportPreviewOut(BaseModel):
    paginas: int
    total: int
    confiables: int
    ambiguousos: int
    bloques: list[BloqueExtraido]

@router.post("/courses/import-pdf", response_model=ImportPreviewOut)
async def import_pdf_preview(
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
    file: UploadFile = File(..., description="Constancia de matrícula en PDF"),
) -> ImportPreviewOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El archivo está vacío")
    if len(raw) > MAX_PESO_PDF:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="El PDF supera el máximo de 10 MB")
    try:
        bloques, paginas = extraer_horarios(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="No se pudo leer el PDF; ¿es un archivo válido?") from exc
    if paginas == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El PDF no tiene páginas legibles")
    if not bloques and paginas > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=("No se encontró TEXTO en el PDF (probablemente es un escaneo). "
                    "RF-07 procesa constancias digitales, no imágenes; ingresa el horario a mano."),
        )
    await audit(db, admin, action="importacion_preview", entity="schedule_block",
                new_value={"archivo": file.filename, "paginas": paginas, "bloques": len(bloques)},
                ip_address=_client_ip(request))
    return ImportPreviewOut(
        paginas=paginas,
        total=len(bloques),
        confiables=sum(1 for b in bloques if b.confiable),
        ambiguousos=sum(1 for b in bloques if not b.confiable),
        bloques=bloques,
    )

class BloqueConfirmado(BaseModel):
    course_code: str = Field(min_length=3, max_length=20)
    course_name: str | None = Field(default=None, max_length=160)
    group_code: str = Field(min_length=1, max_length=5)
    weekday: int = Field(ge=1, le=5, description="1=Lunes … 5=Viernes")
    start_time: time
    end_time: time
    room_id: int | None = Field(default=None, description="Aula del bloque; por defecto, la del import")

    @field_validator("course_code", "group_code")
    @classmethod
    def _mayusculas(cls, v: str) -> str:
        return v.strip().upper()

class ImportConfirmIn(BaseModel):
    teacher_id: int = Field(description="Docente del/de los grupos creados")
    room_id: int = Field(description="Aula por defecto de los bloques importados")
    bloques: list[BloqueConfirmado] = Field(min_length=1, max_length=200)

class ImportConfirmOut(BaseModel):
    cursos_creados: list[str]
    grupos_creados: list[str]
    bloques_creados: int
    total_bloques: int

@router.post("/courses/import-pdf/confirm", response_model=ImportConfirmOut,
             status_code=status.HTTP_201_CREATED)
async def import_pdf_confirm(
    body: ImportConfirmIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> ImportConfirmOut:
    teacher = await _get_or_404(db, AppUser, body.teacher_id, "Docente")
    if teacher.role is not UserRole.DOCENTE or not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El docente asignado no existe o no está activo")
    room = await _get_or_404(db, Room, body.room_id, "Aula")
    cursos_nuevos: list[str] = []
    grupos_nuevos: list[str] = []
    bloques_creados = 0
    vistos: set[tuple[str, str]] = set()
    _grupos_en_sesion: dict[tuple[str, str], CourseGroup] = {}

    try:
        for b in body.bloques:
            curso = (await db.exec(select(Course).where(Course.code == b.course_code))).first()
            if curso is None:
                curso = Course(code=b.course_code,
                               name=b.course_name or f"Curso {b.course_code}")
                db.add(curso)
                await db.flush()
                cursos_nuevos.append(curso.code)
            elif (curso.name is None or curso.name.startswith("Curso ")) and b.course_name:
                curso.name = b.course_name
                db.add(curso)

            clave = (b.course_code, b.group_code)
            if clave in vistos:
                grupo = _grupos_en_sesion[clave]
            else:
                sem_vigente = await semestre_vigente(db)
                grupo = (await db.exec(
                    select(CourseGroup).where(
                        CourseGroup.course_id == curso.id,
                        CourseGroup.group_code == b.group_code,
                        CourseGroup.semester_label == sem_vigente,
                    )
                )).first()
                if grupo is None:
                    grupo = CourseGroup(course_id=curso.id, group_code=b.group_code,
                                        teacher_id=body.teacher_id,
                                        semester_label=sem_vigente, capacity=40)
                    db.add(grupo)
                    await db.flush()
                    grupos_nuevos.append(f"{curso.code}-{b.group_code}")
                _grupos_en_sesion[clave] = grupo
                vistos.add(clave)

            await add_block(
                db, admin, group_id=grupo.id, weekday=b.weekday,
                start_time=b.start_time, end_time=b.end_time,
                room_id=b.room_id or body.room_id,
                ip=_client_ip(request), commit=False,
            )
            bloques_creados += 1
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await audit(db, admin, action="importacion_confirmada", entity="schedule_block",
                new_value={"cursos": cursos_nuevos, "grupos": grupos_nuevos,
                           "bloques": bloques_creados},
                ip_address=_client_ip(request))
    await db.commit()
    return ImportConfirmOut(
        cursos_creados=cursos_nuevos, grupos_creados=grupos_nuevos,
        bloques_creados=bloques_creados, total_bloques=len(body.bloques),
    )
