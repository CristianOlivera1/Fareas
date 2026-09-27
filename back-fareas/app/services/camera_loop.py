"""Bucle de ingestión de cámaras (Bloques 6-7) — RF-17/RF-21/RF-25 en vivo.

Para cada aula con cámara activa: mantiene UNA fuente abierta (~2 fps por
aula, round-robin con un solo task), corre el pipeline de visión y:
1. resuelve la sesión del aula (la crea si hay clase, RF-26),
2. persiste la marca ÚNICA si el alumno identificado está matriculado,
3. envía el veredicto al ESP32 del aula (Tabla 8, Bloque 7),
4. deja el último veredicto en memoria para el feed SSE del Bloque 8.

Clave de rendimiento: si una fuente de red (RTSP) no alcanza, backoff de 60 s
(sin eso, VideoCapture bloquea 30 s por intento — y congelaba el event loop:
era la causa del 'login lento'). Los archivos de video del proyecto siempre
'alcanzan'. La galería facial se carga al arrancar y se refresca al enrolar.
"""
import asyncio
import contextlib
import logging
import socket
import time
from datetime import datetime, timedelta

from sqlmodel import select

from app.ai.runtime import vision_pipeline
from app.database import SessionLocal
from app.services import errors
from app.services.attendance_engine import _naive_peru, ahora_peru, registrar_marca, resolver_sesion
from app.tables import AppSettings, Device, DeviceType, Enrollment

logger = logging.getLogger("fareas.cameras")

FPS_POR_AULA = 2.0

_task: asyncio.Task | None = None
_stop = asyncio.Event()

# room_id -> último veredicto (lo leerá el feed SSE del Bloque 8)
_ultimo: dict[int, dict] = {}
# room_id -> monotonic hasta el cual NO se reintenta una cámara caída (backoff)
_reintentar_desde: dict[int, float] = {}
_BACKOFF_CAIDA = 60.0
# room_id -> fuente abierta (persistente entre ciclos, como una cámara real)
_fuentes: dict[int, object] = {}
# room_id -> lecturas consecutivas fallidas (tolera misses transitorios del hilo)
_fallos: dict[int, int] = {}


def ultimo_veredicto(room_id: int) -> dict | None:
    return _ultimo.get(room_id)


def todos_los_veredictos() -> list[dict]:
    return list(_ultimo.values())


