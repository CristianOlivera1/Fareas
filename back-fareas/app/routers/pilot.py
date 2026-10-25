import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import select

from app.ai.frame_source import open_source
from app.ai.runtime import detector, embedder, gallery, recargar_galeria
from app.core.deps import DbSession, RequireRole
from app.services import go2rtc, pilot
from app.services.settings import get_settings_row
from app.tables import Device, UserRole

logger = logging.getLogger("fareas.pilot")
router = APIRouter(tags=["pilot"])
_busy = asyncio.Lock()


class CaptureIn(BaseModel):
    student_id: int | None = None
    condition: Literal["normal", "adversa"] = "normal"
    seconds: int = Field(default=10, ge=3, le=30)


class CaptureOut(BaseModel):
    capture_id: str
    frames: int
    alias: str
    condition: str


class PilotStudentOut(BaseModel):
    id: int
    code: str | None
    name: str
    alias: str
    normal: int
    adversa: int


class PilotStatusOut(BaseModel):
    camera_room: str | None
    students: list[PilotStudentOut]
    captures: int
    unenrolled_captures: int
    tar: dict
    frr: dict
    misidentified: dict
    far: dict
    curve: list[dict]


async def _pick_camera(db, room_id: int | None) -> tuple[Device, str] | None:
    settings_row = await get_settings_row(db)
    wanted = room_id if room_id is not None else getattr(settings_row, "live_room_id", None)
    rows = (
        await db.exec(
            text(
                "select d.id, r.code from device d join room r on r.id = d.room_id "
                "where d.device_type = 'camara' and d.is_active and d.rtsp_url is not null "
                "order by (d.room_id = :wanted) desc nulls last, d.is_online desc, d.last_heartbeat desc nulls last limit 1"
            ).bindparams(wanted=wanted)
        )
    ).first()
    if rows is None:
        return None
    camera = (await db.exec(select(Device).where(Device.id == rows[0]))).first()
    return camera, rows[1]


async def _enrolled_students(db) -> list[dict]:
    await recargar_galeria(db)
    ids = gallery().student_ids
    if not ids:
        return []
    aliases = pilot.alias_map(ids)
    rows = (
        await db.exec(text("select id, code, full_name from app_user where id = any(:ids)").bindparams(ids=list(ids)))
    ).all()
    return [
        {"id": row[0], "code": row[1], "name": row[2], "alias": aliases[row[0]]}
        for row in sorted(rows, key=lambda r: aliases[r[0]])
    ]


@router.get("/pilot/status", response_model=PilotStatusOut)
async def pilot_status(
    db: DbSession,
    _admin: RequireRole(UserRole.ADMIN),
    threshold: float = Query(0.55, ge=0.1, le=1.0),
    margin: float = Query(0.06, ge=0.0, le=0.5),
    confirm: int = Query(3, ge=1, le=10),
) -> PilotStatusOut:
    students = await _enrolled_students(db)
    summary = pilot.summarize(threshold, margin, confirm)
    camera = await _pick_camera(db, None)
    return PilotStatusOut(
        camera_room=camera[1] if camera else None,
        students=[
            PilotStudentOut(**s, **summary["per_alias"].get(s["alias"], {"normal": 0, "adversa": 0}))
            for s in students
        ],
        captures=summary["captures"],
        unenrolled_captures=summary["unenrolled_captures"],
        tar=summary["tar"],
        frr=summary["frr"],
        misidentified=summary["misidentified"],
        far=summary["far"],
        curve=summary["curve"],
    )


@router.post("/pilot/captures", response_model=CaptureOut, status_code=201)
async def pilot_capture(
    payload: CaptureIn,
    db: DbSession,
    _admin: RequireRole(UserRole.ADMIN),
) -> CaptureOut:
    if _busy.locked():
        raise HTTPException(status_code=409, detail="Ya hay una captura en curso")
    async with _busy:
        students = await _enrolled_students(db)
        if not students:
            raise HTTPException(status_code=422, detail="No hay estudiantes enrolados")
        aliases = pilot.alias_map(gallery().student_ids)
        if payload.student_id is None:
            true_alias, condition = pilot.NON_ENROLLED, "no_enrolado"
        else:
            if payload.student_id not in aliases:
                raise HTTPException(status_code=422, detail="El estudiante no está enrolado")
            true_alias, condition = aliases[payload.student_id], payload.condition
        camera = await _pick_camera(db, None)
        if camera is None:
            raise HTTPException(status_code=404, detail="No hay una cámara activa con RTSP")
        device, _room = camera
        url = await go2rtc.fuente_para_deteccion(device.room_id, device.rtsp_url)
        try:
            source = await asyncio.to_thread(open_source, url)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="No se pudo abrir el stream de la cámara") from exc
        try:
            result = await asyncio.to_thread(
                pilot.run_capture, source, detector(), embedder(), gallery(), aliases,
                true_alias, condition, payload.seconds,
            )
        except pilot.PilotCaptureError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            await asyncio.to_thread(source.release)
    return CaptureOut(**result)


@router.get("/pilot/export")
async def pilot_export(_admin: RequireRole(UserRole.ADMIN)) -> FileResponse:
    path = pilot.data_file()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Aún no hay capturas del piloto")
    return FileResponse(path, media_type="text/csv", filename="pilot_data.csv")


@router.delete("/pilot/data", status_code=204)
async def pilot_reset(_admin: RequireRole(UserRole.ADMIN)) -> None:
    path = pilot.data_file()
    if path.exists():
        path.unlink()
