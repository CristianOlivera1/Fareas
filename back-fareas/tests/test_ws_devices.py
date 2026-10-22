import time

import pytest
from sqlmodel import select
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.routers.ws_devices import _conexiones, _marcar_online, _ultimo_msj, expirar_nodos
from app.tables import Device

WS = "/api/v1/ws/devices"
NODO = "esp32-lab305"


@pytest.fixture
def sync_client():
    app = create_app()
    with TestClient(app) as c:
        yield c

async def _estado_nodo(db, device_key: str) -> Device | None:
    return (await db.exec(select(Device).where(Device.device_key == device_key))).first()

def test_token_invalido_rechaza(sync_client):
    from starlette.websockets import WebSocketDisconnect

    try:
        with sync_client.websocket_connect(f"{WS}?token=incorrecto") as ws:
            ws.receive()
    except WebSocketDisconnect as exc:
        assert exc.code == 4401
    else:
        raise AssertionError("el backend aceptó un token inválido")

def test_hello_key_inexistente_rechaza(sync_client):
    with sync_client.websocket_connect(f"{WS}?token={get_settings().DEVICE_TOKEN_SECRET}") as ws:
        ws.send_json({"type": "hello", "device_id": "esp32-inexistente-xyz"})
        mensaje = ws.receive()
        if isinstance(mensaje, dict):
            assert mensaje.get("type") == "websocket.close"
            assert mensaje.get("code") == 4404
        else:
            raise AssertionError(f"se esperaba close 4404, llegó: {mensaje!r}")

def test_hello_valido_registra_y_latido(sync_client):
    try:
        with sync_client.websocket_connect(f"{WS}?token={get_settings().DEVICE_TOKEN_SECRET}") as ws:
            ws.send_json({"type": "hello", "device_id": NODO})
            ack = ws.receive_json()
            assert ack["type"] == "hello_ack" and ack["device_id"] == NODO
            assert NODO in _conexiones

            ws.send_json({"type": "heartbeat"})
            assert ws.receive_json()["type"] == "heartbeat_ack"

            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"

            ws.send_json({"type": "cualquiera"})
            assert "no soportado" in ws.receive_json()["message"]
    finally:
        _conexiones.pop(NODO, None)
        _ultimo_msj.pop(NODO, None)

async def test_ciclo_online_offline(db_session):
    _conexiones[NODO] = object()
    _ultimo_msj[NODO] = time.monotonic()
    try:
        async with db_session.begin():
            await _marcar_online(db_session, NODO)
        db_session.expire_all()
        nodo = await _estado_nodo(db_session, NODO)
        assert nodo is not None and nodo.is_online is True

        _ultimo_msj[NODO] = time.monotonic() - 91.0
        apagados = await expirar_nodos()
        assert apagados >= 1
        assert NODO not in _conexiones and NODO not in _ultimo_msj
        db_session.expire_all()
        nodo = await _estado_nodo(db_session, NODO)
        assert nodo is not None and nodo.is_online is False
    finally:
        _conexiones.pop(NODO, None)
        _ultimo_msj.pop(NODO, None)
