import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.services.audit import audit
from app.tables import AppUser, RefreshToken

logger = logging.getLogger("fareas.auth.refresh")


class RefreshTokenError(Exception):
    """Refresh token inválido, expirado, reutilizado o de un usuario inactivo."""


class RefreshTokenReuseError(RefreshTokenError):
    """Se presentó un token ya rotado: se revoca toda la familia."""


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    refresh_token_id: int


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _remaining_seconds(expires_at: datetime, now: datetime) -> int:
    return max(0, int((expires_at - now).total_seconds()))


async def _revoke_family(
    db: SQLModelAsyncSession,
    family_id: UUID,
    reason: str,
    now: datetime,
) -> None:
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason=reason)
        .execution_options(synchronize_session=False)
    )
    await db.exec(stmt)


async def revoke_all_for_user(
    db: SQLModelAsyncSession,
    user_id: int,
    reason: str,
    *,
    commit: bool = True,
) -> None:
    """Revoca todas las sesiones activas del usuario (p. ej. cambio de clave)."""
    stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now(), revoked_reason=reason)
        .execution_options(synchronize_session=False)
    )
    await db.exec(stmt)
    if commit:
        await db.commit()


async def _issue(
    db: SQLModelAsyncSession,
    user: AppUser,
    *,
    now: datetime,
    family_id: UUID,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedTokens:
    settings = get_settings()
    raw_token = generate_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_refresh_token(raw_token),
        token_version=user.token_version,
        issued_at=now,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return IssuedTokens(
        access_token=create_access_token(user.id, user.role.value, user.token_version),
        refresh_token=raw_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_expires_in=_remaining_seconds(expires_at, now),
        refresh_token_id=int(row.id),
    )


async def issue_token_pair(
    db: SQLModelAsyncSession,
    user: AppUser,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> IssuedTokens:
    """Crea una familia nueva de refresh tokens para un login exitoso."""
    settings = get_settings()
    now = _now()
    return await _issue(
        db,
        user,
        now=now,
        family_id=uuid4(),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def _audit_reuse(
    db: SQLModelAsyncSession,
    row: RefreshToken,
    ip_address: str | None,
) -> None:
    user = await db.get(AppUser, row.user_id)
    if user is None:
        return
    try:
        await audit(
            db,
            user,
            action="refresh_token_reuse",
            entity="refresh_token",
            entity_id=row.id,
            new_value={"family_id": str(row.family_id)},
            ip_address=ip_address,
        )
    except Exception:
        logger.exception("No se pudo auditar la reutilización del refresh token")


async def rotate_refresh_token(
    db: SQLModelAsyncSession,
    raw_token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> IssuedTokens:
    """Valida y rota un refresh token. Un token ya usado revoca su familia."""
    token_hash = hash_refresh_token(raw_token)
    row = (
        await db.exec(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise RefreshTokenError("Refresh token desconocido")

    now = _now()
    if row.revoked_at is not None:
        if row.revoked_reason != "rotated":
            raise RefreshTokenError("Refresh token revocado")
        logger.warning(
            "Reutilización de refresh token detectada: user_id=%s family_id=%s",
            row.user_id,
            row.family_id,
        )
        await _revoke_family(db, row.family_id, "reuse_detected", now)
        await _audit_reuse(db, row, ip_address)
        await db.commit()
        raise RefreshTokenReuseError("Refresh token reutilizado")

    expires_at = _as_utc(row.expires_at)
    if expires_at <= now:
        await _revoke_family(db, row.family_id, "expired", now)
        await db.commit()
        raise RefreshTokenError("Refresh token expirado")

    user = await db.get(AppUser, row.user_id)
    if user is None or not user.is_active:
        await _revoke_family(db, row.family_id, "user_inactive", now)
        await db.commit()
        raise RefreshTokenError("Usuario inexistente o inactivo")

    if row.token_version != user.token_version:
        await _revoke_family(db, row.family_id, "token_version_changed", now)
        await db.commit()
        raise RefreshTokenError("Sesión invalidada por cambio de clave")

    row.revoked_at = now
    row.revoked_reason = "rotated"
    row.last_used_at = now
    db.add(row)

    issued = await _issue(
        db,
        user,
        now=now,
        family_id=row.family_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    row.replaced_by_id = issued.refresh_token_id
    db.add(row)
    await db.commit()
    return issued


async def revoke_refresh_token(
    db: SQLModelAsyncSession,
    raw_token: str,
    *,
    commit: bool = True,
) -> None:
    """Revoca la familia del token presentado. Idempotente y sin filtrar si existe."""
    token_hash = hash_refresh_token(raw_token)
    row = (
        await db.exec(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
    ).first()
    if row is not None and row.revoked_at is None:
        await _revoke_family(db, row.family_id, "logout", _now())
    if commit:
        await db.commit()
