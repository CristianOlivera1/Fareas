"""Tests del catálogo - RF-02, RF-03, RF-05, RF-08, RF-35 (contra la BD fareas real)."""
import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.tables import AppUser, Device, Room
from tests.conftest import TEMP_EMAIL

pytestmark = pytest.mark.asyncio

API = "/api/v1"

_EMAILS_TMP = [
    "temp.docente.leer@unamba.edu.pe",
    "temp.docente.b4@unamba.edu.pe",
    "temp.estudiante.b4@unamba.edu.pe",
    "temp.estudiante.b5@unamba.edu.pe",
    "temp.docente.patch@unamba.edu.pe",
]


async def _purge(db_session) -> None:
    """Elimina los datos temporales de este módulo (idempotencia entre corridas)."""
    await db_session.exec(delete(AppUser).where(AppUser.email.in_(_EMAILS_TMP)))  # type: ignore[attr-defined]
    await db_session.exec(delete(Device).where(Device.device_key == "esp32-lab998"))  # type: ignore[attr-defined]
    await db_session.exec(delete(Room).where(Room.code.in_(["LAB 999", "LAB 998", "LAB 997"])))  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.fixture(autouse=True)
async def _limpieza(db_session):
    await _purge(db_session)
    yield
    await _purge(db_session)


# ---------------------------------------------------------------------------
# Autorización (RF-01): solo admin escribe; docente lee
# ---------------------------------------------------------------------------
async def test_listas_requieren_token(client: AsyncClient):
    assert (await client.get(f"{API}/rooms")).status_code == 401
    assert (await client.get(f"{API}/teachers")).status_code == 401
    assert (await client.get(f"{API}/students")).status_code == 401


async def test_docente_puede_leer_pero_no_crear(
    client: AsyncClient, admin_headers: dict, docente_headers: dict
):
    # Docente de prueba (la limpieza autouse lo elimina al terminar)
    r = await client.post(
        f"{API}/teachers",
        headers=admin_headers,
        json={"full_name": "Prueba Docente Lectura", "email": "temp.docente.leer@unamba.edu.pe", "dni": "71112233"},
    )
    assert r.status_code == 201, r.text

    doc_headers = docente_headers  # docente de PRUEBA (no depende del seed)

    # Lee OK…
    assert (await client.get(f"{API}/teachers", headers=doc_headers)).status_code == 200
    assert (await client.get(f"{API}/rooms", headers=doc_headers)).status_code == 200
    # …pero no crea (RF-01: solo admin escribe)
    r = await client.post(
        f"{API}/teachers",
        headers=doc_headers,
        json={"full_name": "No Permitido", "email": "x@unamba.edu.pe", "dni": "70000001"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Aulas - RF-05
# ---------------------------------------------------------------------------
async def test_crud_aulas(client: AsyncClient, admin_headers: dict):
    # Crear
    r = await client.post(f"{API}/rooms", headers=admin_headers,
                          json={"code": "LAB 999", "name": "Laboratorio de pruebas"})
    assert r.status_code == 201, r.text
    room = r.json()
    assert room["code"] == "LAB 999"

    # Duplicada → 409
    r = await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "lab 999"})
    assert r.status_code == 409

    # Listado con filtro
    r = await client.get(f"{API}/rooms", headers=admin_headers, params={"q": "999"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1 and any(x["id"] == room["id"] for x in data["items"])

    # Actualizar (normaliza a mayúsculas al crear; PATCH cambia nombre/estado)
    r = await client.patch(f"{API}/rooms/{room['id']}", headers=admin_headers,
                           json={"name": "Laboratorio renombrado", "is_active": False})
    assert r.status_code == 200
    assert r.json()["name"] == "Laboratorio renombrado"
    assert r.json()["is_active"] is False


async def test_crear_aula_requiere_admin(client: AsyncClient):
    r = await client.post(f"{API}/rooms", json={"code": "LAB X"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Dispositivos - RF-05, RF-35
# ---------------------------------------------------------------------------
async def test_dispositivos_flujo_basico(client: AsyncClient, admin_headers: dict):
    # Aula nueva para no ensuciar el seed
    room = (await client.post(f"{API}/rooms", headers=admin_headers, json={"code": "LAB 998"})).json()

    # Cámara sin rtsp_url → 422
    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "camara", "device_key": "cam-lab998"})
    assert r.status_code == 422

    # ESP32 OK
    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "esp32", "device_key": "esp32-lab998",
                                "name": "Nodo de prueba"})
    assert r.status_code == 201, r.text
    device = r.json()
    assert device["room_code"] == "LAB 998"
    assert device["is_online"] is False

    # device_key duplicado → 409
    r = await client.post(f"{API}/devices", headers=admin_headers,
                          json={"room_id": room["id"], "device_type": "esp32", "device_key": "esp32-lab998"})
    assert r.status_code == 409

    # RF-35: /devices/status público incluye el dispositivo nuevo
    r = await client.get(f"{API}/devices/status")
    assert r.status_code == 200
    assert any(d["device_key"] == "esp32-lab998" for d in r.json())

    # Actualizar
    r = await client.patch(f"{API}/devices/{device['id']}", headers=admin_headers, json={"name": "Nodo renombrado"})
    assert r.status_code == 200 and r.json()["name"] == "Nodo renombrado"


