"""Tests de autenticación - RF-01, RF-11, RF-12 (contra la BD fareas real)."""
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import hash_password
from app.services import otp
from app.tables import AppUser

pytestmark = pytest.mark.asyncio

API = "/api/v1/auth"


async def _login(client: AsyncClient, email: str, password: str):
    """``email`` acepta correo institucional O código de matrícula (RF-11)."""
    return await client.post(f"{API}/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


async def test_login_rate_limit(client: AsyncClient, temp_user: AppUser):
    """Seguridad: 5 intentos fallidos por IP/minuto → 429 aunque la clave sea buena."""
    from app.routers.auth import _login_attempts

    _login_attempts.clear()
    for _ in range(5):
        r = await _login(client, temp_user.email, "clave-incorrecta")
        assert r.status_code == 401
    # 6º intento, ahora con la clave CORRECTA: igualmente 429
    r = await _login(client, temp_user.email, "ClaveTemporal1")
    assert r.status_code == 429
    # Y sigue bloqueado un minuto más
    r = await _login(client, temp_user.email, "ClaveTemporal1")
    assert r.status_code == 429

    _login_attempts.clear()  # no contamina otros tests


async def test_login_correcto_limpia_rate_limit(client: AsyncClient, temp_user: AppUser):
    """Tras un login exitoso la ventana se reinicia: se pueden volver a fallar 5."""
    from app.routers.auth import _login_attempts

    _login_attempts.clear()
    for _ in range(3):
        assert (await _login(client, temp_user.email, "clave-incorrecta")).status_code == 401
    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 200
    # La ventana se limpió: 5 fallos nuevos no llegan a 429 hasta el 6º
    for _ in range(5):
        assert (await _login(client, temp_user.email, "clave-incorrecta")).status_code == 401
    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 429
    _login_attempts.clear()


async def test_me_requiere_token(client: AsyncClient):
    r = await client.get(f"{API}/me")
    assert r.status_code == 401


async def test_me_con_token_valido(client: AsyncClient, temp_user: AppUser):
    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    r = await client.get(f"{API}/me", headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["email"] == temp_user.email


async def test_cambio_de_clave_flujo_completo(client: AsyncClient, temp_user: AppUser):
    """RF-11: la clave temporal se cambia sin OTP y el flag se apaga.

    Además: el token viejo queda invalidado y la respuesta entrega uno nuevo
    (si no, el frontend se quedaría sin sesión justo después de cambiarla).
    """
    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)

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
    new_token = r.json()["access_token"]
    assert new_token

    # El token usado ya no sirve; el nuevo sí (token_version cambió)
    assert (await client.get(f"{API}/me", headers=headers)).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(new_token))).status_code == 200

    # Re-login con la nueva clave: must_change_password ya no está activo
    r = await _login(client, temp_user.email, "NuevaClave99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

    # La clave vieja ya no sirve
    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 401


async def test_cambio_clave_voluntario_exige_otp(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    """Cuenta normal: contraseña actual → OTP al correo → nueva contraseña."""
    temp_user.must_change_password = False
    db_session.add(temp_user)
    await db_session.commit()

    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)

    # Sin OTP verificado no se puede cambiar (aunque la clave actual sea correcta)
    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 400
    assert "código" in r.json()["detail"].lower()

    # Clave actual incorrecta al pedir el OTP → 400
    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "otra-clave"},
    )
    assert r.status_code == 400

    # Clave actual correcta → OTP creado y correo enmascarado
    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "ClaveTemporal1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email"] != temp_user.email
    assert data["email"].endswith("@unamba.edu.pe")
    assert data["expires_in"] == otp.OTP_TTL_SECONDS
    assert data["resend_in"] == otp.OTP_RESEND_SECONDS

    key = (temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    assert key in otp._store
    otp._store[key].code_hash = hash_password("654321")

    # Segundo pedido dentro del cooldown → 429
    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "ClaveTemporal1"},
    )
    assert r.status_code == 429

    # Código incorrecto → 400; correcto → 200 (queda verificado)
    r = await client.post(
        f"{API}/change-password/otp/verify",
        headers=headers,
        json={"code": "000000"},
    )
    assert r.status_code == 400
    r = await client.post(
        f"{API}/change-password/otp/verify",
        headers=headers,
        json={"code": "654321"},
    )
    assert r.status_code == 200

    # Cambio final: consume el OTP, actualiza y devuelve un token nuevo
    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert new_token
    assert key not in otp._store  # un solo uso

    # Sesiones viejas invalidadas; la nueva sigue viva
    assert (await client.get(f"{API}/me", headers=headers)).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(new_token))).status_code == 200

    # Login con la nueva clave
    r = await _login(client, temp_user.email, "NuevaClave99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False


async def test_cambio_clave_otp_expira(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    """El OTP de cambio vence a los 10 minutos y se elimina del store."""
    temp_user.must_change_password = False
    db_session.add(temp_user)
    await db_session.commit()

    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)
    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "ClaveTemporal1"},
    )
    assert r.status_code == 200

    key = (temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    otp._store[key].expires_at = 0  # forzar vencimiento

    r = await client.post(
        f"{API}/change-password/otp/verify",
        headers=headers,
        json={"code": "123456"},
    )
    assert r.status_code == 400
    assert "expir" in r.json()["detail"].lower()
    assert key not in otp._store


async def test_cambio_clave_otp_max_intentos(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    """Tras 5 códigos incorrectos el OTP se invalida aunque llegue el correcto."""
    temp_user.must_change_password = False
    db_session.add(temp_user)
    await db_session.commit()

    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)
    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "ClaveTemporal1"},
    )
    assert r.status_code == 200

    key = (temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    otp._store[key].code_hash = hash_password("654321")

    for _ in range(otp.OTP_MAX_ATTEMPTS):
        r = await client.post(
            f"{API}/change-password/otp/verify",
            headers=headers,
            json={"code": "000000"},
        )
        assert r.status_code == 400

    # El 6.º intento (aunque sea el código correcto) ya no se evalúa.
    r = await client.post(
        f"{API}/change-password/otp/verify",
        headers=headers,
        json={"code": "654321"},
    )
    assert r.status_code == 429
    assert key not in otp._store


async def test_recuperacion_otp_flujo_completo(client: AsyncClient, temp_user: AppUser):
    """RF-12: recover → verify OTP → reset → login con la nueva clave.

    MAIL_ENABLED=false en pruebas: el código queda en el store; para el test
    se reemplaza su hash por uno conocido ('123456').
    """
    email = temp_user.email
    r = await client.post(f"{API}/recover", json={"email": email})
    assert r.status_code == 200  # respuesta uniforme aunque el correo no exista

    key = (temp_user.id, otp.OtpPurpose.RECOVER)
    assert key in otp._store, "el OTP se generó en memoria"
    otp._store[key].code_hash = hash_password("123456")

    # Código incorrecto → 400 y consume un intento
    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "999999"})
    assert r.status_code == 400

    # Código correcto
    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "123456"})
    assert r.status_code == 200

    # Reset con OTP verificado
    r = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Reseteada99"},
    )
    assert r.status_code == 200

    # El store se limpia tras el reset
    assert key not in otp._store

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
