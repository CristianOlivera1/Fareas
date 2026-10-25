import pytest
from httpx import AsyncClient
from sqlmodel import delete, select

from app.tables import AppUser, Device, FaceEmbedding, Room
from tests.conftest import TEMP_EMAIL

pytestmark = pytest.mark.asyncio

API = "/api/v1"

_EMAILS_TMP = [
    "temp.docente.leer@unamba.edu.pe",
    "temp.docente.b4@unamba.edu.pe",
    "temp.estudiante.b4@unamba.edu.pe",
    "temp.estudiante.b5@unamba.edu.pe",
    "temp.estudiante.reciente1@unamba.edu.pe",
    "temp.estudiante.reciente2@unamba.edu.pe",
    "temp.docente.patch@unamba.edu.pe",
]


async def _purge(db_session) -> None:
    await db_session.exec(delete(AppUser).where(AppUser.email.in_(_EMAILS_TMP)))
    await db_session.exec(
        delete(Device).where(Device.device_key.in_(["esp32-lab998", "cam-rtsp-edit-test"]))
    )
    await db_session.exec(delete(Room).where(Room.code.in_(["LAB 999", "LAB 998", "LAB 997"])))
    await db_session.commit()

@pytest.fixture(autouse=True)
async def _limpieza(db_session):
    await _purge(db_session)
    yield
    await _purge(db_session)

async def test_listas_requieren_token(client: AsyncClient):
    assert (await client.get(f"{API}/rooms")).status_code == 401
    assert (await client.get(f"{API}/teachers")).status_code == 401
    assert (await client.get(f"{API}/students")).status_code == 401

async def test_docente_puede_leer_pero_no_crear(
    client: AsyncClient, admin_headers: dict, docente_headers: dict
):
    r = await client.post(
        f"{API}/teachers",
        headers=admin_headers,
        json={"full_name": "Prueba Docente Lectura", "email": "temp.docente.leer@unamba.edu.pe", "dni": "71112233"},
    )
    assert r.status_code == 201, r.text

    doc_headers = docente_headers

    assert (await client.get(f"{API}/teachers", headers=doc_headers)).status_code == 200
    assert (await client.get(f"{API}/rooms", headers=doc_headers)).status_code == 200
    r = await client.post(
        f"{API}/teachers",
        headers=doc_headers,
        json={"full_name": "No Permitido", "email": "x@unamba.edu.pe", "dni": "70000001"},
    )
    assert r.status_code == 403

async def test_crud_aulas(client: AsyncClient, admin_headers: dict):
    r = await client.post(f"{API}/rooms", headers=admin_headers,
                          json={"code": "LAB 999", "name": "Laboratorio de pruebas"})
    assert r.status_code == 201, r.text
    room = r.json()
    assert room["code"] == "LAB 999"

    r = await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "lab 999"})
    assert r.status_code == 409

    r = await client.get(f"{API}/rooms", headers=admin_headers, params={"q": "999"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1 and any(x["id"] == room["id"] for x in data["items"])

    r = await client.patch(f"{API}/rooms/{room['id']}", headers=admin_headers,
                           json={"name": "Laboratorio renombrado", "is_active": False})
    assert r.status_code == 200
    assert r.json()["name"] == "Laboratorio renombrado"
    assert r.json()["is_active"] is False

async def test_crear_aula_requiere_admin(client: AsyncClient):
    r = await client.post(f"{API}/rooms", json={"code": "LAB X"})
    assert r.status_code == 401

async def test_dispositivos_flujo_basico(client: AsyncClient, admin_headers: dict):
    room = (await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 998"})).json()

    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "camara", "device_key": "cam-lab998"})
    assert r.status_code == 422

    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "esp32", "device_key": "esp32-lab998",
                                "name": "Nodo de prueba"})
    assert r.status_code == 201, r.text
    device = r.json()
    assert device["room_code"] == "LAB 998"
    assert device["is_online"] is False

    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "esp32", "device_key": "esp32-lab998"})
    assert r.status_code == 409

    r = await client.get(f"{API}/devices/status")
    assert r.status_code == 200
    assert any(d["device_key"] == "esp32-lab998" for d in r.json())

    r = await client.patch(f"{API}/devices/{device['id']}", headers=admin_headers, json={"name": "Nodo renombrado"})
    assert r.status_code == 200 and r.json()["name"] == "Nodo renombrado"

