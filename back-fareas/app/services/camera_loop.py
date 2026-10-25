import asyncio
import contextlib
import logging
import socket
import time
from datetime import datetime

from sqlalchemy import update
from sqlmodel import select

from app.ai.runtime import vision_pipeline
from app.database import SessionLocal
from app.services import errors
from app.services.attendance_engine import (
    _naive_peru,
    ahora_peru,
    bloques_candidatos,
    clasificar,
    registrar_marca,
    resolver_sesion,
)
from app.services.settings import get_settings_row
from app.tables import Device, DeviceType, Enrollment

logger = logging.getLogger("fareas.cameras")

FPS_POR_AULA = 2.0

_task: asyncio.Task | None = None
_stop = asyncio.Event()

_ultimo: dict[int, dict] = {}
_ultimo_mono: dict[int, float] = {}
_reintentar_desde: dict[int, float] = {}
_BACKOFF_CAIDA = 60.0
_fuentes: dict[int, object] = {}
_fallos: dict[int, int] = {}


_HEARTBEAT_EVERY_S = 30.0
_last_heartbeat: dict[int, float] = {}


async def _set_camera_state(db, cam: Device, online: bool) -> None:
    if cam.is_online == online and not online:
        return
    cam.is_online = online
    cam.last_heartbeat = datetime.now() if online else cam.last_heartbeat
    db.add(cam)
    await db.commit()
    if online:
        _last_heartbeat[cam.room_id] = time.monotonic()
    else:
        _last_heartbeat.pop(cam.room_id, None)
    logger.info("[RF-35] Cámara %s %s", cam.device_key, "en línea" if online else "fuera de línea")


async def _refresh_heartbeat(db, cam: Device) -> None:
    if time.monotonic() - _last_heartbeat.get(cam.room_id, 0.0) < _HEARTBEAT_EVERY_S:
        return
    cam.is_online = True
    cam.last_heartbeat = datetime.now()
    db.add(cam)
    await db.commit()
    _last_heartbeat[cam.room_id] = time.monotonic()


async def _reset_cameras_offline() -> None:
    async with SessionLocal() as db:
        await db.exec(
            update(Device).where(Device.device_type == DeviceType.CAMARA).values(is_online=False)
        )
        await db.commit()


def ultimo_veredicto(room_id: int) -> dict | None:
    return _ultimo.get(room_id)

def veredicto_reciente(room_id: int, max_age: float = 3.0) -> dict | None:
    marca = _ultimo_mono.get(room_id)
    if marca is None or time.monotonic() - marca > max_age:
        return None
    return _ultimo.get(room_id)

def todos_los_veredictos() -> list[dict]:
    return list(_ultimo.values())

def _rtsp_alcanzable(rtsp_url: str, timeout: float = 2.0) -> bool:
    from urllib.parse import urlparse

    if not rtsp_url.lower().startswith(("rtsp://", "http://", "https://")):
        return True
    try:
        p = urlparse(rtsp_url)
        host, port = p.hostname, p.port or 554
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

async def _abrir_fuente(room_id: int, rtsp_url: str):
    from app.ai.frame_source import open_source

    if not await asyncio.to_thread(_rtsp_alcanzable, rtsp_url):
        return None
    try:
        src = await asyncio.to_thread(open_source, rtsp_url)
    except FileNotFoundError:
        return None
    limite = time.monotonic() + 5.0
    while time.monotonic() < limite:
        ok, frame = await asyncio.to_thread(src.read)
        if ok and frame is not None:
            _fuentes[room_id] = src
            _fallos[room_id] = 0
            return src
        await asyncio.sleep(0.1)
    with contextlib.suppress(Exception):
        await asyncio.to_thread(src.release)
    return None

