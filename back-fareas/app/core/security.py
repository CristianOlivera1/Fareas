import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_pwd = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)

def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(plain, password_hash)
    except Exception:
        return False

def generate_refresh_token() -> str:
    """Create an opaque, high-entropy refresh token. It is shown only once."""
    return f"rt_{secrets.token_urlsafe(48)}"

def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage. SHA-256 is enough for 256-bit random tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(user_id: int, role: str, token_version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "ver": token_version,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

class TokenPayload:
    __slots__ = ("user_id", "role", "token_version", "expires_at")

    def __init__(self, user_id: int, role: str, token_version: int, expires_at: datetime):
        self.user_id = user_id
        self.role = role
        self.token_version = token_version
        self.expires_at = expires_at

def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    claims = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return TokenPayload(
        user_id=int(claims["sub"]),
        role=str(claims["role"]),

        token_version=int(claims.get("ver", 0)),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
