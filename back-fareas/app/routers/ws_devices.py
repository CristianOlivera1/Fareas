"""Canal WebSocket para nodos ESP32 en las puertas de las aulas.

RF-25 (feedback LED/buzzer) + RF-33 (identidad y latido) + RF-35 (monitoreo).

Protocolo (contrato con el firmware, guía en PLAN §4.2):

1. Conexión:  ``ws://host:8000/api/v1/ws/devices?token=<DEVICE_TOKEN_SECRET>``
   Token incorrecto → close 4401.
2. Presentación:  ``{"type": "hello", "device_id": "esp32-lab305", "mac": "..."}``
   El ``device_id`` DEBE existir como ``device.device_key`` (tipo esp32, activo)
   en la BD; si no, close 4404. Al validarse: ``is_online=TRUE`` y
   ``last_heartbeat=NOW()`` (RF-33/RF-35) — visible en GET /devices/status.
3. Latido cada 30 s:  ``{"type": "heartbeat"}`` → actualiza last_heartbeat.
   La tarea ``expirar_nodos`` marca is_online=FALSE si no llega latido en 90 s.
4. El backend despacha veredictos Tabla 8 al device_key:
   ``{"type": "verdict", "status": "asistio", "color": "verde", "buzzer": "beep_1",
      "seconds": 3, "message": "Registro correcto"}``
   (los envía ``services/camera_loop.py`` usando ``conexiones()``).
"""
import contextlib
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings
from app.database import SessionLocal
from app.tables import Device, DeviceType

logger = logging.getLogger("fareas.ws")
router = APIRouter()

# device_key -> WebSocket activo (proceso único; PLAN §7 descarta pub/sub).
_conexiones: dict[str, WebSocket] = {}
# device_key -> monotonic del último mensaje recibido (para expirar sin BD extra)
_ultimo_msj: dict[str, float] = {}

HEARTBEAT_TIMEOUT_S = 90.0  # RF-33: 3 latidos perdidos (30 c/u) → fuera de línea


def conexiones() -> dict[str, WebSocket]:
    """Mapa device_key → WebSocket para el despacho de veredictos."""
    return _conexiones


async def _validar_dispositivo(db: SQLModelAsyncSession, device_id: str) -> Device | None:
    """El device_key debe ser un ESP32 activo registrado (RF-33)."""
    return (
        await db.exec(
            select(Device).where(
                Device.device_key == device_id,
                Device.device_type == DeviceType.ESP32,  # type: ignore[arg-type]
                Device.is_active,  # type: ignore[arg-type]
            )
        )
    ).first()


async def _marcar_online(db: SQLModelAsyncSession, device_id: str) -> None:
    d = await _validar_dispositivo(db, device_id)
    if d is not None:
        d.is_online = True
        d.last_heartbeat = datetime.now()
        db.add(d)
        await db.commit()


async def _marcar_offline(db: SQLModelAsyncSession, device_id: str) -> None:
    d = await _validar_dispositivo(db, device_id)
    if d is not None:
        d.is_online = False
        db.add(d)
        await db.commit()


async def expirar_nodos() -> int:
    """RF-35: marca offline los nodos con latidos vencidos (>90 s).

    La llama el scheduler (lifespan). Devuelve cuántos nodos se apagaron.
    """
    import time as _time

    ahora = _time.monotonic()
    vencidos = [k for k, t in _ultimo_msj.items() if ahora - t > HEARTBEAT_TIMEOUT_S]
    if not vencidos:
        return 0
    apagados = 0
    for device_id in vencidos:
        _conexiones.pop(device_id, None)
        _ultimo_msj.pop(device_id, None)
        try:
            async with SessionLocal() as db:
                await _marcar_offline(db, device_id)
            apagados += 1
            logger.info("[RF-35] Nodo %s fuera de línea (sin latidos)", device_id)
        except Exception:
            logger.exception("No se pudo marcar offline el nodo %s", device_id)
    return apagados


@router.websocket("/ws/devices")
async def devices_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    settings = get_settings()
    if token != settings.DEVICE_TOKEN_SECRET:
        await websocket.close(code=4401, reason="Token de dispositivo inválido")
        return

    await websocket.accept()
    device_id: str | None = None
    try:
        # 1) La PRIMERA trama debe ser el hello (RF-33)
        raw = await websocket.receive_text()
        try:
            hello = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.close(code=4400, reason="La primera trama debe ser JSON hello")
            return
        device_id = str(hello.get("device_id") or "")[:64]
        if hello.get("type") != "hello" or not device_id:
            await websocket.close(code=4400, reason="Se espera {type:'hello', device_id:'...'}")
            return

        async with SessionLocal() as db:
            dispositivo = await _validar_dispositivo(db, device_id)
        if dispositivo is None:
            await websocket.close(code=4404, reason=f"device_key '{device_id}' no registrado como ESP32 activo")
            return

        # Registrado: online + último latido ahora (RF-33/RF-35)
        import time as _time

        _conexiones[device_id] = websocket
        _ultimo_msj[device_id] = _time.monotonic()
        async with SessionLocal() as db:
            await _marcar_online(db, device_id)
        await websocket.send_text(json.dumps({"type": "hello_ack", "device_id": device_id,
                                              "room_id": dispositivo.room_id}))
        logger.info("[RF-33] Nodo ESP32 '%s' conectado (%s)", device_id, hello.get("mac", "sin mac"))

        # 2) Bucle de latidos/comandos
        while True:
            raw = await websocket.receive_text()
            _ultimo_msj[device_id] = _time.monotonic()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "JSON inválido"}))
                continue

            msg_type = message.get("type")
            if msg_type == "heartbeat":
                async with SessionLocal() as db:
                    d = await _validar_dispositivo(db, device_id)
                    if d is not None:
                        d.last_heartbeat = datetime.now()
                        db.add(d)
                        await db.commit()
                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": f"Tipo no soportado: {msg_type}"})
                )
    except WebSocketDisconnect:
        pass
    finally:
        if device_id:
            _conexiones.pop(device_id, None)
            _ultimo_msj.pop(device_id, None)
            with contextlib.suppress(Exception):
                async with SessionLocal() as db:
                    await _marcar_offline(db, device_id)
            logger.info("[RF-33] Nodo ESP32 '%s' desconectado", device_id)


async def enviar_veredicto(device_key: str, comando: dict) -> bool:
    """Envía un comando al nodo (Tabla 8). False si no está conectado."""
    ws = _conexiones.get(device_key)
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(comando))
        return True
    except Exception:
        logger.exception("Fallo enviando veredicto a %s", device_key)
        return False
