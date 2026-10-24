from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip
from app.services.audit import audit
from app.services.ocr_curriculum import extraer_malla_documento
from app.services.ocr_extract import MAX_PESO_ARCHIVO, leer_documento_async
from app.tables import Course, UserRole

router = APIRouter(tags=["courses"])

MAX_COURSES = 200


class ExistingCourseOut(BaseModel):
    id: int
    name: str
    cycle: int


class CurriculumRowOut(BaseModel):
    fila: int
    code: str
    name: str
    cycle: int | None
    confiable: bool
    nota: str | None
    linea: str
    pagina: int
    ya_existe: bool
    existente: ExistingCourseOut | None


class CurriculumPreviewOut(BaseModel):
    tipo: str
    paginas: int
    total: int
    listos: int
    por_revisar: int
    ya_existentes: int
    ciclos: list[int]
    cursos: list[CurriculumRowOut]


class CurriculumCourseIn(BaseModel):
    code: str = Field(min_length=3, max_length=20)
    name: str = Field(min_length=3, max_length=160)
    cycle: int = Field(ge=1, le=10)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        return " ".join(value.split())


class CurriculumConfirmIn(BaseModel):
    cursos: list[CurriculumCourseIn] = Field(min_length=1, max_length=MAX_COURSES)


class CurriculumConfirmOut(BaseModel):
    creados: int
    omitidos: int
    codigos_creados: list[str]
    codigos_omitidos: list[str]
    total: int


def _download_error(detail: str) -> HTTPException:
    code = (
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        if detail.startswith("Formato no soportado")
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(status_code=code, detail=detail)


@router.post("/courses/import-curriculum", response_model=CurriculumPreviewOut)
async def import_curriculum_preview(
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
    file: Annotated[UploadFile, File(description="Malla curricular en PDF, JPG, PNG o WEBP")],
    default_cycle: Annotated[int | None, Form(ge=1, le=10)] = None,
) -> CurriculumPreviewOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="El archivo está vacío")
    if len(raw) > MAX_PESO_ARCHIVO:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="El archivo supera el máximo de 10 MB"
        )

    try:
        document = await leer_documento_async(raw, file.filename)
        extracted = extraer_malla_documento(document, default_cycle)
        if not extracted and document.tipo == "pdf_texto":
            document = await leer_documento_async(raw, file.filename, forzar_ocr=True)
            extracted = extraer_malla_documento(document, default_cycle)
    except ValueError as exc:
        raise _download_error(str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se pudo leer el archivo; ¿es una malla curricular válida?",
        ) from exc

    if not extracted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "No se reconocieron cursos. Revisa que la imagen muestre los códigos de los cursos y los "
                "títulos de ciclo («PRIMER CICLO», «SEGUNDO CICLO»…), o indica el ciclo por defecto."
            ),
        )

    existing = {course.code: course for course in (await db.exec(select(Course))).all()}
    rows: list[CurriculumRowOut] = []
    for index, course in enumerate(extracted, start=1):
        current = existing.get(course.code)
        note = course.nota
        if current is not None:
            differs = current.name.strip().lower() != course.name.strip().lower() or current.cycle != course.cycle
            detail = "Ya existe en el sistema; no se modificará"
            note = "; ".join(filter(None, [note, detail + (" (con otro nombre o ciclo)" if differs else "")]))
        rows.append(
            CurriculumRowOut(
                fila=index,
                code=course.code,
                name=course.name,
                cycle=course.cycle,
                confiable=course.confiable,
                nota=note,
                linea=course.linea,
                pagina=course.pagina,
                ya_existe=current is not None,
                existente=(
                    ExistingCourseOut(id=current.id, name=current.name, cycle=current.cycle)
                    if current is not None
                    else None
                ),
            )
        )

    await audit(
        db, admin, action="importacion_malla_preview", entity="course",
        new_value={"archivo": file.filename, "tipo": document.tipo, "paginas": document.paginas, "cursos": len(rows)},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return CurriculumPreviewOut(
        tipo=document.tipo,
        paginas=document.paginas,
        total=len(rows),
        listos=sum(1 for row in rows if row.confiable and not row.ya_existe),
        por_revisar=sum(1 for row in rows if not row.confiable),
        ya_existentes=sum(1 for row in rows if row.ya_existe),
        ciclos=sorted({row.cycle for row in rows if row.cycle is not None}),
        cursos=rows,
    )


@router.post(
    "/courses/import-curriculum/confirm",
    response_model=CurriculumConfirmOut,
    status_code=status.HTTP_201_CREATED,
)
async def import_curriculum_confirm(
    body: CurriculumConfirmIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> CurriculumConfirmOut:
    repeated = sorted({
        code for code in (course.code for course in body.cursos)
        if sum(1 for other in body.cursos if other.code == code) > 1
    })
    if repeated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Hay códigos repetidos en la lista: {', '.join(repeated)}",
        )

    existing = {course.code for course in (await db.exec(select(Course))).all()}
    created: list[str] = []
    skipped: list[str] = []
    for item in body.cursos:
        if item.code in existing:
            skipped.append(item.code)
            continue
        db.add(Course(code=item.code, name=item.name, cycle=item.cycle))
        created.append(item.code)

    await audit(
        db, admin, action="importacion_malla_confirmada", entity="course",
        new_value={"creados": len(created), "omitidos": len(skipped), "codigos": created},
        ip_address=_client_ip(request),
    )
    await db.commit()
    return CurriculumConfirmOut(
        creados=len(created),
        omitidos=len(skipped),
        codigos_creados=created,
        codigos_omitidos=skipped,
        total=len(body.cursos),
    )
