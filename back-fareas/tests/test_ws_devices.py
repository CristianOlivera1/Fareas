"""Tests del protocolo WebSocket de dispositivos — RF-25, RF-33, RF-35.

Usa el TestClient de Starlette (websocket_connect) para el handshake y la
BD real para validar el ciclo is_online: hello → TRUE, expirar_nodos → FALSE.
"""
import time

import pytest
from sqlmodel import select
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.routers.ws_devices import _conexiones, _marcar_online, _ultimo_msj, expirar_nodos
from app.tables import Device

WS = "/api/v1/ws/devices"
NODO = "esp32-lab305"  # device_key del seed


@pytest.fixture
def sync_client():
    """TestClient síncrono SOLO para websockets (los tests async de BD van aparte)."""
    app = create_app()
    with TestClient(app) as c:
        yield c


async def _estado_nodo(db, device_key: str) -> Device | None:
    return (await db.exec(select(Device).where(Device.device_key == device_key))).first()


def test_token_invalido_rechaza(sync_client):
    """Token incorrecto: el backend cierra con 4401 (WebSocketDisconnect en cliente)."""
    from starlette.websockets import WebSocketDisconnect

    try:
        with sync_client.websocket_connect(f"{WS}?token=incorrecto") as ws:
            ws.receive()
    except WebSocketDisconnect as exc:
        assert exc.code == 4401  # el cierre correcto del backend
    else:
        raise AssertionError("el backend aceptó un token inválido")


def test_hello_key_inexistente_rechaza(sync_client):
    """Un device_key que no está en la BD se rechaza con close 4404 (RF-33)."""
    with sync_client.websocket_connect(f"{WS}?token={get_settings().DEVICE_TOKEN_SECRET}") as ws:
        ws.send_json({"type": "hello", "device_id": "esp32-inexistente-xyz"})
        mensaje = ws.receive()
        # TestClient entrega el close como dict (según versión) o lanza:
        if isinstance(mensaje, dict):
            assert mensaje.get("type") == "websocket.close"
            assert mensaje.get("code") == 4404
        else:  # pragma: no cover - versiones que levantan WebSocketDisconnect
            raise AssertionError(f"se esperaba close 4404, llegó: {mensaje!r}")


def test_hello_valido_registra_y_latido(sync_client):
    """Hello válido → hello_ack + conexión registrada; heartbeat y ping OK (RF-33)."""
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
    """RF-35: hello marca is_online=TRUE; expirar_nodos (latido vencido) → FALSE."""
    # simula una conexión reciente: online + latido ahora
    _conexiones[NODO] = object()  # placeholder solo para el registro
    _ultimo_msj[NODO] = time.monotonic()
    try:
        async with db_session.begin():
            await _marcar_online(db_session, NODO)
        db_session.expire_all()
        nodo = await _estado_nodo(db_session, NODO)
        assert nodo is not None and nodo.is_online is True

        # envejece el último mensaje (>90 s) y corre la expiración
        _ultimo_msj[NODO] = time.monotonic() - 91.0
        apagados = await expirar_nodos()
        assert apagados >= 1
        assert NODO not in _conexiones and NODO not in _ultimo_msj
        db_session.expire_all()  # expire_on_commit=False: invalida el objeto cacheado
        nodo = await _estado_nodo(db_session, NODO)
        assert nodo is not None and nodo.is_online is False
    finally:
        _conexiones.pop(NODO, None)
        _ultimo_msj.pop(NODO, None)