async def test_actualizar_rtsp_enmascarada_conserva_clave_y_aplica_la_nueva_direccion(
    client: AsyncClient, admin_headers: dict, db_session
):
    room = (
        await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 997"})
    ).json()
    device = (
        await client.post(
            f"{API}/devices",
            headers=admin_headers,
            json={
                "room_id": room["id"],
                "device_type": "camara",
                "device_key": "cam-rtsp-edit-test",
                "rtsp_url": "rtsp://admin:sample-password@192.0.2.10:554/Streaming/Channels/101",
            },
        )
    ).json()

    response = await client.patch(
        f"{API}/devices/{device['id']}",
        headers=admin_headers,
        json={
            "rtsp_url": "rtsp://admin:***@192.0.2.11:554/Streaming/Channels/102",
        },
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(await db_session.get(Device, device["id"]))
    updated = await db_session.get(Device, device["id"])
    assert updated.rtsp_url == (
        "rtsp://admin:sample-password@192.0.2.11:554/Streaming/Channels/102"
    )

async def test_crear_docente_validaciones(client: AsyncClient, admin_headers: dict):
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Mal DNI", "email": "mal.dni@unamba.edu.pe", "dni": "123"})
    assert r.status_code == 422

    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Correo Gmail", "email": "alguien@gmail.com", "dni": "71122334"})
    assert r.status_code == 422
    assert "unamba.edu.pe" in r.json()["detail"]

    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Temporal Bloque4", "email": "temp.docente.b4@unamba.edu.pe",
                                "dni": "71123456", "whatsapp": "900111222"})
    assert r.status_code == 201, r.text
    teacher = r.json()
    assert teacher["role"] == "docente"
    assert teacher["must_change_password"] is True

    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Duplicado", "email": "temp.docente.b4@unamba.edu.pe",
                                "dni": "71123457"})
    assert r.status_code == 409

    r = await client.post(f"{API}/accounts/{teacher['id']}/send-temp-password", headers=admin_headers)
    assert r.status_code == 200
    assert "enviadas" in r.json()["message"] or "enviado" in r.json()["message"]

async def test_crear_estudiante_y_ciclo(client: AsyncClient, admin_headers: dict):
    r = await client.post(f"{API}/students", headers=admin_headers,
                          json={"full_name": "Estudiante Temporal Bloque4", "email": "temp.estudiante.b4@unamba.edu.pe",
                                "dni": "71234501", "code": "998877", "semester": 9})
    assert r.status_code == 201, r.text
    student = r.json()
    assert student["role"] == "estudiante" and student["code"] == "998877"

    r = await client.post(f"{API}/students", headers=admin_headers,
                          json={"full_name": "Otro Estudiante", "email": "temp.estudiante.b5@unamba.edu.pe",
                                "dni": "71234502", "code": "998877", "semester": 9})
    assert r.status_code == 409

    r = await client.get(f"{API}/students", headers=admin_headers, params={"semester": 9, "q": "Bloque4"})
    assert r.status_code == 200
    assert any(s["id"] == student["id"] for s in r.json()["items"])