def _rtsp_alcanzable(rtsp_url: str, timeout: float = 2.0) -> bool:
    """Pre-chequeo TCP: ¿algo escucha en host:puerto del RTSP?

    cv2.VideoCapture con un host caído BLOQUEA ~30 s (medido) y si se llama
    en el event loop congela TODA la API. Archivos locales siempre 'alcanzan'.
    """
    from urllib.parse import urlparse

    if not rtsp_url.lower().startswith(("rtsp://", "http://", "https://")):
        return True  # archivo local: VideoFileSource
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
    """Abre (o reabre) la fuente del aula y espera su PRIMER frame.

    El hilo lector tarda unos ms en decodificar: sin esta espera, el primer
    read() llega vacío y el código daría la fuente por muerta en cada ciclo
    (bug real: la fuente se abría y cerraba indefinidamente).
    """
    from app.ai.frame_source import open_source

    if not await asyncio.to_thread(_rtsp_alcanzable, rtsp_url):
        return None
    try:
        src = await asyncio.to_thread(open_source, rtsp_url)
    except FileNotFoundError:
        return None
    # Calentamiento: hasta 5 s esperando el primer frame del hilo lector
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
    """Un ciclo de UNA aula: frame → pipeline → BD → websocket."""

    async with SessionLocal() as db:
        cam = (
            await db.exec(
                select(Device).where(
                    Device.room_id == room_id,
                    Device.device_type == DeviceType.CAMARA,  # type: ignore[arg-type]
                    Device.is_active,  # type: ignore[arg-type]
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
                return

        ok, frame = await asyncio.to_thread(src.read)
        if not ok or frame is None:
            # Fallo transitorio (hilo ocupado) vs fuente muerta: tolera 5
            # fallos seguidos (~2.5 s) antes de reabrir con backoff.
            _fallos[room_id] = _fallos.get(room_id, 0) + 1
            if _fallos[room_id] >= 5:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(src.release)
                _fuentes.pop(room_id, None)
                _fallos[room_id] = 0
                _reintentar_desde[room_id] = time.monotonic() + _BACKOFF_CAIDA
            return
        _fallos[room_id] = 0

        # Clase activa del aula (crea la sesión si corresponde, RF-26)
        sesion, bloque = await resolver_sesion(db, room_id)
        candidates: set[int] | None = None
        clasificador = None
        if sesion is not None and bloque is not None:
            ids = (
                await db.exec(select(Enrollment.student_id).where(Enrollment.group_id == bloque.group_id))
            ).all()
            candidates = {r[0] if isinstance(r, tuple) else r for r in ids}

            # RF-23 en vivo: el clasificador decide asistio/tardanza por aula
            settings = await db.get(AppSettings, 1)
            tolerancia = timedelta(minutes=settings.late_tolerance_minutes if settings else 10)
            fin = datetime.combine(sesion.session_date, bloque.end_time)

            def clasificador(_sid: int, _t: float) -> str:
                ahora = _naive_peru(ahora_peru())
                if ahora <= fin:
                    return "asistio"
                if ahora <= fin + tolerancia:
                    return "tardanza"
                return "sin_registro"

        await db.commit()  # persiste la sesión recién creada (si la hubo)

        # Con clasificador activo el pipeline genera `mark` → persistencia BD;
        # sin clase, modo demo (solo LED).
        pipe.classifier = clasificador
        resultado = pipe.process_frame(frame, candidates=candidates)
        _ultimo[room_id] = {
            "room_id": room_id,
            "verdict": resultado.verdict,
            "student_id": resultado.student_id,
            "similarity": round(resultado.similarity, 4),
            "ts": ahora_peru().isoformat(timespec="seconds"),
        }

        # Marca única en BD (solo con clase activa y alumno matriculado)
        if sesion is not None and resultado.mark is not None:
            try:
                await registrar_marca(
                    db, sesion, resultado.mark["student_id"],
                    similarity=resultado.mark["similarity"], method="facial",
                )
                await db.commit()
            except errors.ConflictError:
                await db.rollback()  # ya marcó en esta sesión (UNIQUE)

        # Veredicto al ESP32 del aula (Bloque 7): por device_key registrado
        nodo = (
            await db.exec(
                select(Device.device_key).where(
                    Device.room_id == room_id,
                    Device.device_type == DeviceType.ESP32,  # type: ignore[arg-type]
                    Device.is_active,  # type: ignore[arg-type]
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
    """Task maestro: recorre las aulas con cámara activa en round-robin."""
    pipe = vision_pipeline()
    try:
        from app.ai.runtime import recargar_galeria

        async with SessionLocal() as db:
            n = await recargar_galeria(db)
        logger.info("Galería facial cargada: %s alumnos", n)
    except Exception:
        logger.exception("No se pudo cargar la galería facial; el bucle sigue")

    while not _stop.is_set():
        try:
            async with SessionLocal() as db:
                filas = (
                    await db.exec(
                        select(Device.room_id).where(
                            Device.device_type == DeviceType.CAMARA,  # type: ignore[arg-type]
                            Device.is_active,  # type: ignore[arg-type]
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
    """Arranca el bucle (idempotente)."""
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
    # cierra todas las fuentes abiertas
    for _room_id, src in list(_fuentes.items()):
        with contextlib.suppress(Exception):
            await asyncio.to_thread(src.release)
    _fuentes.clear()
    logger.info("Bucle de cámaras detenido")
