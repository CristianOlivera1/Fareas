"""Seguridad: hash de contraseñas (argon2id) y tokens JWT (RF-11).

- Hash: pwdlib con formato PHC ($argon2id$v=19$...) - el mismo que ya usan
  los seeds de la base de datos.
- JWT: pyjwt HS256 con claims `sub` (id de usuario), `role` (RF-01) y `exp`.
- Sin refresh tokens (decisión PLAN §7): JWT simple de 120 min; el logout
  es cliente (descartar el token) y la expiración obliga a re-login.
"""
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_pwd = PasswordHash.recommended()  # argon2id


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(plain, password_hash)
    except Exception:  # noqa: BLE001 - hash corrupto no debe tumbar el request
        return False


# ---------------------------------------------------------------------------
# Access token (JWT)
# ---------------------------------------------------------------------------
def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class TokenPayload:
    """Claims validados del token de acceso."""

    __slots__ = ("user_id", "role", "expires_at")

    def __init__(self, user_id: int, role: str, expires_at: datetime):
        self.user_id = user_id
        self.role = role
        self.expires_at = expires_at


def decode_access_token(token: str) -> TokenPayload:
    """Lanza jwt.ExpiredSignatureError / jwt.InvalidTokenError si es inválido."""
    settings = get_settings()
    claims = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return TokenPayload(
        user_id=int(claims["sub"]),
        role=str(claims["role"]),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
