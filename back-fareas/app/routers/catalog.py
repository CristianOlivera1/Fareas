from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlmodel import func, select

from app.core.deps import DbSession, RequireRole
from app.core.pagination import PageParams, PageParamsDep
from app.schemas.common import Page
from app.services.accounts import create_account, resend_credentials
from app.services.audit import audit
from app.services.formats import validar_whatsapp
from app.services.ocr_extract import MAX_PESO_ARCHIVO
from app.services.students_import import (
    ImportacionAlumnosIn,
    ImportacionAlumnosOut,
    ImportacionAlumnosPreviewOut,
    confirmar_nomina,
    preview_nomina,
)
from app.tables import AppUser, Device, DeviceType, FaceEmbedding, Room, UserRole

router = APIRouter(tags=["catalog"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None

async def _get_or_404(db, model, entity_id: int, name: str):
    obj = await db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} no encontrado")
    return obj

class RoomIn(BaseModel):
    code: str = Field(min_length=1, max_length=20, examples=["LAB 304"])
    name: str | None = Field(default=None, max_length=120)
    building: str | None = Field(default=None, max_length=80)
    capacity: int | None = Field(default=None, gt=0, description="Aforo informativo (R9)")

class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    building: str | None = Field(default=None, max_length=80)
    capacity: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

class RoomOut(BaseModel):
    id: int
    code: str
    name: str | None
    building: str | None
    capacity: int | None
    is_active: bool

def room_out(r: Room) -> RoomOut:
    return RoomOut(
        id=r.id, code=r.code, name=r.name, building=r.building,
        capacity=r.capacity, is_active=r.is_active,
    )

@router.get("/rooms", response_model=Page[RoomOut])
async def list_rooms(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    q: str | None = Query(None, max_length=40, description="Filtra por código o nombre"),
) -> Page[RoomOut]:
    stmt = select(Room)
    count_stmt = select(func.count()).select_from(Room)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Room.code.ilike(like) | Room.name.ilike(like))
        count_stmt = count_stmt.where(Room.code.ilike(like) | Room.name.ilike(like))
    total = (await db.exec(count_stmt)).one()
    rooms = (await db.exec(stmt.order_by(Room.code).offset(page.offset).limit(page.limit))).all()
    return Page(items=[room_out(r) for r in rooms], total=total, page=page.page, page_size=page.page_size)

