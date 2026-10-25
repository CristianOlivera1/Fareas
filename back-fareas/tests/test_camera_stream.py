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
    monkeypatch.setattr(camera_stream, "RECONNECT_ATTEMPTS", 0)
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
    assert r.content.count(b"--frame") >= 1
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


def test_el_recuadro_se_dibuja_con_el_color_del_veredicto():
    fondo = np.zeros((480, 640, 3), dtype=np.uint8)
    jpeg = camera_stream._encode(fondo, boxes=[np.array([200, 120, 400, 360], dtype=np.float32)],
                                 verdict={"verdict": "asistio"})
    sin_recuadro = camera_stream._encode(fondo)
    imagen = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert imagen[120, 200:260].max() > 100
    assert imagen[240, 300].max() < 30
    assert jpeg != sin_recuadro
    assert fondo.max() == 0


OFERTA = {"type": "offer", "sdp": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\n"}


async def test_webrtc_reenvia_la_oferta_a_go2rtc(client, admin_login, aula_con_camara, monkeypatch):
    from app.services import go2rtc

    registrados = []

    async def registrar(room_id, rtsp_url):
        registrados.append(room_id)

    async def responder(room_id, offer):
        return {"type": "answer", "sdp": "v=0 respuesta"}

    monkeypatch.setattr(go2rtc, "registrar", registrar)
    monkeypatch.setattr(go2rtc, "responder_oferta", responder)
    r = await client.post(f"{API}/dashboard/camera/{aula_con_camara}/webrtc", json=OFERTA,
                          headers=admin_login["headers"])

    assert r.status_code == 200
    assert r.json() == {"type": "answer", "sdp": "v=0 respuesta"}
    assert registrados == [aula_con_camara]


async def test_webrtc_responde_503_si_go2rtc_no_esta_activo(client, admin_login, aula_con_camara, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "GO2RTC_API_URL", "http://127.0.0.1:1")
    r = await client.post(f"{API}/dashboard/camera/{aula_con_camara}/webrtc", json=OFERTA,
                          headers=admin_login["headers"])

    assert r.status_code == 503


async def test_webrtc_valida_sesion_oferta_y_camara(client, admin_login):
    sin_sesion = await client.post(f"{API}/dashboard/camera/1/webrtc", json=OFERTA)
    oferta_mala = await client.post(f"{API}/dashboard/camera/1/webrtc", json={"type": "answer", "sdp": "x" * 20},
                                    headers=admin_login["headers"])
    sin_camara = await client.post(f"{API}/dashboard/camera/999999/webrtc", json=OFERTA,
                                   headers=admin_login["headers"])

    assert sin_sesion.status_code == 401
    assert oferta_mala.status_code == 422
    assert sin_camara.status_code == 404


async def test_faces_exige_token_y_camara_activa(client, admin_login):
    token = admin_login["headers"]["Authorization"].split()[1]
    sin_token = await client.get(f"{API}/dashboard/camera/1/faces", params={"access_token": "malo-malo-malo"})
    sin_camara = await client.get(f"{API}/dashboard/camera/999999/faces", params={"access_token": token})

    assert sin_token.status_code == 401
    assert sin_camara.status_code == 404
