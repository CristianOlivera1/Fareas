import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("fareas.go2rtc")

TIMEOUT_S = 4.0


class Go2rtcUnavailable(Exception):
    pass


def stream_name(room_id: int) -> str:
    return f"room-{room_id}"


def _base() -> str:
    return get_settings().GO2RTC_API_URL.rstrip("/")


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    if not get_settings().GO2RTC_ENABLED:
        raise Go2rtcUnavailable("go2rtc está deshabilitado")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.request(method, f"{_base()}{path}", **kwargs)
    except httpx.HTTPError as exc:
        raise Go2rtcUnavailable("No se pudo contactar a go2rtc") from exc
    if response.status_code >= 400:
        raise Go2rtcUnavailable(f"go2rtc respondió {response.status_code}")
    return response


async def registrar(room_id: int, rtsp_url: str) -> None:
    await _request("PUT", "/api/streams", params={"name": stream_name(room_id), "src": rtsp_url})


async def responder_oferta(room_id: int, offer: dict) -> dict:
    response = await _request("POST", "/api/webrtc", params={"src": stream_name(room_id)}, json=offer)
    return response.json()


async def fuente_para_deteccion(room_id: int, rtsp_url: str) -> str:
    try:
        await registrar(room_id, rtsp_url)
    except Go2rtcUnavailable:
        return rtsp_url
    return f"{get_settings().GO2RTC_RTSP_URL.rstrip('/')}/{stream_name(room_id)}"
