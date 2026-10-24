import pytest
from sqlmodel import delete, select

from app.services import camera_loop
from app.tables import Device, DeviceType, Room

API = "/api/v1"
ROOM = "TST-CAM-STATUS"
KEY = "cam-tst-status"


@pytest.fixture
async def camera(db_session):
    await db_session.exec(delete(Device).where(Device.device_key == KEY))
    await db_session.exec(delete(Room).where(Room.code == ROOM))
    await db_session.commit()
    room = Room(code=ROOM, name="Aula estado cámara")
    db_session.add(room)
    await db_session.flush()
    device = Device(
        room_id=room.id,
        device_type=DeviceType.CAMARA,
        device_key=KEY,
        rtsp_url="rtsp://127.0.0.1:1/stream",
        is_online=False,
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    yield device
    await db_session.exec(delete(Device).where(Device.device_key == KEY))
    await db_session.exec(delete(Room).where(Room.code == ROOM))
    await db_session.commit()
    camera_loop._last_heartbeat.pop(room.id, None)


async def _summary(client, headers) -> dict:
    return (await client.get(f"{API}/dashboard/summary", headers=headers)).json()


async def test_online_camera_is_counted_as_active(client, admin_headers, db_session, camera):
    before = await _summary(client, admin_headers)

    await camera_loop._set_camera_state(db_session, camera, True)
    after = await _summary(client, admin_headers)

    assert after["camaras_activas"] == before["camaras_activas"] + 1
    assert after["camaras_total"] == before["camaras_total"]
    assert after["streams_caidos"] == before["streams_caidos"] - 1


async def test_offline_camera_counts_as_fallen_stream(client, admin_headers, db_session, camera):
    await camera_loop._set_camera_state(db_session, camera, True)
    online = await _summary(client, admin_headers)

    await camera_loop._set_camera_state(db_session, camera, False)
    offline = await _summary(client, admin_headers)

    assert offline["camaras_activas"] == online["camaras_activas"] - 1
    assert offline["streams_caidos"] == online["streams_caidos"] + 1


async def test_heartbeat_is_throttled(db_session, camera):
    await camera_loop._set_camera_state(db_session, camera, True)
    first = camera.last_heartbeat

    await camera_loop._refresh_heartbeat(db_session, camera)

    assert camera.last_heartbeat == first


async def test_startup_resets_cameras_to_offline(db_session, camera):
    await camera_loop._set_camera_state(db_session, camera, True)

    await camera_loop._reset_cameras_offline()

    await db_session.refresh(camera)
    assert camera.is_online is False
    stored = (await db_session.exec(select(Device).where(Device.device_key == KEY))).one()
    assert stored.is_online is False
