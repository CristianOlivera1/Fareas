from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.tables import PasswordOtp, RefreshToken

EXPIRED_TOKEN_GRACE_DAYS = 7
REVOKED_TOKEN_RETENTION_DAYS = 30
EXPIRED_OTP_GRACE_DAYS = 1


async def purge_expired_credentials(
    db: SQLModelAsyncSession, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    tokens = await db.exec(
        delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < now - timedelta(days=EXPIRED_TOKEN_GRACE_DAYS),
                RefreshToken.revoked_at < now - timedelta(days=REVOKED_TOKEN_RETENTION_DAYS),
            )
        )
    )
    otps = await db.exec(
        delete(PasswordOtp).where(PasswordOtp.expires_at < now - timedelta(days=EXPIRED_OTP_GRACE_DAYS))
    )
    await db.commit()
    return {"refresh_tokens": tokens.rowcount, "password_otps": otps.rowcount}
