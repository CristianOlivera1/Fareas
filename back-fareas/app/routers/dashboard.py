import asyncio
import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app.core.deps import DbSession, RequireRole
from app.core.security import decode_access_token
from app.database import SessionLocal
from app.routers.dpi import TEACHER_SCOPE
from app.services.course_groups import full_courses
from app.services.camera_loop import todos_los_veredictos
from app.services import go2rtc
from app.services.camera_stream import (
    BOUNDARY,
    StreamBusy,
    StreamUnavailable,
    face_events,
    mjpeg_frames,
)
from app.tables import AppSettings, AppUser, Device, DeviceType, UserRole

logger = logging.getLogger("fareas.dashboard")
router = APIRouter(tags=["dashboard"])

class Summary(BaseModel):
    asistencias_hoy: int
    tardanzas_hoy: int
    ausencias_hoy: int
    total_marcas_hoy: int
    pct_ausentismo: float
    camaras_total: int
    camaras_activas: int
    streams_caidos: int
    alertas_dpi: int
    en_riesgo: int
    sessions_to_review: int
    cursos_llenos: int = 0
    at: str

async def _contar_marcas_hoy(db, teacher_id: int | None = None) -> dict:
    sql = (
        "SELECT ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "JOIN schedule_block sb ON sb.id = s.block_id "
        "JOIN course_group cg ON cg.id = sb.group_id "
        "WHERE s.session_date = CURRENT_DATE AND s.status <> 'cancelada'"
    )
    if teacher_id is not None:
        sql += " AND cg.teacher_id = :docente"
    sql += " GROUP BY ar.status"
    stmt = sql_text(sql)
    rows = (
        (await db.exec(stmt.bindparams(docente=teacher_id))).all()
        if teacher_id is not None
        else (await db.exec(stmt)).all()
    )
    conteo = {r[0]: r[1] for r in rows}
    asistio = conteo.get("asistio", 0)
    tardanza = conteo.get("tardanza", 0)
    falta = conteo.get("falta", 0)
    total = asistio + tardanza + falta
    return {
        "asistencias": asistio,
        "tardanzas": tardanza,
        "ausencias": falta,
        "total": total,
        "pct": round(falta * 100.0 / total, 1) if total else 0.0,
    }

async def _contar_camaras(db) -> dict:
    sql = (
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE is_online) "
        "FROM device WHERE is_active AND device_type = 'camara'"
    )
    total, activas = (await db.exec(sql_text(sql))).one()
    return {"total": total, "activas": activas}

async def _contar_alertas_dpi(db, docente_id: int | None = None) -> dict:
    cfg = await db.get(AppSettings, 1)
    alerta, limite = 20.0, 30.0
    if cfg is not None:
        alerta, limite = float(cfg.dpi_alert_percent), float(cfg.dpi_limit_percent)
    sql = "SELECT COUNT(*) FROM v_student_dpi v WHERE v.absence_percent > :limite"
    params: dict = {"limite": limite}
    if docente_id is not None:
        sql += TEACHER_SCOPE
        params["docente"] = docente_id
    limite_n = (await db.exec(sql_text(sql).bindparams(**params))).scalar_one()
    sql_riesgo = sql.replace("v.absence_percent > :limite", "v.absence_percent >= :alerta")
    params2 = dict(params, alerta=alerta)
    sql_riesgo += " AND v.absence_percent <= :limite"
    en_riesgo = (await db.exec(sql_text(sql_riesgo).bindparams(**params2))).scalar_one()
    return {"limite": limite_n, "en_riesgo": en_riesgo}

async def _contar_por_revisar(db, teacher_id: int | None = None) -> int:
    sql = (
        "SELECT COUNT(*) FROM attendance_session s "
        "JOIN schedule_block sb ON sb.id = s.block_id "
        "JOIN course_group cg ON cg.id = sb.group_id "
        "WHERE s.needs_review AND s.status = 'cerrada'"
    )
    if teacher_id is not None:
        sql += " AND cg.teacher_id = :docente"
        return (await db.exec(sql_text(sql).bindparams(docente=teacher_id))).scalar_one()
    return (await db.exec(sql_text(sql))).scalar_one()

