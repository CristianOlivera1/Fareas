from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import hash_password, verify_password
from app.tables import PasswordOtp

OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class OtpPurpose(StrEnum):
    RECOVER = "recover"
    CHANGE_PASSWORD = "change_password"

class OtpError(Exception):
    pass

class OtpCooldownError(OtpError):
    def __init__(self, seconds: int) -> None:
        self.seconds = max(1, seconds)
        super().__init__(f"Espera {self.seconds} segundos antes de solicitar otro código")

class OtpExpiredError(OtpError):
    pass

class OtpAttemptsExceededError(OtpError):
    pass

class OtpInvalidError(OtpError):
    pass

class OtpNotVerifiedError(OtpError):
    pass

class OtpUsedError(OtpError):
    pass

def _now() -> datetime:
    return datetime.now(UTC)

async def _get(db: AsyncSession, user_id: int, purpose: str | OtpPurpose) -> PasswordOtp | None:
    query = select(PasswordOtp).where(
        PasswordOtp.user_id == user_id,
        PasswordOtp.purpose == str(purpose),
    )
    return (await db.exec(query)).first()

async def _drop(db: AsyncSession, row: PasswordOtp) -> None:
    await db.delete(row)
    await db.commit()

async def issue(db: AsyncSession, user_id: int, purpose: str | OtpPurpose) -> str:
    now = _now()
    row = await _get(db, user_id, purpose)
    if row is not None and row.consumed_at is None and row.expires_at > now:
        elapsed = (now - row.sent_at).total_seconds()
        if elapsed < OTP_RESEND_SECONDS:
            raise OtpCooldownError(math.ceil(OTP_RESEND_SECONDS - elapsed))

    code = f"{secrets.randbelow(1_000_000):06d}"
    if row is None:
        row = PasswordOtp(user_id=user_id, purpose=str(purpose))
    row.code_hash = hash_password(code)
    row.sent_at = now
    row.expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)
    row.attempts = 0
    row.verified = False
    row.consumed_at = None
    db.add(row)
    await db.commit()
    return code

async def verify(db: AsyncSession, user_id: int, purpose: str | OtpPurpose, code: str) -> None:
    row = await _get(db, user_id, purpose)
    now = _now()
    if row is None or row.expires_at <= now:
        if row is not None:
            await _drop(db, row)
        raise OtpExpiredError("Código expirado o inexistente")

    if row.consumed_at is not None:
        raise OtpUsedError("Este código ya se usó; solicita uno nuevo")

    if row.attempts >= OTP_MAX_ATTEMPTS:
        await _drop(db, row)
        raise OtpAttemptsExceededError("Demasiados intentos; solicita otro código")

    row.attempts += 1
    db.add(row)
    await db.commit()

    if not verify_password(code, row.code_hash):
        raise OtpInvalidError("Código incorrecto")

    row.verified = True
    db.add(row)
    await db.commit()

async def consume(db: AsyncSession, user_id: int, purpose: str | OtpPurpose) -> None:
    row = await _get(db, user_id, purpose)
    now = _now()
    if row is None or row.expires_at <= now:
        if row is not None:
            await _drop(db, row)
        raise OtpExpiredError("El código expiró; solicita uno nuevo")
    if row.consumed_at is not None:
        raise OtpUsedError("Este código ya se usó; solicita uno nuevo")
    if not row.verified:
        raise OtpNotVerifiedError("Verifica el código antes de continuar")

    row.consumed_at = now
    db.add(row)
    await db.commit()

async def clear(db: AsyncSession) -> None:
    rows = (await db.exec(select(PasswordOtp))).all()
    for row in rows:
        await db.delete(row)
    await db.commit()

def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + "*" * (len(local) - 2)
    return f"{masked}@{domain}"
