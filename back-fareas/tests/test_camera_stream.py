import cv2
import numpy as np
import pytest
from sqlmodel import delete

from app.services import camera_stream
from app.tables import Device, DeviceType, Room

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _rapido(monkeypatch):
    monkeypatch.setattr(camera_stream, "RECONNECT_DELAY_S", 0.01)
    monkeypatch.setattr(camera_stream, "IDLE_GRACE_S", 0.01)
    yield
    camera_stream.shutdown()

API = "/api/v1"
SALA = "LAB 996"
CLAVE = "cam-test-996"


@pytest.fixture
def video(tmp_path) -> str:
    ruta = str(tmp_path / "camara.avi")
    escritor = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
    for i in range(6):
        escritor.write(np.full((240, 320, 3), i * 40, dtype=np.uint8))
    escritor.release()
    return ruta


async def _limpiar(db_session) -> None:
    await db_session.exec(delete(Device).where(Device.device_key == CLAVE))
    await db_session.exec(delete(Room).where(Room.code == SALA))
    await db_session.commit()


@pytest.fixture
async def aula_con_camara(db_session, video):
    await _limpiar(db_session)
    aula = Room(code=SALA)
    db_session.add(aula)
    await db_session.commit()
    await db_session.refresh(aula)
    db_session.add(Device(room_id=aula.id, device_type=DeviceType.CAMARA, device_key=CLAVE, rtsp_url=video))
    await db_session.commit()
    yield aula.id
    await _limpiar(db_session)


async def test_stream_entrega_frames_jpeg_multipart(client, admin_login, aula_con_camara):
    token = admin_login["headers"]["Authorization"].split()[1]
    r = await client.get(f"{API}/dashboard/camera/{aula_con_camara}/mjpeg", params={"access_token": token})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("multipart/x-mixed-replace; boundary=frame")
    assert r.content.count(b"--frame") >= 3
    assert b"\xff\xd8" in r.content


async def test_stream_exige_token_y_camara_activa(client, admin_login, db_session):
    token = admin_login["headers"]["Authorization"].split()[1]
    sin_token = await client.get(f"{API}/dashboard/camera/1/mjpeg", params={"access_token": "malo-malo-malo"})
    sin_camara = await client.get(f"{API}/dashboard/camera/999999/mjpeg", params={"access_token": token})

    assert sin_token.status_code == 401
    assert sin_camara.status_code == 404


async def test_stream_limita_las_vistas_simultaneas(client, admin_login, aula_con_camara, monkeypatch):
    token = admin_login["headers"]["Authorization"].split()[1]
    monkeypatch.setattr(camera_stream, "MAX_VIEWERS_PER_ROOM", 0)
    r = await client.get(f"{API}/dashboard/camera/{aula_con_camara}/mjpeg", params={"access_token": token})

    assert r.status_code == 429


async def test_stream_con_rtsp_inalcanzable_responde_502(client, admin_login, aula_con_camara, db_session):
    from sqlalchemy import update

    await db_session.exec(update(Device).where(Device.device_key == CLAVE).values(rtsp_url="C:/no-existe/video.avi"))
    await db_session.commit()
    token = admin_login["headers"]["Authorization"].split()[1]
    r = await client.get(f"{API}/dashboard/camera/{aula_con_camara}/mjpeg", params={"access_token": token})

    assert r.status_code == 502
