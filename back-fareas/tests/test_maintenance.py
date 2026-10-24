from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import delete, select

from app.services.maintenance import purge_expired_credentials
from app.tables import AppUser, PasswordOtp, RefreshToken, UserRole

EMAIL = "temp.maintenance@unamba.edu.pe"


@pytest.fixture
async def user(db_session):
    await db_session.exec(delete(AppUser).where(AppUser.email == EMAIL))
    await db_session.commit()
    account = AppUser(
        role=UserRole.ESTUDIANTE, email=EMAIL, code="992001", full_name="Mantenimiento",
        password_hash="x" * 20, must_change_password=False,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    yield account
    await db_session.exec(delete(AppUser).where(AppUser.id == account.id))
    await db_session.commit()


def _token(user_id: int, now: datetime, expires_in_days: float, revoked_days_ago: float | None = None):
    return RefreshToken(
        user_id=user_id,
        family_id=uuid4(),
        token_hash=uuid4().hex + uuid4().hex,
        issued_at=now - timedelta(days=60),
        expires_at=now + timedelta(days=expires_in_days),
        revoked_at=None if revoked_days_ago is None else now - timedelta(days=revoked_days_ago),
    )


async def test_purges_only_stale_credentials(db_session, user):
    now = datetime.now(UTC)
    keep_valid = _token(user.id, now, expires_in_days=10)
    keep_recent_expired = _token(user.id, now, expires_in_days=-2)
    keep_recent_revoked = _token(user.id, now, expires_in_days=10, revoked_days_ago=3)
    drop_expired = _token(user.id, now, expires_in_days=-10)
    drop_revoked = _token(user.id, now, expires_in_days=10, revoked_days_ago=40)
    otp_old = PasswordOtp(user_id=user.id, purpose="recover", code_hash="h", sent_at=now - timedelta(days=3),
                          expires_at=now - timedelta(days=2))
    db_session.add_all([keep_valid, keep_recent_expired, keep_recent_revoked, drop_expired, drop_revoked, otp_old])
    await db_session.commit()

    removed = await purge_expired_credentials(db_session, now)

    assert removed["refresh_tokens"] >= 2
    assert removed["password_otps"] >= 1
    remaining = {
        row.token_hash
        for row in (await db_session.exec(select(RefreshToken).where(RefreshToken.user_id == user.id))).all()
    }
    assert remaining == {keep_valid.token_hash, keep_recent_expired.token_hash, keep_recent_revoked.token_hash}
    assert (await db_session.exec(select(PasswordOtp).where(PasswordOtp.user_id == user.id))).first() is None
