from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import hash_password
from app.main import create_app
from app.services import otp
from app.tables import AppUser, PasswordOtp

pytestmark = pytest.mark.asyncio

API = "/api/v1/auth"


async def _otp_row(
    db: SQLModelAsyncSession, user_id: int, purpose: otp.OtpPurpose
) -> PasswordOtp | None:
    query = select(PasswordOtp).where(
        PasswordOtp.user_id == user_id,
        PasswordOtp.purpose == str(purpose),
    )
    return (await db.exec(query)).first()

async def _set_otp_code(
    db: SQLModelAsyncSession, user_id: int, purpose: otp.OtpPurpose, code: str
) -> PasswordOtp:
    row = await _otp_row(db, user_id, purpose)
    assert row is not None, "el OTP debe quedar guardado en la base de datos"
    row.code_hash = hash_password(code)
    db.add(row)
    await db.commit()
    return row


async def _login(client: AsyncClient, email: str, password: str):
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
    assert data["user"]["must_change_password"] is True

async def test_login_rechaza_credenciales_malas(client: AsyncClient, temp_user: AppUser):
    r = await _login(client, temp_user.email, "clave-incorrecta")
    assert r.status_code == 401

async def test_login_rate_limit(client: AsyncClient, temp_user: AppUser):
    from app.routers.auth import _login_attempts

    _login_attempts.clear()
    for _ in range(5):
        r = await _login(client, temp_user.email, "clave-incorrecta")
        assert r.status_code == 401
    r = await _login(client, temp_user.email, "ClaveTemporal1")
    assert r.status_code == 429
    r = await _login(client, temp_user.email, "ClaveTemporal1")
    assert r.status_code == 429

    _login_attempts.clear()

async def test_login_correcto_limpia_rate_limit(client: AsyncClient, temp_user: AppUser):
    from app.routers.auth import _login_attempts

    _login_attempts.clear()
    for _ in range(3):
        assert (await _login(client, temp_user.email, "clave-incorrecta")).status_code == 401
    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 200
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
    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)

    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "otra-clave", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 400

    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert new_token

    assert (await client.get(f"{API}/me", headers=headers)).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(new_token))).status_code == 200

    r = await _login(client, temp_user.email, "NuevaClave99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

    assert (await _login(client, temp_user.email, "ClaveTemporal1")).status_code == 401

async def test_cambio_clave_voluntario_exige_otp(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    temp_user.must_change_password = False
    db_session.add(temp_user)
    await db_session.commit()

    token = (await _login(client, temp_user.email, "ClaveTemporal1")).json()["access_token"]
    headers = _bearer(token)

    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 400
    assert "código" in r.json()["detail"].lower()

    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "otra-clave"},
    )
    assert r.status_code == 400

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

    await _set_otp_code(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD, "654321")

    r = await client.post(
        f"{API}/change-password/otp",
        headers=headers,
        json={"current_password": "ClaveTemporal1"},
    )
    assert r.status_code == 429

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

    r = await client.post(
        f"{API}/change-password",
        headers=headers,
        json={"current_password": "ClaveTemporal1", "new_password": "NuevaClave99"},
    )
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert new_token
    consumed = await _otp_row(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    assert consumed is not None and consumed.consumed_at is not None

    assert (await client.get(f"{API}/me", headers=headers)).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(new_token))).status_code == 200

    r = await _login(client, temp_user.email, "NuevaClave99")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