async def test_estudiantes_se_listan_del_mas_reciente_al_mas_antiguo(
    client: AsyncClient, admin_headers: dict
):
    created_ids = []
    for index, (email, dni, code) in enumerate(
        [
            ("temp.estudiante.reciente1@unamba.edu.pe", "71234511", "998871"),
            ("temp.estudiante.reciente2@unamba.edu.pe", "71234512", "998872"),
        ],
        start=1,
    ):
        response = await client.post(
            f"{API}/students",
            headers=admin_headers,
            json={
                "full_name": f"Estudiante Reciente {index}",
                "email": email,
                "dni": dni,
                "code": code,
                "semester": 1,
            },
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["id"])

    response = await client.get(
        f"{API}/students",
        headers=admin_headers,
        params={"q": "Estudiante Reciente", "page_size": 1},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["id"] == created_ids[-1]

async def test_admin_no_se_crea_por_api_y_patch_protege_admin(client: AsyncClient, admin_headers: dict):
    me = (await client.get(f"{API}/auth/me", headers=admin_headers)).json()
    r = await client.patch(f"{API}/accounts/{me['id']}", headers=admin_headers, json={"full_name": "Otro"})
    assert r.status_code == 403

    teacher = (await client.post(
        f"{API}/teachers", headers=admin_headers,
        json={"full_name": "Docente Para Patch", "email": "temp.docente.patch@unamba.edu.pe", "dni": "71234600"},
    )).json()
    r = await client.patch(f"{API}/accounts/{teacher['id']}", headers=admin_headers,
                           json={"whatsapp": "955666777", "is_active": False})
    assert r.status_code == 200
    assert r.json()["whatsapp"] == "955666777" and r.json()["is_active"] is False

async def test_docente_sin_grupos_no_ve_estudiantes(
    client: AsyncClient, docente_headers: dict, temp_student: AppUser
):
    r = await client.get(f"{API}/students", headers=docente_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0 and r.json()["items"] == []
    r = await client.get(f"{API}/accounts/{temp_student.id}", headers=docente_headers)
    assert r.status_code == 403

async def test_temp_user_fixture_intacto(client: AsyncClient, temp_user: AppUser):
    assert temp_user.email == TEMP_EMAIL

async def test_students_with_face_flag(client, admin_headers, db_session):
    alumno = (await db_session.exec(select(AppUser).where(AppUser.code == "221181"))).one()
    embedding = FaceEmbedding(student_id=alumno.id, vector=[0.0] * 512)
    db_session.add(embedding)
    await db_session.commit()
    try:
        r = await client.get(
            f"{API}/students", headers=admin_headers,
            params={"with_face": "true", "page_size": 50},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items
        raul = next((i for i in items if i["code"] == "221181"), None)
        assert raul is not None and raul["enrolled"] is True
    finally:
        await db_session.delete(embedding)
        await db_session.commit()

    r = await client.get(f"{API}/students", headers=admin_headers, params={"page_size": 5})
    assert r.status_code == 200
    assert all(i["enrolled"] is None for i in r.json()["items"])


async def test_camara_valida_la_direccion_y_toma_la_ip_del_rtsp(
    client: AsyncClient, admin_headers: dict, db_session
):
    from sqlmodel import delete

    await db_session.exec(delete(Device).where(Device.device_key.in_(["cam-ip-test", "esp32-ip-test"])))
    await db_session.exec(delete(Room).where(Room.code == "LAB 995"))
    await db_session.commit()
    room = (await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 995"})).json()
    try:
        malo = await client.post(
            f"{API}/devices", headers=admin_headers,
            json={"room_id": room["id"], "device_type": "camara", "device_key": "cam-ip-test",
                  "rtsp_url": "rtsp://admin:clave@10.14.5.2474:554/Streaming/Channels/102"},
        )
        assert malo.status_code == 422 and "no es válida" in malo.json()["detail"]
        sin_esquema = await client.post(
            f"{API}/devices", headers=admin_headers,
            json={"room_id": room["id"], "device_type": "camara", "device_key": "cam-ip-test",
                  "rtsp_url": "http://admin:clave@10.14.5.20/x"},
        )
        assert sin_esquema.status_code == 422

        camara = (await client.post(
            f"{API}/devices", headers=admin_headers,
            json={"room_id": room["id"], "device_type": "camara", "device_key": "cam-ip-test",
                  "rtsp_url": "rtsp://admin:clave@192.168.1.64:554/Streaming/Channels/102"},
        )).json()
        assert camara["ip_address"] == "192.168.1.64"

        editada = await client.patch(
            f"{API}/devices/{camara['id']}", headers=admin_headers,
            json={"rtsp_url": "rtsp://admin:***@192.168.1.70:554/Streaming/Channels/101"},
        )
        assert editada.status_code == 200 and editada.json()["ip_address"] == "192.168.1.70"

        nodo = (await client.post(
            f"{API}/devices", headers=admin_headers,
            json={"room_id": room["id"], "device_type": "esp32", "device_key": "esp32-ip-test"},
        )).json()
        con_ip = await client.patch(
            f"{API}/devices/{nodo['id']}", headers=admin_headers, json={"ip_address": "192.168.1.90"}
        )
        assert con_ip.json()["ip_address"] == "192.168.1.90"
        ip_mala = await client.patch(
            f"{API}/devices/{nodo['id']}", headers=admin_headers, json={"ip_address": "300.1.1.1"}
        )
        assert ip_mala.status_code == 422
        rtsp_en_nodo = await client.patch(
            f"{API}/devices/{nodo['id']}", headers=admin_headers,
            json={"rtsp_url": "rtsp://a:b@192.168.1.5/x"},
        )
        assert rtsp_en_nodo.status_code == 422
    finally:
        await db_session.exec(delete(Device).where(Device.device_key.in_(["cam-ip-test", "esp32-ip-test"])))
        await db_session.exec(delete(Room).where(Room.code == "LAB 995"))
        await db_session.commit()