@router.get("/dashboard/summary", response_model=Summary)
async def summary(db: DbSession, user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)) -> Summary:
    docente_id = user.id if user.role is UserRole.DOCENTE else None
    marcas = await _contar_marcas_hoy(db, docente_id)
    camaras = await _contar_camaras(db)
    alertas = await _contar_alertas_dpi(db, docente_id)
    por_revisar = await _contar_por_revisar(db, docente_id)
    return Summary(
        asistencias_hoy=marcas["asistencias"],
        tardanzas_hoy=marcas["tardanzas"],
        ausencias_hoy=marcas["ausencias"],
        total_marcas_hoy=marcas["total"],
        pct_ausentismo=marcas["pct"],
        camaras_total=camaras["total"],
        camaras_activas=camaras["activas"],
        streams_caidos=camaras["total"] - camaras["activas"],
        alertas_dpi=alertas["limite"],
        en_riesgo=alertas["en_riesgo"],
        sessions_to_review=por_revisar,
        cursos_llenos=len(await full_courses(db)) if docente_id is None else 0,
        at=datetime.now().isoformat(timespec="seconds"),
    )

async def _usuario_de_token(access_token: str) -> AppUser:
    try:
        payload = decode_access_token(access_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido o expirado") from exc
    async with SessionLocal() as db:
        user = (await db.exec(select(AppUser).where(AppUser.id == payload.user_id))).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inexistente o inactivo")
    if payload.token_version != user.token_version:
        raise HTTPException(status_code=401, detail="Sesión invalidada. Inicia sesión nuevamente.")
    if user.must_change_password:
        raise HTTPException(status_code=403, detail={
            "code": "must_change_password",
            "message": "Cambia tu clave temporal antes de usar el sistema",
        })
    if user.role not in (UserRole.ADMIN, UserRole.DOCENTE):
        raise HTTPException(status_code=403, detail="No tienes permisos para esta operación")
    return user

@router.get("/dashboard/live")
async def dashboard_live(
    access_token: str = Query(..., min_length=10),
    room_id: int | None = Query(None, description="Filtra por aula"),
) -> EventSourceResponse:
    await _usuario_de_token(access_token)

    async def generador():
        ultimo_enviado: dict[int, str] = {}
        try:
            while True:
                for v in todos_los_veredictos():
                    if room_id is not None and v.get("room_id") != room_id:
                        continue
                    ts = str(v.get("ts", ""))
                    if ultimo_enviado.get(v.get("room_id")) != ts:
                        ultimo_enviado[v.get("room_id")] = ts
                        yield {"event": "verdict", "data": json.dumps(v, ensure_ascii=False)}
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        finally:
            logger.info("Cliente SSE desconectado (room_id=%s)", room_id)

    return EventSourceResponse(generador(), ping=15)

@router.get("/dashboard/live-room/{room_id}")
async def dashboard_live_room(
    room_id: int,
    access_token: str = Query(..., min_length=10),
) -> EventSourceResponse:
    return await dashboard_live(access_token=access_token, room_id=room_id)

async def _camara_activa(room_id: int) -> Device:
    async with SessionLocal() as db:
        camara = (
            await db.exec(
                select(Device).where(
                    Device.room_id == room_id,
                    Device.device_type == DeviceType.CAMARA,
                    Device.is_active,
                    Device.rtsp_url.is_not(None),
                )
            )
        ).first()
    if camara is None or not camara.rtsp_url:
        raise HTTPException(status_code=404, detail="El aula no tiene una cámara activa con RTSP")
    return camara


class SdpIn(BaseModel):
    type: str = Field(pattern="^offer$")
    sdp: str = Field(min_length=10, max_length=20000)


@router.post("/dashboard/camera/{room_id}/webrtc")
async def dashboard_camera_webrtc(
    room_id: int,
    oferta: SdpIn,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    camara = await _camara_activa(room_id)
    try:
        await go2rtc.registrar(room_id, camara.rtsp_url)
        return await go2rtc.responder_oferta(room_id, oferta.model_dump())
    except go2rtc.Go2rtcUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/dashboard/camera/{room_id}/faces")
async def dashboard_camera_faces(
    room_id: int,
    access_token: str = Query(..., min_length=10),
) -> EventSourceResponse:
    await _usuario_de_token(access_token)
    camara = await _camara_activa(room_id)
    fuente = await go2rtc.fuente_para_deteccion(room_id, camara.rtsp_url)

    async def generador():
        try:
            async for evento in face_events(room_id, fuente):
                yield {"event": "faces", "data": json.dumps(evento)}
        except (StreamBusy, StreamUnavailable):
            return

    return EventSourceResponse(generador(), ping=15)


@router.get("/dashboard/camera/{room_id}/mjpeg")
async def dashboard_camera(
    room_id: int,
    access_token: str = Query(..., min_length=10),
) -> StreamingResponse:
    await _usuario_de_token(access_token)
    camara = await _camara_activa(room_id)
    fuente = await go2rtc.fuente_para_deteccion(room_id, camara.rtsp_url)
    frames = mjpeg_frames(room_id, fuente)
    try:
        primero = await anext(frames)
    except StreamBusy as exc:
        raise HTTPException(status_code=429, detail="Ya hay demasiadas vistas abiertas de esta cámara") from exc
    except StreamUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except StopAsyncIteration as exc:
        raise HTTPException(status_code=502, detail="La cámara no entregó imagen") from exc

    async def cuerpo():
        try:
            yield primero
            async for parte in frames:
                yield parte
        finally:
            await frames.aclose()

    return StreamingResponse(
        cuerpo(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        headers={"Cache-Control": "no-store"},
    )

HORA_INICIO, HORA_FIN = 7, 20


@router.get("/stats/hourly")
async def stats_hourly(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    day: date | None = Query(None, description="Día a consultar (default: hoy)"),
) -> list[dict]:
    dia = day or date.today()
    sql = (
        "SELECT EXTRACT(HOUR FROM sb.start_time)::int AS hora, ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "JOIN schedule_block sb ON sb.id = s.block_id "
        "JOIN course_group cg ON cg.id = sb.group_id "
        "WHERE s.session_date = :dia AND s.status <> 'cancelada' AND NOT s.needs_review"
    )
    params: dict = {"dia": dia}
    if user.role is UserRole.DOCENTE:
        sql += " AND cg.teacher_id = :docente"
        params["docente"] = user.id
    sql += " GROUP BY 1, 2 ORDER BY 1"
    rows = (await db.exec(sql_text(sql).bindparams(**params))).all()
    por_hora: dict[int, dict[str, int]] = {}
    for hora, status_, total in rows:
        h = por_hora.setdefault(int(hora), {"asistio": 0, "tardanza": 0, "falta": 0})
        h[status_] = h.get(status_, 0) + total
    serie = []
    for hora in range(HORA_INICIO, HORA_FIN + 1):
        h = por_hora.get(hora, {"asistio": 0, "tardanza": 0, "falta": 0})
        serie.append({
            "hour": f"{hora:02d}:00",
            "asistio": h["asistio"],
            "tardanza": h["tardanza"],
            "falta": h["falta"],
            "total": sum(h.values()),
        })
    return serie

@router.get("/stats/distribution")
async def stats_distribution(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    desde: date | None = Query(None),
    hasta: date | None = Query(None),
) -> dict:
    hoy = date.today()
    d1, d2 = desde or hoy, hasta or hoy
    if d1 > d2:
        raise HTTPException(status_code=422, detail="'desde' no puede ser mayor que 'hasta'")

    filtro = ""
    params: dict = {"d1": d1, "d2": d2}
    if user.role is UserRole.DOCENTE:
        filtro = " AND cg.teacher_id = :docente"
        params["docente"] = user.id
    sql = (
        "SELECT ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "JOIN schedule_block sb ON sb.id = s.block_id "
        "JOIN course_group cg ON cg.id = sb.group_id "
        "WHERE s.session_date BETWEEN :d1 AND :d2 "
        "AND s.status <> 'cancelada' AND NOT s.needs_review" + filtro +
        " GROUP BY ar.status"
    )
    rows = (await db.exec(sql_text(sql).bindparams(**params))).all()
    out = {"asistio": 0, "tardanza": 0, "falta": 0, "sin_registro": 0}
    for status_, total in rows:
        if status_ in out:
            out[status_] = total

    sql_sin = (
        "SELECT COUNT(*) FROM enrollment e "
        "JOIN course_group cg ON cg.id = e.group_id "
        "JOIN schedule_block sb ON sb.group_id = cg.id "
        "JOIN attendance_session s ON s.block_id = sb.id "
        " AND s.status = 'cerrada' AND NOT s.needs_review "
        " AND s.session_date BETWEEN :d1 AND :d2 "
        "LEFT JOIN attendance_record ar ON ar.session_id = s.id AND ar.student_id = e.student_id "
        "WHERE ar.id IS NULL" + filtro
    )
    out["sin_registro"] = (await db.exec(sql_text(sql_sin).bindparams(**params))).scalar_one()
    return out
