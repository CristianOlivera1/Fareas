"""Tests de autenticación - RF-01, RF-11, RF-12 (contra la BD fareas real)."""
import pytest
from httpx import AsyncClient

from app.core.security import hash_password
from app.routers.auth import _otp_store
from app.tables import AppUser

pytestmark = pytest.mark.asyncio

API = "/api/v1/auth"


async def _login(client: AsyncClient, email: str, password: str):
    """``email`` acepta correo institucional O código de matrícula (RF-11)."""
    return await client.post(f"{API}/login", json={"email": email, "password": password})


async def test_login_con_clave_temporal(client: AsyncClient, temp_user: AppUser):
    r = await _login(client, temp_user.email, "ClaveTemporal1")
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == temp_user.email
    assert data["user"]["role"] == "admin"
    assert data["user"]["must_change_password"] is True  # RF-11: obliga al cambio


async def test_login_rechaza_credenciales_malas(client: AsyncClient, temp_user: AppUser):
    r = await _login(client, temp_user.email, "clave-incorrecta")
    assert r.status_code == 401


async def test_me_requiere_token(client: AsyncClient):
    r = await client.get(f"{API}/me")
    assert r.status_code == 401


async def test_me_con_token_valido(client: AsyncClient, temp_user: AppUser):
    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    r = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == temp_user.email


async def test_cambio_de_clave_flujo_completo(client: AsyncClient, temp_user: AppUser):
    """RF-11: cambia la clave temporal y el flag must_change_password se apaga."""
    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Clave actual incorrecta → 400
    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "otra-clave", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 400

    # Cambio correcto
    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 200

    # Re-login con la nueva clave: must_change_password ya no está activo
    r = await _login(client, temp_user.email, "NuevaClave99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

    # La clave vieja ya no sirve
    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 401


async def test_recuperacion_otp_flujo_completo(client: AsyncClient, temp_user: AppUser):
    """RF-12: recover → verify OTP → reset → login con la nueva clave.

    MAIL_ENABLED=false en pruebas: el código queda en _otp_store; para el test
    se reemplaza su hash por uno conocido ('123456').
    """
    email = temp_user.email
    r = await client.post(f"{API}/recover", json={"email": email})
    assert r.status_code == 200  # respuesta uniforme aunque el correo no exista
    assert email in _otp_store, "el OTP se generó en memoria"

    _otp_store[email]["hash"] = hash_password("123456")

    # Código incorrecto → 400 y consume un intento
    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "999999"})
    assert r.status_code == 400

    # Código correcto
    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "123456"})
    assert r.status_code == 200

    # Reset sin OTP verificado en otra cuenta no aplica; aquí sí está verificado:
    r = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Reseteada99"},
    )
    assert r.status_code == 200

    # El store se limpia tras el reset
    assert email not in _otp_store

    # Login con la nueva contraseña
    r = await _login(client, email, "Reseteada99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False


async def test_reset_sin_verificar_otp_falla(client: AsyncClient, temp_user: AppUser):
    email = temp_user.email
    await client.post(f"{API}/recover", json={"email": email})
    # NO verificamos el OTP: el reseteo debe rechazarse
    r = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Hackeada99"},
    )
    assert r.status_code == 400
