from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings
from app.services import errors
from app.services.accounts import create_account
from app.services.audit import audit
from app.services.enrollments import matricular
from app.services.ocr_extract import DocumentoLeido, leer_documento_async
from app.services.ocr_roster import (
    DOMINIO_POR_DEFECTO,
    MAX_FILAS,
    AlumnoExtraido,
    parsear_nomina,
    validar_alumno,
)
from app.services.settings import semestre_vigente
from app.services.spreadsheet_roster import is_spreadsheet, read_spreadsheet
from app.tables import AppUser, CourseGroup, UserRole


class AlumnoConfirmado(BaseModel):
    fila: int | None = None
    code: str = Field(default="", max_length=20)
    dni: str = Field(default="", max_length=20)
    full_name: str = Field(default="", max_length=200)
    email: str | None = Field(default=None, max_length=160)
    semester: int | None = None
    whatsapp: str | None = Field(default=None, max_length=20)


class ImportacionAlumnosIn(BaseModel):
    alumnos: list[AlumnoConfirmado] = Field(min_length=1, max_length=MAX_FILAS)
    group_id: int | None = Field(default=None, description="Matrícula opcional en un grupo")


class ErrorImportacion(BaseModel):
    fila: int
    code: str | None = None
    motivo: str


class ImportacionAlumnosOut(BaseModel):
    creados: int
    omitidos: int
    matriculados: int
    total: int
    errores: list[ErrorImportacion]


class ImportacionAlumnosPreviewOut(BaseModel):
    tipo: str
    paginas: int
    total: int
    listos: int
    con_error: int
    alumnos: list[AlumnoExtraido]


def _dominio() -> str:
    return get_settings().ALLOWED_EMAIL_DOMAIN.strip().lower() or DOMINIO_POR_DEFECTO


async def _marcar_duplicados(db: SQLModelAsyncSession, alumnos: list[AlumnoExtraido]) -> None:
    codigos = {alumno.code for alumno in alumnos if alumno.code}
    dnis = {alumno.dni for alumno in alumnos if alumno.dni}
    correos = {alumno.email for alumno in alumnos if alumno.email}
    condiciones = []
    if codigos:
        condiciones.append(AppUser.code.in_(codigos))
    if dnis:
        condiciones.append(AppUser.dni.in_(dnis))
    if correos:
        condiciones.append(AppUser.email.in_(correos))
    if not condiciones:
        return

    usuarios = (await db.exec(select(AppUser).where(or_(*condiciones)))).all()
    por_codigo = {usuario.code: usuario for usuario in usuarios if usuario.code}
    por_dni = {usuario.dni: usuario for usuario in usuarios if usuario.dni}
    por_correo = {usuario.email.lower(): usuario for usuario in usuarios if usuario.email}

    for alumno in alumnos:
        if alumno.code and alumno.code in por_codigo:
            alumno.duplicado = True
            alumno.errores.append(f"Ya existe una cuenta con el código {alumno.code}")
        if alumno.dni and alumno.dni in por_dni:
            alumno.errores.append(f"El DNI {alumno.dni} ya está registrado")
        if alumno.email and alumno.email.lower() in por_correo:
            alumno.errores.append(f"El correo {alumno.email} ya está registrado")
        if alumno.errores:
            alumno.errores = list(dict.fromkeys(alumno.errores))
            alumno.confiable = False


async def preview_nomina(
    db: SQLModelAsyncSession,
    raw: bytes,
    filename: str | None,
    default_semester: int,
) -> tuple[DocumentoLeido, list[AlumnoExtraido]]:
    if is_spreadsheet(raw, filename):
        hoja = read_spreadsheet(
            raw, filename, default_semester=default_semester, domain=_dominio()
        )
        documento = DocumentoLeido(tipo=hoja.kind, paginas=hoja.sheets, items=[], lineas=[])
        await _marcar_duplicados(db, hoja.students)
        return documento, hoja.students
    documento = await leer_documento_async(raw, filename)
    alumnos = parsear_nomina(documento, default_semester=default_semester, dominio_email=_dominio())
    if not alumnos and documento.tipo == "pdf_texto":
        documento = await leer_documento_async(raw, filename, forzar_ocr=True)
        alumnos = parsear_nomina(documento, default_semester=default_semester, dominio_email=_dominio())
    await _marcar_duplicados(db, alumnos)
    return documento, alumnos


async def _matricular_si_corresponde(
    db: SQLModelAsyncSession, actor: AppUser, *, group_id: int | None, student_id: int
) -> str | None:
    if group_id is None:
        return None
    try:
        await matricular(db, actor, group_id=group_id, student_id=student_id)
        return None
    except errors.DomainError as exc:
        return str(exc)
    except Exception:
        await db.rollback()
        await db.refresh(actor)
        return "No se pudo matricular en el grupo seleccionado"


