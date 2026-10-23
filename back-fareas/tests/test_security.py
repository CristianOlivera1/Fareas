from app.tables import Device, Room

API = "/api/v1"

CLAVE_TEMP = "ClaveTemporal1"
CLAVE_NUEVA = "ClaveNuevaSegura9"


async def _login(client, email: str, password: str) -> str:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

async def test_must_change_password_bloquea_todo_lo_demas(client, temp_student):
    token = await _login(client, temp_student.email, CLAVE_TEMP)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 200 and r.json()["must_change_password"] is True

    r = await client.get(f"{API}/attendance/me", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "must_change_password"

    r = await client.post(f"{API}/auth/change-password", headers=headers,
                          json={"current_password": CLAVE_TEMP, "new_password": CLAVE_NUEVA})
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]
    assert new_token
    headers = {"Authorization": f"Bearer {new_token}"}
    r = await client.get(f"{API}/attendance/me", headers=headers)
    assert r.status_code == 200, r.text

async def test_usuario_desactivado_pierde_acceso_al_instante(client, temp_student, db_session):
    token = await _login(client, temp_student.email, CLAVE_TEMP)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"{API}/auth/me", headers=headers)).status_code == 200

    temp_student.is_active = False
    db_session.add(temp_student)
    await db_session.commit()

    r = await client.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 401

async def test_rtsp_enmascarada_en_listados(client, admin_headers, db_session):
    r = await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 998"})
    assert r.status_code == 201, r.text
    room_id = r.json()["id"]
    rtsp = "rtsp://admin:secreta123@10.14.5.11:554/Streaming/Channels/102"
    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room_id, "device_type": "camara",
                                "device_key": "cam-tst-rtsp", "name": "Cam RTSP",
                                "rtsp_url": rtsp})
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    try:
        r = await client.get(f"{API}/devices", headers=admin_headers, params={"page_size": 100})
        fila = next(d for d in r.json()["items"] if d["id"] == device_id)
        assert "secreta123" not in fila["rtsp_url"] and "***" in fila["rtsp_url"]

        r = await client.get(f"{API}/devices/{device_id}", headers=admin_headers)
        assert r.json()["rtsp_url"] == rtsp

        r = await client.patch(f"{API}/devices/{device_id}", headers=admin_headers,
                               json={"rtsp_url": fila["rtsp_url"], "name": "Cam RTSP v2"})
        assert r.status_code == 200
        r = await client.get(f"{API}/devices/{device_id}", headers=admin_headers)
        assert r.json()["rtsp_url"] == rtsp and r.json()["name"] == "Cam RTSP v2"
    finally:
        device = await db_session.get(Device, device_id)
        if device is not None:
            await db_session.delete(device)
        room = await db_session.get(Room, room_id)
        if room is not None:
            await db_session.delete(room)
        await db_session.commit()

async def test_consentimiento_obligatorio_para_enrolar(client, admin_headers, temp_student):
    r = await client.post(f"{API}/students/{temp_student.id}/faces", headers=admin_headers,
                          json={"photos": ["aGVsbG8=", "aGVsbG8=", "aGVsbG8="]})
    assert r.status_code == 422
    assert "consentimiento" in r.json()["detail"].lower()

    r = await client.post(f"{API}/students/{temp_student.id}/faces", headers=admin_headers,
                          json={"consent": True, "photos": ["aGVsbG8=", "aGVsbG8=", "aGVsbG8="]})
    assert r.status_code == 422
    assert "consentimiento" not in r.json()["detail"].lower()

async def test_estudiante_no_accede_a_endpoints_de_panel(client, temp_student, db_session):
    from app.core.security import create_access_token

    temp_student.must_change_password = False
    db_session.add(temp_student)
    await db_session.commit()
    token = create_access_token(temp_student.id, "estudiante")
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get(f"{API}/rooms", headers=headers)).status_code == 403
    assert (await client.get(f"{API}/audit-log", headers=headers)).status_code == 403
    assert (await client.get(f"{API}/attendance/today", headers=headers)).status_code == 403
