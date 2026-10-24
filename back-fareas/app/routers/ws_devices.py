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

_conexiones: dict[str, WebSocket] = {}
_ultimo_msj: dict[str, float] = {}

HEARTBEAT_TIMEOUT_S = 90.0


def conexiones() -> dict[str, WebSocket]:
    return _conexiones

async def _validar_dispositivo(db: SQLModelAsyncSession, device_id: str) -> Device | None:
    return (
        await db.exec(
            select(Device).where(
                Device.device_key == device_id,
                Device.device_type == DeviceType.ESP32,
                Device.is_active,
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
        estaba_online = d.is_online
        d.is_online = False
        db.add(d)
        if estaba_online:
            from app.services.notification_center import notificar_dispositivo_offline

            await notificar_dispositivo_offline(db, device=d)
        await db.commit()

async def expirar_nodos() -> int:
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

        import time as _time

        _conexiones[device_id] = websocket
        _ultimo_msj[device_id] = _time.monotonic()
        async with SessionLocal() as db:
            await _marcar_online(db, device_id)
        await websocket.send_text(json.dumps({"type": "hello_ack", "device_id": device_id,
                                              "room_id": dispositivo.room_id}))
        logger.info("[RF-33] Nodo ESP32 '%s' conectado (%s)", device_id, hello.get("mac", "sin mac"))

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
    ws = _conexiones.get(device_key)
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(comando))
        return True
    except Exception:
        logger.exception("Fallo enviando veredicto a %s", device_key)
        return False