async def confirmar_nomina(
    db: SQLModelAsyncSession,
    actor: AppUser,
    body: ImportacionAlumnosIn,
    *,
    ip: str | None = None,
) -> ImportacionAlumnosOut:
    if body.group_id is not None:
        grupo = await db.get(CourseGroup, body.group_id)
        if grupo is None or not grupo.is_active:
            raise errors.NotFoundError("Grupo de matrícula no encontrado o inactivo")
        if grupo.semester_label != await semestre_vigente(db):
            raise errors.DomainError("El grupo de matrícula no pertenece al semestre vigente")

    creados = 0
    omitidos = 0
    matriculados = 0
    errores: list[ErrorImportacion] = []
    vistos_codigo: set[str] = set()
    vistos_dni: set[str] = set()
    vistos_email: set[str] = set()

    for indice, fila in enumerate(body.alumnos, start=1):
        alumno = AlumnoExtraido(
            fila=fila.fila or indice,
            code=fila.code,
            dni=fila.dni or None,
            full_name=fila.full_name,
            email=fila.email,
            semester=fila.semester,
            whatsapp=fila.whatsapp,
        )
        validar_alumno(
            alumno,
            default_semester=None,
            dominio=_dominio(),
            vistos_codigo=vistos_codigo,
            vistos_dni=vistos_dni,
            vistos_email=vistos_email,
        )
        if alumno.errores:
            errores.append(
                ErrorImportacion(fila=alumno.fila, code=alumno.code, motivo="; ".join(alumno.errores))
            )
            continue

        existente = (
            await db.exec(select(AppUser).where(AppUser.code == alumno.code))
        ).first()
        if existente is not None:
            if existente.role is not UserRole.ESTUDIANTE:
                errores.append(
                    ErrorImportacion(
                        fila=alumno.fila,
                        code=alumno.code,
                        motivo="El código pertenece a una cuenta que no es de estudiante",
                    )
                )
                continue
            omitidos += 1
            motivo = await _matricular_si_corresponde(
                db, actor, group_id=body.group_id, student_id=existente.id
            )
            if motivo:
                errores.append(
                    ErrorImportacion(
                        fila=alumno.fila,
                        code=alumno.code,
                        motivo=f"El alumno ya existía, pero no se matriculó: {motivo}",
                    )
                )
            else:
                matriculados += 1 if body.group_id is not None else 0
            continue

        coincidencias = [AppUser.email == alumno.email]
        if alumno.dni:
            coincidencias.append(AppUser.dni == alumno.dni)
        conflicto = (await db.exec(select(AppUser).where(or_(*coincidencias)))).first()
        if conflicto is not None:
            campo = "DNI" if alumno.dni and conflicto.dni == alumno.dni else "correo"
            errores.append(
                ErrorImportacion(
                    fila=alumno.fila,
                    code=alumno.code,
                    motivo=f"El {campo} ya está registrado en otra cuenta",
                )
            )
            continue

        try:
            usuario = await create_account(
                db,
                actor,
                role=UserRole.ESTUDIANTE,
                full_name=alumno.full_name or "",
                email=alumno.email or "",
                dni=alumno.dni,
                code=alumno.code,
                semester=alumno.semester,
                whatsapp=alumno.whatsapp,
                ip=ip,
            )
        except (errors.DomainError, ValueError) as exc:
            errores.append(
                ErrorImportacion(fila=alumno.fila, code=alumno.code, motivo=str(exc))
            )
            continue
        except Exception:
            await db.rollback()
            await db.refresh(actor)
            errores.append(
                ErrorImportacion(
                    fila=alumno.fila,
                    code=alumno.code,
                    motivo="No se pudo crear la cuenta",
                )
            )
            continue

        creados += 1
        motivo = await _matricular_si_corresponde(
            db, actor, group_id=body.group_id, student_id=usuario.id
        )
        if motivo:
            errores.append(
                ErrorImportacion(
                    fila=alumno.fila,
                    code=alumno.code,
                    motivo=f"Cuenta creada, pero no se matriculó: {motivo}",
                )
            )
        elif body.group_id is not None:
            matriculados += 1

    await audit(
        db,
        actor,
        action="importacion_alumnos_confirmada",
        entity="app_user",
        new_value={
            "creados": creados,
            "omitidos": omitidos,
            "matriculados": matriculados,
            "errores": len(errores),
        },
        ip_address=ip,
    )
    await db.commit()
    return ImportacionAlumnosOut(
        creados=creados,
        omitidos=omitidos,
        matriculados=matriculados,
        total=len(body.alumnos),
        errores=errores,
    )
