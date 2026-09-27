"""Carga académica - RF-06 (cursos → grupos → bloques con validación de
choques) y RF-22 (matrícula estudiante ↔ grupo).

La validación de solapamientos (misma aula o mismo docente en rangos que se
cruzan) vive en ``app/services/schedule.py``; aquí solo se orchestra y se
audita (RF-32).
"""
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
from app.services.schedule import add_block, update_block
from app.tables import AppUser, Course, CourseGroup, Enrollment, Room, ScheduleBlock, UserRole

router = APIRouter(tags=["courses"])


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------
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
        cond = Course.code.ilike(like) | Course.name.ilike(like)  # type: ignore[union-attr]
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await db.exec(count_stmt)).one()
    courses = (await db.exec(stmt.order_by(Course.code).offset(page.offset).limit(page.limit))).all()
    return Page(
        items=[CourseOut(id=c.id, code=c.code, name=c.name) for c in courses],  # type: ignore[arg-type]
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
    return CourseOut(id=course.id, code=course.code, name=course.name)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------
class GroupIn(BaseModel):
    group_code: str = Field(min_length=1, max_length=5, examples=["A"])
    teacher_id: int
    room_id: int


class GroupOut(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_name: str
    group_code: str
    teacher_id: int
    teacher_name: str
    room_id: int
    room_code: str
    is_active: bool


def _group_out(g: CourseGroup, course: Course, teacher: AppUser, room: Room) -> GroupOut:
    return GroupOut(
        id=g.id,  # type: ignore[arg-type]
        course_id=course.id,  # type: ignore[arg-type]
        course_code=course.code,
        course_name=course.name,
        group_code=g.group_code,
        teacher_id=teacher.id,  # type: ignore[arg-type]
        teacher_name=teacher.full_name,
        room_id=room.id,  # type: ignore[arg-type]
        room_code=room.code,
        is_active=g.is_active,
    )


async def _group_rows(db, *, group_id: int | None = None, course_id: int | None = None,
                      teacher_id: int | None = None, active_only: bool = False):
    stmt = (
        select(CourseGroup, Course, AppUser, Room)
        .join(Course, Course.id == CourseGroup.course_id)
        .join(AppUser, AppUser.id == CourseGroup.teacher_id)
        .join(Room, Room.id == CourseGroup.room_id)
    )
    if group_id is not None:
        stmt = stmt.where(CourseGroup.id == group_id)
    if course_id is not None:
        stmt = stmt.where(CourseGroup.course_id == course_id)
    if teacher_id is not None:
        stmt = stmt.where(CourseGroup.teacher_id == teacher_id)
    if active_only:
        stmt = stmt.where(CourseGroup.is_active)  # type: ignore[arg-type]
    return (await db.exec(stmt.order_by(Course.code, CourseGroup.group_code))).all()


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = None,
    teacher_id: int | None = None,
    include_inactive: bool = False,
) -> list[GroupOut]:
    rows = await _group_rows(db, course_id=course_id, teacher_id=teacher_id,
                             active_only=not include_inactive)
    return [_group_out(g, c, t, r) for g, c, t, r in rows]


@router.get("/courses/{course_id}/groups", response_model=list[GroupOut])
async def list_course_groups(
    course_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> list[GroupOut]:
    await _get_or_404(db, Course, course_id, "Curso")
    rows = await _group_rows(db, course_id=course_id)
    return [_group_out(g, c, t, r) for g, c, t, r in rows]


@router.post("/courses/{course_id}/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    course_id: int, body: GroupIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> GroupOut:
    course = await _get_or_404(db, Course, course_id, "Curso")
    group_code = body.group_code.strip().upper()
    if (await db.exec(
        select(CourseGroup).where(CourseGroup.course_id == course_id, CourseGroup.group_code == group_code)
    )).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El curso {course.code} ya tiene un grupo '{group_code}'",
        )
    teacher = await _get_or_404(db, AppUser, body.teacher_id, "Docente")
    if teacher.role is not UserRole.DOCENTE or not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El usuario asignado debe ser un docente activo")
    room = await _get_or_404(db, Room, body.room_id, "Aula")

    group = CourseGroup(course_id=course_id, group_code=group_code,
                        teacher_id=body.teacher_id, room_id=body.room_id)
    db.add(group)
    await db.flush()  # obtiene group.id para la bitácora
    await audit(db, admin, action="grupo_creado", entity="course_group", entity_id=group.id,
                new_value={"course": course.code, "group": group_code,
                           "teacher_id": body.teacher_id, "room_id": body.room_id},
                ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(group)
    return _group_out(group, course, teacher, room)


@router.delete("/groups/{group_id}", response_model=dict)
async def deactivate_group(
    group_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    """Baja lógica del grupo: deja de abrir sesiones y de validar choques."""
    group = await _get_or_404(db, CourseGroup, group_id, "Grupo")
    if not group.is_active:
        raise errors.DomainError("El grupo ya está inactivo")
    group.is_active = False
    db.add(group)
    await audit(db, admin, action="grupo_desactivado", entity="course_group", entity_id=group.id,
                ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Grupo #{group_id} desactivado"}


# ---------------------------------------------------------------------------
# Bloques horarios - RF-06 (choques)
# ---------------------------------------------------------------------------
class BlockIn(BaseModel):
    weekday: int = Field(ge=1, le=7, description="1=Lunes … 7=Domingo")
    start_time: time
    end_time: time


class BlockUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=1, le=7)
    start_time: time | None = None
    end_time: time | None = None


class BlockOut(BaseModel):
    id: int
    group_id: int
    weekday: int
    start_time: time
    end_time: time


def _block_out(b: ScheduleBlock) -> BlockOut:
    return BlockOut(id=b.id, group_id=b.group_id, weekday=b.weekday,  # type: ignore[arg-type]
                    start_time=b.start_time, end_time=b.end_time)


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
    return [_block_out(b) for b in blocks]


@router.post("/groups/{group_id}/blocks", response_model=BlockOut, status_code=status.HTTP_201_CREATED)
async def create_block(
    group_id: int, body: BlockIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> BlockOut:
    """RF-06: valida solapamientos (misma aula o mismo docente) antes de crear."""
    block = await add_block(
        db, admin, group_id=group_id, weekday=body.weekday,
        start_time=body.start_time, end_time=body.end_time, ip=_client_ip(request),
    )
    return _block_out(block)


@router.patch("/blocks/{block_id}", response_model=BlockOut)
async def patch_block(
    block_id: int, body: BlockUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> BlockOut:
    block = await update_block(db, admin, block_id=block_id,
                               data=body.model_dump(exclude_unset=True), ip=_client_ip(request))
    return _block_out(block)


@router.delete("/blocks/{block_id}", response_model=dict)
async def delete_block(
    block_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    block = await _get_or_404(db, ScheduleBlock, block_id, "Bloque horario")
    old = {"group_id": block.group_id, "weekday": block.weekday,
           "start_time": str(block.start_time), "end_time": str(block.end_time)}
    await db.delete(block)
    await audit(db, admin, action="bloque_eliminado", entity="schedule_block", entity_id=block_id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"Bloque #{block_id} eliminado"}


# ---------------------------------------------------------------------------
# Matrículas - RF-22
# ---------------------------------------------------------------------------
class EnrollIn(BaseModel):
    student_id: int


class EnrolledStudentOut(BaseModel):
    id: int
    code: str | None
    full_name: str
    email: str
    semester: int | None
    enrolled_at: str | None


@router.get("/groups/{group_id}/students", response_model=list[EnrolledStudentOut])
async def list_enrolled(
    group_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> list[EnrolledStudentOut]:
    await _get_or_404(db, CourseGroup, group_id, "Grupo")
    rows = (
        await db.exec(
            select(AppUser, Enrollment.enrolled_at)
            .join(Enrollment, Enrollment.student_id == AppUser.id)
            .where(Enrollment.group_id == group_id)
            .order_by(AppUser.full_name)
        )
    ).all()
    return [
        EnrolledStudentOut(
            id=u.id, code=u.code, full_name=u.full_name, email=u.email, semester=u.semester,  # type: ignore[arg-type]
            enrolled_at=ea.isoformat(timespec="seconds") if ea else None,
        )
        for u, ea in rows
    ]


@router.post("/groups/{group_id}/students", status_code=status.HTTP_201_CREATED)
async def enroll_student(
    group_id: int, body: EnrollIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    group = await _get_or_404(db, CourseGroup, group_id, "Grupo")
    if not group.is_active:
        raise errors.DomainError("No se puede matricular en un grupo inactivo")
    student = await _get_or_404(db, AppUser, body.student_id, "Estudiante")
    if student.role is not UserRole.ESTUDIANTE:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Solo se matricula a usuarios con rol estudiante")
    if (await db.exec(
        select(Enrollment).where(Enrollment.student_id == body.student_id, Enrollment.group_id == group_id)
    )).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="El estudiante ya está matriculado en este grupo")
    enrollment = Enrollment(student_id=body.student_id, group_id=group_id)
    db.add(enrollment)
    await audit(db, admin, action="matricula_creada", entity="enrollment",
                new_value={"student_id": body.student_id, "group_id": group_id},
                ip_address=_client_ip(request))
    await db.commit()
    return {"message": f"{student.full_name} matriculado en el grupo #{group_id}"}


@router.delete("/groups/{group_id}/students/{student_id}", response_model=dict)
async def unenroll_student(
    group_id: int, student_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    enrollment = (
        await db.exec(
            select(Enrollment).where(Enrollment.group_id == group_id, Enrollment.student_id == student_id)
        )
    ).first()
    if enrollment is None:
        raise errors.NotFoundError("El estudiante no está matriculado en ese grupo")
    await db.delete(enrollment)
    await audit(db, admin, action="matricula_eliminada", entity="enrollment", entity_id=enrollment.id,
                old_value={"student_id": student_id, "group_id": group_id},
                ip_address=_client_ip(request))
    await db.commit()
    return {"message": "Matrícula eliminada"}


# ---------------------------------------------------------------------------
# Importación de horarios por PDF - RF-07 (previsualizar → confirmar)
# ---------------------------------------------------------------------------
from fastapi import File, UploadFile  # noqa: E402
from pydantic import field_validator  # noqa: E402

from app.services.ocr_schedule import (  # noqa: E402
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
    file: UploadFile = File(..., description="Constancia de matrícula en PDF"),  # noqa: B008
) -> ImportPreviewOut:
    """RF-07 paso 1: extrae bloques horarios y los devuelve para revisión.

    NADA se persiste aquí: el admin corrige lo ambiguo en la pantalla de
    confirmación y recién entonces llama a /courses/import-pdf/confirm.
    """
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
    """Un bloque ya revisado por el admin (RF-07 paso 2)."""

    course_code: str = Field(min_length=3, max_length=20)
    course_name: str | None = Field(default=None, max_length=160)
    group_code: str = Field(min_length=1, max_length=5)
    weekday: int = Field(ge=1, le=7)
    start_time: time
    end_time: time

    @field_validator("course_code", "group_code")
    @classmethod
    def _mayusculas(cls, v: str) -> str:
        return v.strip().upper()


class ImportConfirmIn(BaseModel):
    teacher_id: int = Field(description="Docente del/de los grupos creados")
    room_id: int = Field(description="Aula del/de los grupos creados")
    bloques: list[BloqueConfirmado] = Field(min_length=1, max_length=200)


class ImportConfirmOut(BaseModel):
    cursos_creados: list[str]
    grupos_creados: list[str]  # 'ISA903-A'
    bloques_creados: int
    total_bloques: int


@router.post("/courses/import-pdf/confirm", response_model=ImportConfirmOut,
             status_code=status.HTTP_201_CREATED)
async def import_pdf_confirm(
    body: ImportConfirmIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> ImportConfirmOut:
    """RF-07 paso 2: persiste la propuesta REVISADA por el admin.

    Crea cursos que no existan, un grupo por (curso, group_code) y sus
    bloques con la MISMA validación de choques RF-06 que el alta manual.
    Todo o nada: si un choque revienta, no queda nada a medias.
    """
    teacher = await _get_or_404(db, AppUser, body.teacher_id, "Docente")
    if teacher.role is not UserRole.DOCENTE or not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El docente asignado no existe o no está activo")
    room = await _get_or_404(db, Room, body.room_id, "Aula")  # noqa: F841 - valida existencia
    cursos_nuevos: list[str] = []
    grupos_nuevos: list[str] = []
    bloques_creados = 0
    vistos: set[tuple[str, str]] = set()
    _grupos_en_sesion: dict[tuple[str, str], CourseGroup] = {}

    try:
        for b in body.bloques:
            # 1) Curso (lo crea si no existe)
            curso = (await db.exec(select(Course).where(Course.code == b.course_code))).first()
            if curso is None:
                curso = Course(code=b.course_code,
                               name=b.course_name or f"Curso {b.course_code}")
                db.add(curso)
                await db.flush()
                cursos_nuevos.append(curso.code)
            elif (curso.name is None or curso.name.startswith("Curso ")) and b.course_name:
                curso.name = b.course_name  # completa el nombre faltante
                db.add(curso)

            # 2) Grupo (uno por curso+código; reutiliza el existente si ya hay)
            clave = (b.course_code, b.group_code)
            if clave in vistos:
                grupo = _grupos_en_sesion[clave]
            else:
                grupo = (await db.exec(
                    select(CourseGroup).where(
                        CourseGroup.course_id == curso.id, CourseGroup.group_code == b.group_code)
                )).first()
                if grupo is None:
                    grupo = CourseGroup(course_id=curso.id, group_code=b.group_code,
                                        teacher_id=body.teacher_id, room_id=body.room_id)
                    db.add(grupo)
                    await db.flush()
                    grupos_nuevos.append(f"{curso.code}-{b.group_code}")
                _grupos_en_sesion[clave] = grupo
                vistos.add(clave)

            # 3) Bloque con choques RF-06 (misma validación que el manual);
            #    commit=False: la transacción la cierra este endpoint (todo o nada)
            await add_block(
                db, admin, group_id=grupo.id, weekday=b.weekday,
                start_time=b.start_time, end_time=b.end_time,
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
