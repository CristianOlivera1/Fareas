from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import hash_password, hash_refresh_token
from app.services import otp
from app.tables import AppUser, AuditLog, RefreshToken

pytestmark = pytest.mark.asyncio

API = "/api/v1/auth"
PASSWORD = "ClaveTemporal1"


async def _login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict:
    r = await client.post(f"{API}/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _refresh(client: AsyncClient, refresh_token: str):
    return await client.post(f"{API}/refresh", json={"refresh_token": refresh_token})


async def _rows(db: SQLModelAsyncSession, user_id: int) -> list[RefreshToken]:
    db.expire_all()
    result = await db.exec(
        select(RefreshToken).where(RefreshToken.user_id == user_id).order_by(RefreshToken.id)
    )
    return list(result.all())


async def test_login_emits_refresh_token_and_stores_only_its_hash(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    data = await _login(client, temp_user.email)

    assert data["token_type"] == "bearer"
    assert data["refresh_token"].startswith("rt_")
    assert data["expires_in"] == 120 * 60
    assert data["refresh_expires_in"] > 0
    assert (await client.get(f"{API}/me", headers=_bearer(data["access_token"]))).status_code == 200

    rows = await _rows(db_session, user_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.token_hash == hash_refresh_token(data["refresh_token"])
    assert row.token_hash != data["refresh_token"]
    assert row.family_id is not None
    assert row.revoked_at is None


async def test_refresh_rotates_token_and_keeps_the_family_expiry(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    login = await _login(client, temp_user.email)
    original = (await _rows(db_session, user_id))[0]
    original_expiry = original.expires_at

    r = await _refresh(client, login["refresh_token"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["refresh_token"] != login["refresh_token"]
    assert data["access_token"] != login["access_token"]
    assert (await client.get(f"{API}/me", headers=_bearer(data["access_token"]))).status_code == 200

    rows = await _rows(db_session, user_id)
    assert len(rows) == 2
    old, new = rows
    assert old.revoked_at is not None
    assert old.revoked_reason == "rotated"
    assert old.replaced_by_id == new.id
    assert new.revoked_at is None
    assert new.family_id == old.family_id
    assert new.expires_at == original_expiry

    r = await _refresh(client, data["refresh_token"])
    assert r.status_code == 200, r.text


async def test_reusing_rotated_token_revokes_the_whole_family(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    login = await _login(client, temp_user.email)
    first = await _refresh(client, login["refresh_token"])
    assert first.status_code == 200, first.text
    new_token = first.json()["refresh_token"]

    r = await _refresh(client, login["refresh_token"])
    assert r.status_code == 401
    assert "Sesión inválida" in r.json()["detail"]

    r = await _refresh(client, new_token)
    assert r.status_code == 401

    rows = await _rows(db_session, user_id)
    assert all(row.revoked_at is not None for row in rows)
    assert any(row.revoked_reason == "reuse_detected" for row in rows)

    db_session.expire_all()
    audit_row = (
        await db_session.exec(
            select(AuditLog).where(
                AuditLog.actor_id == user_id,
                AuditLog.action == "refresh_token_reuse",
            )
        )
    ).first()
    assert audit_row is not None


async def test_expired_refresh_token_is_rejected(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    login = await _login(client, temp_user.email)
    row = (await _rows(db_session, user_id))[0]
    now = datetime.now(UTC)
    row.issued_at = now - timedelta(days=2)
    row.expires_at = now - timedelta(days=1)
    db_session.add(row)
    await db_session.commit()

    r = await _refresh(client, login["refresh_token"])
    assert r.status_code == 401

    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "expired"


async def test_inactive_user_cannot_refresh(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    login = await _login(client, temp_user.email)

    temp_user.is_active = False
    db_session.add(temp_user)
    await db_session.commit()

    r = await _refresh(client, login["refresh_token"])
    assert r.status_code == 401

    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "user_inactive"


async def test_password_change_revokes_old_sessions_and_returns_new_pair(
    client: AsyncClient,
    temp_user: AppUser,
):
    login = await _login(client, temp_user.email)
    old_access = login["access_token"]
    old_refresh = login["refresh_token"]

    r = await client.post(
        f"{API}/change-password",
        headers=_bearer(old_access),
        json={"current_password": PASSWORD, "new_password": "NuevaClave99"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["refresh_token"].startswith("rt_")
    assert data["refresh_token"] != old_refresh
    assert data["expires_in"] == 120 * 60
    assert data["refresh_expires_in"] > 0

    assert (await client.get(f"{API}/me", headers=_bearer(old_access))).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(data["access_token"]))).status_code == 200
    assert (await _refresh(client, old_refresh)).status_code == 401
    assert (await _refresh(client, data["refresh_token"])).status_code == 200

    assert (await _login(client, temp_user.email, "NuevaClave99"))["refresh_token"]


async def test_password_reset_revokes_refresh_tokens(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    email = temp_user.email
    login = await _login(client, email)

    r = await client.post(f"{API}/recover", json={"email": email})
    assert r.status_code == 200
    key = (user_id, otp.OtpPurpose.RECOVER)
    assert key in otp._store
    otp._store[key].code_hash = hash_password("123456")

    assert (
        await client.post(
            f"{API}/recover/verify",
            json={"email": email, "code": "123456"},
        )
    ).status_code == 200
    assert (
        await client.post(
            f"{API}/recover/reset",
            json={
                "email": email,
                "code": "123456",
                "new_password": "Reseteada99",
            },
        )
    ).status_code == 200

    assert (await _refresh(client, login["refresh_token"])).status_code == 401
    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "password_reset"
    assert (await _login(client, email, "Reseteada99"))["refresh_token"]


async def test_logout_revokes_refresh_family_idempotently(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    login = await _login(client, temp_user.email)

    r = await client.post(f"{API}/logout", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 204
    assert (await _refresh(client, login["refresh_token"])).status_code == 401

    r = await client.post(f"{API}/logout", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 204
    r = await client.post(f"{API}/logout", json={"refresh_token": "rt_" + "x" * 64})
    assert r.status_code == 204

    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "logout"


async def test_logout_all_revokes_every_session_and_access_token(
    client: AsyncClient,
    temp_user: AppUser,
    db_session: SQLModelAsyncSession,
):
    user_id = temp_user.id
    first = await _login(client, temp_user.email)
    second = await _login(client, temp_user.email)

    r = await client.post(f"{API}/logout-all", headers=_bearer(first["access_token"]))
    assert r.status_code == 204

    assert (await _refresh(client, first["refresh_token"])).status_code == 401
    assert (await _refresh(client, second["refresh_token"])).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(first["access_token"]))).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(second["access_token"]))).status_code == 401

    rows = await _rows(db_session, user_id)
    assert len(rows) == 2
    assert all(row.revoked_reason == "logout_all" for row in rows)


async def test_refresh_rejects_malformed_token(client: AsyncClient):
    r = await client.post(f"{API}/refresh", json={"refresh_token": "corto"})
    assert r.status_code == 422


async def test_resend_temp_password_revokes_sessions(
    client: AsyncClient,
    temp_student: AppUser,
    admin_headers: dict[str, str],
    db_session: SQLModelAsyncSession,
):
    user_id = temp_student.id
    login = await _login(client, temp_student.email)

    r = await client.post(
        f"/api/v1/accounts/{user_id}/send-temp-password",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text

    assert (await _refresh(client, login["refresh_token"])).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(login["access_token"]))).status_code == 401
    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "temporary_password_resent"


async def test_deactivating_account_revokes_sessions(
    client: AsyncClient,
    temp_student: AppUser,
    admin_headers: dict[str, str],
    db_session: SQLModelAsyncSession,
):
    user_id = temp_student.id
    login = await _login(client, temp_student.email)

    r = await client.patch(
        f"/api/v1/accounts/{user_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert r.status_code == 200, r.text

    assert (await _refresh(client, login["refresh_token"])).status_code == 401
    assert (await client.get(f"{API}/me", headers=_bearer(login["access_token"]))).status_code == 401
    rows = await _rows(db_session, user_id)
    assert rows[0].revoked_reason == "account_deactivated"
