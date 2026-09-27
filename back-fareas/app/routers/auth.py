"""Autenticación y cuenta personal - RF-01, RF-08 (envío), RF-11, RF-12.

Decisión de diseño (PLAN §7): JWT de acceso simple con expiración de 120 min
SIN refresh tokens — no hay tabla de sesiones ni rotación; el logout es
cliente (descartar el token). Alcance académico, sin sobre-ingeniería.
"""
import secrets
import time

from fastapi import APIRouter, HTTPException, status
from pwdlib import PasswordHash
from sqlmodel import select

from app.core.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RecoverRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyOtpRequest,
)
from app.services.emailer import send_otp
from app.tables import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])

_pwd = PasswordHash.recommended()

# ---------------------------------------------------------------------------
# OTP en memoria (RF-12). Alcance académico: un solo proceso; sin Redis.
# email -> {"hash", "expires_at", "attempts", "verified"}
# ---------------------------------------------------------------------------
_OTP_TTL_SECONDS = 10 * 60
_OTP_MAX_ATTEMPTS = 5
_otp_store: dict[str, dict] = {}


def _build_user_out(user: AppUser) -> UserOut:
    return UserOut(
        id=user.id,  # type: ignore[arg-type]
        role=user.role.value,
        full_name=user.full_name,
        email=user.email,
        must_change_password=user.must_change_password,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession) -> LoginResponse:
    """RF-11. ``body.email`` acepta correo institucional O código de matrícula."""
    lookup = body.email.strip().lower()
    query = select(AppUser).where(
        (AppUser.email == lookup) | (AppUser.code == lookup)  # type: ignore[operator]
    )
    user = (await db.exec(query)).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario inactivo",
        )
    access = create_access_token(user.id, user.role.value)
    return LoginResponse(access_token=access, user=_build_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    """Datos del usuario autenticado (usa el JWT Bearer)."""
    return _build_user_out(user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(body: ChangePasswordRequest, user: CurrentUser, db: DbSession) -> MessageResponse:
    """RF-11: cambio de clave (obligatorio si must_change_password=True)."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La nueva clave debe ser distinta")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    await db.commit()
    return MessageResponse(message="Contraseña actualizada correctamente")


@router.post("/recover", response_model=MessageResponse)
async def recover(body: RecoverRequest, db: DbSession) -> MessageResponse:
    """RF-12 paso 1: envía un OTP de 6 dígitos al correo institucional."""
    user = (await db.exec(select(AppUser).where(AppUser.email == body.email.lower()))).first()
    # Respuesta uniforme: no revelar si el correo existe o no.
    if user is not None:
        code = f"{secrets.randbelow(1_000_000):06d}"
        _otp_store[body.email.lower()] = {
            "hash": _pwd.hash(code),
            "expires_at": time.monotonic() + _OTP_TTL_SECONDS,
            "attempts": 0,
            "verified": False,
        }
        await send_otp(body.email.lower(), code)
    return MessageResponse(message="Si el correo existe, se envió un código de recuperación")


@router.post("/recover/verify", response_model=MessageResponse)
async def verify_otp(body: VerifyOtpRequest) -> MessageResponse:
    """RF-12 paso 2: valida el código (habilita el reseteo)."""
    entry = _otp_store.get(body.email.lower())
    if entry is None or time.monotonic() > entry["expires_at"]:
        _otp_store.pop(body.email.lower(), None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código expirado o inexistente")
    if entry["attempts"] >= _OTP_MAX_ATTEMPTS:
        _otp_store.pop(body.email.lower(), None)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Demasiados intentos; solicita otro código")
    entry["attempts"] += 1
    if not _pwd.verify(body.code, entry["hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código incorrecto")
    entry["verified"] = True
    return MessageResponse(message="Código validado. Ahora define tu nueva contraseña")


@router.post("/recover/reset", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: DbSession) -> MessageResponse:
    """RF-12 paso 3: establece la nueva contraseña (requiere OTP verificado)."""
    entry = _otp_store.get(body.email.lower())
    if entry is None or not entry.get("verified") or time.monotonic() > entry["expires_at"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valida primero el código enviado al correo")
    user = (await db.exec(select(AppUser).where(AppUser.email == body.email.lower()))).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    await db.commit()
    _otp_store.pop(body.email.lower(), None)
    return MessageResponse(message="Contraseña restablecida. Ya puedes iniciar sesión")