async def _procesar_aula(pipe, room_id: int) -> None:
    async with SessionLocal() as db:
        cam = (
            await db.exec(
                select(Device).where(
                    Device.room_id == room_id,
                    Device.device_type == DeviceType.CAMARA,
                    Device.is_active,
                )
            )
        ).first()
        if cam is None or not cam.rtsp_url:
            return

        src = _fuentes.get(room_id)
        if src is None:
            if time.monotonic() < _reintentar_desde.get(room_id, 0.0):
                return
            src = await _abrir_fuente(room_id, cam.rtsp_url)
            if src is None:
                _reintentar_desde[room_id] = time.monotonic() + _BACKOFF_CAIDA
                await _set_camera_state(db, cam, False)
                return
            await _set_camera_state(db, cam, True)

        ok, frame = await asyncio.to_thread(src.read)
        if not ok or frame is None:
            _fallos[room_id] = _fallos.get(room_id, 0) + 1
            if _fallos[room_id] >= 5:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(src.release)
                _fuentes.pop(room_id, None)
                _fallos[room_id] = 0
                _reintentar_desde[room_id] = time.monotonic() + _BACKOFF_CAIDA
                await _set_camera_state(db, cam, False)
            return
        _fallos[room_id] = 0
        await _refresh_heartbeat(db, cam)

        cfg = await get_settings_row(db)
        ahora = _naive_peru(ahora_peru())
        hoy = ahora.date()
        pares = await bloques_candidatos(db, room_id, ahora, cfg)
        candidates: set[int] | None = None
        clasificador = None
        bloque_de_alumno: dict[int, object] = {}
        if pares:
            for b, g in pares:
                ids = (
                    await db.exec(
                        select(Enrollment.student_id).where(
                            Enrollment.group_id == g.id,
                            Enrollment.withdrawn_at.is_(None),
                        )
                    )
                ).all()
                for sid in ids:
                    bloque_de_alumno[sid[0] if isinstance(sid, tuple) else sid] = b
            candidates = set(bloque_de_alumno)

            def clasificador(sid: int, _t: float) -> str:
                b = bloque_de_alumno.get(sid)
                if b is None:
                    return "sin_registro"
                estado = clasificar(ahora, b, hoy, cfg)
                return estado or "sin_registro"

        await db.commit()

        pipe.classifier = clasificador
        pipe.threshold = float(cfg.face_match_threshold)
        resultado = pipe.process_frame(frame, candidates=candidates, track_key=room_id)
        _ultimo[room_id] = {
            "room_id": room_id,
            "verdict": resultado.verdict,
            "student_id": resultado.student_id,
            "similarity": round(resultado.similarity, 4),
            "ts": ahora_peru().isoformat(timespec="seconds"),
        }
        _ultimo_mono[room_id] = time.monotonic()

        if resultado.verdict == "denegado" and resultado.student_id is not None and pares:
            from app.tables import CourseGroup as _CG

            cursos_del_aula = [g.course_id for (_b, g) in pares]
            fila = (
                await db.exec(
                    select(_CG.group_code).join(Enrollment, Enrollment.group_id == _CG.id).where(
                        Enrollment.student_id == resultado.student_id,
                        _CG.course_id.in_(cursos_del_aula),
                        Enrollment.withdrawn_at.is_(None),
                    )
                )
            ).first()
            if fila is not None:
                grupo_x = fila[0] if isinstance(fila, tuple) else fila
                resultado.message = f"{resultado.message} (matriculado en el grupo {grupo_x})"

        if resultado.mark is not None:
            sesion_ok, _bloque_ok = await resolver_sesion(
                db, room_id, student_id=resultado.mark["student_id"]
            )
            if sesion_ok is not None:
                try:
                    await registrar_marca(
                        db, sesion_ok, resultado.mark["student_id"],
                        similarity=resultado.mark["similarity"], method="facial",
                    )
                    await db.commit()
                except errors.ConflictError:
                    await db.rollback()

        nodo = (
            await db.exec(
                select(Device.device_key).where(
                    Device.room_id == room_id,
                    Device.device_type == DeviceType.ESP32,
                    Device.is_active,
                )
            )
        ).first()
        device_key = (nodo[0] if isinstance(nodo, tuple) else nodo) if nodo else None
        if device_key:
            from app.routers.ws_devices import enviar_veredicto

            enviado = await enviar_veredicto(device_key, resultado.as_ws_command())
            if not enviado:
                logger.debug("Nodo %s no conectado; veredicto no entregado", device_key)

async def _bucle() -> None:
    pipe = vision_pipeline()
    try:
        from app.ai.runtime import recargar_galeria

        async with SessionLocal() as db:
            n = await recargar_galeria(db)
        logger.info("Galería facial cargada: %s alumnos", n)
    except Exception:
        logger.exception("No se pudo cargar la galería facial; el bucle sigue")

    try:
        await _reset_cameras_offline()
    except Exception:
        logger.exception("No se pudo reiniciar el estado de las cámaras")

    while not _stop.is_set():
        try:
            async with SessionLocal() as db:
                filas = (
                    await db.exec(
                        select(Device.room_id).where(
                            Device.device_type == DeviceType.CAMARA,
                            Device.is_active,
                        )
                    )
                ).all()
            room_ids = [r[0] if isinstance(r, tuple) else r for r in filas]
            if not room_ids:
                await asyncio.sleep(5.0)
                continue
            for room_id in room_ids:
                if _stop.is_set():
                    break
                try:
                    await _procesar_aula(pipe, room_id)
                except Exception:
                    logger.exception("Fallo procesando el aula %s", room_id)
                await asyncio.sleep(1.0 / FPS_POR_AULA)
        except Exception:
            logger.exception("El bucle de cámaras falló; reintenta en 5 s")
            await asyncio.sleep(5.0)

def iniciar_bucle_camaras() -> asyncio.Task:
    global _task
    if _task is not None and not _task.done():
        return _task
    _stop.clear()
    _task = asyncio.create_task(_bucle())
    logger.info("Bucle de cámaras iniciado (%.1f fps por aula)", FPS_POR_AULA)
    return _task

async def detener_bucle_camaras() -> None:
    global _task
    _stop.set()
    if _task is not None:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
        for _room_id, src in list(_fuentes.items()):
            with contextlib.suppress(Exception):
                await asyncio.to_thread(src.release)
    _fuentes.clear()
    logger.info("Bucle de cámaras detenido")