# ---------------------------------------------------------------------------
# Docentes / estudiantes - RF-02, RF-03, RF-08
# ---------------------------------------------------------------------------
async def test_crear_docente_validaciones(client: AsyncClient, admin_headers: dict):
    # DNI inválido → 422 (pydantic)
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Mal DNI", "email": "mal.dni@unamba.edu.pe", "dni": "123"})
    assert r.status_code == 422

    # Correo no institucional → 422 (regla de negocio RF-08)
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Correo Gmail", "email": "alguien@gmail.com", "dni": "71122334"})
    assert r.status_code == 422
    assert "unamba.edu.pe" in r.json()["detail"]

    # Docente válido → 201; MAIL_ENABLED=false, así que no hay envío real
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Temporal Bloque4", "email": "temp.docente.b4@unamba.edu.pe",
                                "dni": "71123456", "whatsapp": "900111222"})
    assert r.status_code == 201, r.text
    teacher = r.json()
    assert teacher["role"] == "docente"
    assert teacher["must_change_password"] is True  # clave temporal RF-11

    # Duplicado (mismo email) → 409
    r = await client.post(f"{API}/teachers", headers=admin_headers,
                          json={"full_name": "Docente Duplicado", "email": "temp.docente.b4@unamba.edu.pe",
                                "dni": "71123457"})
    assert r.status_code == 409

    # RF-08: reenvío de credenciales (nueva clave temporal)
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

    # Código duplicado → 409
    r = await client.post(f"{API}/students", headers=admin_headers,
                          json={"full_name": "Otro Estudiante", "email": "temp.estudiante.b5@unamba.edu.pe",
                                "dni": "71234502", "code": "998877", "semester": 9})
    assert r.status_code == 409

    # Filtro por ciclo
    r = await client.get(f"{API}/students", headers=admin_headers, params={"semester": 9, "q": "Bloque4"})
    assert r.status_code == 200
    assert any(s["id"] == student["id"] for s in r.json()["items"])


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


async def test_temp_user_fixture_intacto(client: AsyncClient, temp_user: AppUser):
    """El fixture de auth sigue usable desde este módulo (misma BD)."""
    assert temp_user.email == TEMP_EMAIL


async def test_students_with_face_flag(client, admin_headers, db_session):
    """with_face=1 añade enrolled (RF-04) con UNA query por página (no N)."""
    r = await client.get(
        f"{API}/students", headers=admin_headers,
        params={"with_face": "true", "page_size": 50},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items
    raul = next((i for i in items if i["code"] == "221181"), None)
    assert raul is not None and raul["enrolled"] is True

    r = await client.get(f"{API}/students", headers=admin_headers, params={"page_size": 5})
    assert r.status_code == 200
    assert all(i["enrolled"] is None for i in r.json()["items"])