@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: RoomIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> RoomOut:
    code = body.code.strip().upper()
    if (await db.exec(select(Room).where(Room.code == code))).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El aula '{code}' ya existe")
    room = Room(code=code, name=body.name, building=body.building)
    db.add(room)
    await db.flush()
    await audit(db, admin, action="aula_creada", entity="room", entity_id=room.id,
                new_value={"code": code, "name": body.name}, ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(room)
    return room_out(room)

@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int, body: RoomUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> RoomOut:
    room = await _get_or_404(db, Room, room_id, "Aula")
    old = {"code": room.code, "name": room.name, "building": room.building, "is_active": room.is_active}
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(room, field, value)
    db.add(room)
    await audit(db, admin, action="aula_actualizada", entity="room", entity_id=room.id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(room)
    return room_out(room)

class DeviceIn(BaseModel):
    room_id: int
    device_type: DeviceType
    device_key: str = Field(min_length=3, max_length=64, examples=["esp32-lab305"])
    name: str | None = Field(default=None, max_length=80)
    rtsp_url: str | None = Field(default=None, max_length=255, description="Solo cámaras")

class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    rtsp_url: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

class DeviceOut(BaseModel):
    id: int
    room_id: int
    room_code: str | None
    device_type: str
    device_key: str
    name: str | None
    ip_address: str | None
    is_online: bool
    last_heartbeat: str | None
    is_active: bool
    rtsp_url: str | None = None

_RTSP_MASK = "***"


def _rtsp_enmascarada(rtsp_url: str | None) -> str | None:
    if not rtsp_url:
        return None
    import re as _re

    return _re.sub(r"(://[^:/@]+):([^@]+)@", rf"\1:{_RTSP_MASK}@", rtsp_url)

def device_out(d: Device, room_code: str | None, *, mask_rtsp: bool = True) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        room_id=d.room_id,
        room_code=room_code,
        device_type=d.device_type.value,
        device_key=d.device_key,
        name=d.name,
        ip_address=d.ip_address,
        is_online=d.is_online,
        last_heartbeat=d.last_heartbeat.isoformat(timespec="seconds") if d.last_heartbeat else None,
        is_active=d.is_active,
        rtsp_url=_rtsp_enmascarada(d.rtsp_url) if mask_rtsp else d.rtsp_url,
    )

@router.get("/devices", response_model=Page[DeviceOut])
async def list_devices(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    room_id: int | None = None,
    device_type: DeviceType | None = None,
) -> Page[DeviceOut]:
    stmt = select(Device, Room.code).join(Room, Room.id == Device.room_id)
    count_stmt = select(func.count()).select_from(Device)
    if room_id is not None:
        stmt = stmt.where(Device.room_id == room_id)
        count_stmt = count_stmt.where(Device.room_id == room_id)
    if device_type is not None:
        stmt = stmt.where(Device.device_type == device_type)
        count_stmt = count_stmt.where(Device.device_type == device_type)
    total = (await db.exec(count_stmt)).one()
    rows = (await db.exec(stmt.order_by(Device.device_key).offset(page.offset).limit(page.limit))).all()
    return Page(
        items=[device_out(d, rc) for d, rc in rows], total=total, page=page.page, page_size=page.page_size
    )

@router.get("/devices/status", response_model=list[DeviceOut])
async def devices_status(db: DbSession) -> list[DeviceOut]:
    rows = (
        await db.exec(
            select(Device, Room.code)
            .join(Room, Room.id == Device.room_id)
            .where(Device.is_active)
            .order_by(Device.is_online.desc(), Device.device_key)
        )
    ).all()
    return [device_out(d, rc) for d, rc in rows]

@router.get("/devices/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: int, db: DbSession, _admin: RequireRole(UserRole.ADMIN)
) -> DeviceOut:
    device = await _get_or_404(db, Device, device_id, "Dispositivo")
    room = await db.get(Room, device.room_id)
    return device_out(device, room.code if room else None, mask_rtsp=False)

@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> DeviceOut:
    await _get_or_404(db, Room, body.room_id, "Aula")
    key = body.device_key.strip().lower()
    if (await db.exec(select(Device).where(Device.device_key == key))).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El device_key '{key}' ya existe")
    if body.device_type is DeviceType.CAMARA and not body.rtsp_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Una cámara requiere su rtsp_url (Streaming/Channels/102 recomendado)",
        )
    device = Device(room_id=body.room_id, device_type=body.device_type, device_key=key,
                    name=body.name, rtsp_url=body.rtsp_url)
    db.add(device)
    await db.flush()
    await audit(db, admin, action="dispositivo_creado", entity="device", entity_id=device.id,
                new_value={"device_key": key, "room_id": body.room_id, "type": body.device_type.value},
                ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(device)
    room = await db.get(Room, device.room_id)
    return device_out(device, room.code if room else None)

@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int, body: DeviceUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> DeviceOut:
    device = await _get_or_404(db, Device, device_id, "Dispositivo")
    old = {"name": device.name, "rtsp_url": _rtsp_enmascarada(device.rtsp_url), "is_active": device.is_active}
    data = body.model_dump(exclude_unset=True)

    if "rtsp_url" in data and data["rtsp_url"] and _RTSP_MASK in data["rtsp_url"]:
        data.pop("rtsp_url")
    for field, value in data.items():
        setattr(device, field, value)
    db.add(device)
    await audit(db, admin, action="dispositivo_actualizado", entity="device", entity_id=device.id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(device)
    room = await db.get(Room, device.room_id)
    return device_out(device, room.code if room else None)

class TeacherIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=160, examples=["Aquino Cruz, Mario (Mag.)"])
    email: EmailStr
    dni: str = Field(pattern=r"^\d{8}$")
    whatsapp: str | None = Field(default=None, max_length=20)

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp_pe(cls, v: str | None) -> str | None:
        try:
            return validar_whatsapp(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

class PersonUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=160)
    whatsapp: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    semester: int | None = Field(default=None, ge=1, le=12)

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp_pe(cls, v: str | None) -> str | None:
        try:
            return validar_whatsapp(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

class PersonOut(BaseModel):
    id: int
    role: str
    full_name: str
    email: str
    dni: str | None
    code: str | None
    whatsapp: str | None
    semester: int | None
    is_active: bool
    must_change_password: bool
    enrolled: bool | None = None

def person_out(u: AppUser) -> PersonOut:
    return PersonOut(
        id=u.id,
        role=u.role.value,
        full_name=u.full_name,
        email=u.email,
        dni=u.dni,
        code=u.code,
        whatsapp=u.whatsapp,
        semester=u.semester,
        is_active=u.is_active,
        must_change_password=u.must_change_password,
    )

def _people_stmt(role: UserRole, q: str | None):
    stmt = select(AppUser).where(AppUser.role == role)
    count_stmt = select(func.count()).select_from(AppUser).where(AppUser.role == role)
    if q:
        like = f"%{q}%"
        cond = AppUser.full_name.ilike(like) | AppUser.email.ilike(like)
        if role is UserRole.ESTUDIANTE:
            cond = cond | AppUser.code.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    return stmt, count_stmt

async def _paged_people(db, role: UserRole, page: PageParams, q: str | None) -> Page[PersonOut]:
    stmt, count_stmt = _people_stmt(role, q)
    total = (await db.exec(count_stmt)).one()
    people = (
        await db.exec(stmt.order_by(AppUser.full_name).offset(page.offset).limit(page.limit))
    ).all()
    return Page(items=[person_out(p) for p in people], total=total, page=page.page, page_size=page.page_size)

@router.get("/teachers", response_model=Page[PersonOut])
async def list_teachers(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    q: str | None = Query(None, max_length=80),
) -> Page[PersonOut]:
    return await _paged_people(db, UserRole.DOCENTE, page, q)

@router.post("/teachers", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    body: TeacherIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> PersonOut:
    user = await create_account(
        db, admin, role=UserRole.DOCENTE, full_name=body.full_name, email=body.email.lower(),
        dni=body.dni, whatsapp=body.whatsapp, ip=_client_ip(request),
    )
    return person_out(user)

class StudentIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=160)
    email: EmailStr
    dni: str = Field(pattern=r"^\d{8}$")
    code: str = Field(pattern=r"^\d{6}$", description="Código de matrícula")
    semester: int = Field(ge=1, le=12, description="Ciclo actual")
    whatsapp: str | None = Field(default=None, max_length=20)

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp_pe(cls, v: str | None) -> str | None:
        try:
            return validar_whatsapp(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

@router.get("/students", response_model=Page[PersonOut])
async def list_students(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    page: PageParamsDep,
    q: str | None = Query(None, max_length=80),
    semester: int | None = Query(None, ge=1, le=12),
    with_face: bool = Query(False, description="Incluye enrolled (rostro actual RF-04)"),
) -> Page[PersonOut]:
    stmt, count_stmt = _people_stmt(UserRole.ESTUDIANTE, q)
    if semester is not None:
        stmt = stmt.where(AppUser.semester == semester)
        count_stmt = count_stmt.where(AppUser.semester == semester)
    total = (await db.exec(count_stmt)).one()
    students = (
        await db.exec(stmt.order_by(AppUser.full_name).offset(page.offset).limit(page.limit))
    ).all()
    enrolled_ids: set[int] = set()
    if with_face and students:
        ids = [s.id for s in students]
        filas = (
            await db.exec(
                select(FaceEmbedding.student_id).where(
                    FaceEmbedding.student_id.in_(ids),
                    FaceEmbedding.is_current,
                )
            )
        ).all()
        enrolled_ids = {r[0] if isinstance(r, tuple) else r for r in filas}
    items = [
        PersonOut(
            id=s.id,
            role=s.role.value,
            full_name=s.full_name,
            email=s.email,
            dni=s.dni,
            code=s.code,
            whatsapp=s.whatsapp,
            semester=s.semester,
            is_active=s.is_active,
            must_change_password=s.must_change_password,
            enrolled=(s.id in enrolled_ids) if with_face else None,
        )
        for s in students
    ]
    return Page(items=items, total=total, page=page.page, page_size=page.page_size)

@router.post("/students", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
async def create_student(
    body: StudentIn, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> PersonOut:
    user = await create_account(
        db, admin, role=UserRole.ESTUDIANTE, full_name=body.full_name, email=body.email.lower(),
        dni=body.dni, code=body.code, semester=body.semester, whatsapp=body.whatsapp,
        ip=_client_ip(request),
    )
    return person_out(user)

@router.post("/students/import-preview", response_model=ImportacionAlumnosPreviewOut)
async def students_import_preview(
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
    file: Annotated[UploadFile, File(description="Nómina en PDF, JPG, PNG o WEBP")],
    default_semester: Annotated[int, Form(ge=1, le=12)] = 1,
) -> ImportacionAlumnosPreviewOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="El archivo está vacío")
    if len(raw) > MAX_PESO_ARCHIVO:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="El archivo supera el máximo de 10 MB")
    try:
        documento, alumnos = await preview_nomina(db, raw, file.filename, default_semester)
    except ValueError as exc:
        detalle = str(exc)
        codigo = (status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
                  if detalle.startswith("Formato no soportado") else
                  status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(status_code=codigo, detail=detalle) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="No se pudo leer la nómina; ¿es una tabla impresa válida?") from exc
    if not alumnos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=("No se detectaron filas con código y nombre. Revisa que sea una nómina "
                    "impresa en tabla, derecha y con buena luz, o registra a los alumnos a mano."),
        )
    await audit(db, admin, action="importacion_alumnos_preview", entity="app_user",
                new_value={"archivo": file.filename, "tipo": documento.tipo,
                           "paginas": documento.paginas, "filas": len(alumnos)},
                ip_address=_client_ip(request))
    await db.commit()
    listos = sum(1 for alumno in alumnos if alumno.confiable and not alumno.errores)
    con_error = sum(1 for alumno in alumnos if alumno.errores)
    return ImportacionAlumnosPreviewOut(
        tipo=documento.tipo,
        paginas=documento.paginas,
        total=len(alumnos),
        listos=listos,
        con_error=con_error,
        alumnos=alumnos,
    )

@router.post("/students/import-confirm", response_model=ImportacionAlumnosOut)
async def students_import_confirm(
    body: ImportacionAlumnosIn, request: Request, db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> ImportacionAlumnosOut:
    return await confirmar_nomina(db, admin, body, ip=_client_ip(request))

@router.get("/accounts/{user_id}", response_model=PersonOut)
async def get_account(
    user_id: int, db: DbSession, _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)
) -> PersonOut:
    return person_out(await _get_or_404(db, AppUser, user_id, "Cuenta"))

@router.patch("/accounts/{user_id}", response_model=PersonOut)
async def update_account(
    user_id: int, body: PersonUpdate, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> PersonOut:
    user = await _get_or_404(db, AppUser, user_id, "Cuenta")
    if user.role is UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La cuenta admin se gestiona por BD")
    old = {"full_name": user.full_name, "whatsapp": user.whatsapp, "is_active": user.is_active,
           "semester": user.semester}
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    await audit(db, admin, action="cuenta_actualizada", entity="app_user", entity_id=user.id,
                old_value=old, ip_address=_client_ip(request))
    await db.commit()
    await db.refresh(user)
    return person_out(user)

@router.post("/accounts/{user_id}/send-temp-password")
async def account_send_temp_password(
    user_id: int, request: Request, db: DbSession, admin: RequireRole(UserRole.ADMIN)
) -> dict:
    result = await resend_credentials(db, admin, user_id, ip=_client_ip(request))
    return {"message": result.message}