async def test_cambio_clave_otp_expira(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
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

    row = await _otp_row(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    assert row is not None
    row.sent_at = datetime.now(UTC) - timedelta(minutes=11)
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add(row)
    await db_session.commit()

    r = await client.post(
        f"{API}/change-password/otp/verify",
        headers=headers,
        json={"code": "123456"},
    )
    assert r.status_code == 400
    assert "expir" in r.json()["detail"].lower()
    assert await _otp_row(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD) is None

async def test_cambio_clave_otp_max_intentos(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
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

    await _set_otp_code(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD, "654321")

    for _ in range(otp.OTP_MAX_ATTEMPTS):
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
    assert r.status_code == 429
    assert await _otp_row(db_session, temp_user.id, otp.OtpPurpose.CHANGE_PASSWORD) is None

async def test_recuperacion_otp_flujo_completo(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    email = temp_user.email
    r = await client.post(f"{API}/recover", json={"email": email})
    assert r.status_code == 200

    await _set_otp_code(db_session, temp_user.id, otp.OtpPurpose.RECOVER, "123456")

    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "999999"})
    assert r.status_code == 400

    r = await client.post(f"{API}/recover/verify", json={"email": email, "code": "123456"})
    assert r.status_code == 200

    r = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Reseteada"},
    )
    assert r.status_code == 200

    used = await _otp_row(db_session, temp_user.id, otp.OtpPurpose.RECOVER)
    assert used is not None and used.consumed_at is not None

    r = await _login(client, email, "Reseteada")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is False

async def test_recuperacion_otp_sobrevive_reinicio(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    email = temp_user.email
    await client.post(f"{API}/recover", json={"email": email})
    await _set_otp_code(db_session, temp_user.id, otp.OtpPurpose.RECOVER, "123456")

    assert (
        await client.post(f"{API}/recover/verify", json={"email": email, "code": "123456"})
    ).status_code == 200

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as fresh:
        r = await fresh.post(
            f"{API}/recover/reset",
            json={"email": email, "code": "123456", "new_password": "Reseteada99"},
        )
    assert r.status_code == 200

async def test_recuperacion_otp_usado_no_permite_otro_reset(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    email = temp_user.email
    await client.post(f"{API}/recover", json={"email": email})
    await _set_otp_code(db_session, temp_user.id, otp.OtpPurpose.RECOVER, "123456")
    await client.post(f"{API}/recover/verify", json={"email": email, "code": "123456"})

    primero = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Reseteada99"},
    )
    assert primero.status_code == 200

    segundo = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "OtraClave99"},
    )
    assert segundo.status_code == 400
    assert "ya se usó" in segundo.json()["detail"]

async def test_reset_sin_verificar_otp_falla(client: AsyncClient, temp_user: AppUser):
    email = temp_user.email
    await client.post(f"{API}/recover", json={"email": email})
    r = await client.post(
        f"{API}/recover/reset",
        json={"email": email, "code": "123456", "new_password": "Hackeada99"},
    )
    assert r.status_code == 400

async def test_recover_rejects_non_institutional_email(client: AsyncClient):
    r = await client.post(f"{API}/recover", json={"email": "persona@gmail.com"})
    assert r.status_code == 422
    assert "institucional" in r.text

async def test_recover_returns_resend_window_and_does_not_resend_during_cooldown(
    client: AsyncClient, temp_user: AppUser, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple[str, str, str]] = []

    async def capture(to: str, code: str, purpose: str = "recover") -> bool:
        calls.append((to, code, purpose))
        return True

    monkeypatch.setattr("app.routers.auth.send_otp", capture)

    r = await client.post(f"{API}/recover", json={"email": temp_user.email})
    assert r.status_code == 200
    assert r.json()["resend_in"] == otp.OTP_RESEND_SECONDS
    assert len(calls) == 1

    r = await client.post(f"{API}/recover", json={"email": temp_user.email})
    assert r.status_code == 200
    assert r.json()["resend_in"] == otp.OTP_RESEND_SECONDS
    assert len(calls) == 1

async def test_recover_unknown_email_keeps_generic_response(client: AsyncClient):
    r = await client.post(f"{API}/recover", json={"email": "nadie@unamba.edu.pe"})
    assert r.status_code == 200
    assert r.json()["resend_in"] == otp.OTP_RESEND_SECONDS
    assert "Si el correo existe" in r.json()["message"]

async def test_recover_survives_email_failure(
    client: AsyncClient, temp_user: AppUser, monkeypatch: pytest.MonkeyPatch
):
    async def fail(*_args, **_kwargs) -> bool:
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.routers.auth.send_otp", fail)

    r = await client.post(f"{API}/recover", json={"email": temp_user.email})
    assert r.status_code == 200
    assert r.json()["resend_in"] == otp.OTP_RESEND_SECONDS

async def test_reset_rejects_weak_password(client: AsyncClient, temp_user: AppUser):
    r = await client.post(
        f"{API}/recover/reset",
        json={
            "email": temp_user.email,
            "code": "123456",
            "new_password": "12345678",
        },
    )
    assert r.status_code == 422
    assert "al menos una letra" in r.text
