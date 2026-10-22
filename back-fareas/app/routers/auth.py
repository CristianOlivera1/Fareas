import logging
import time

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from app.core.deps import CurrentUserPending, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import (
    ChangePasswordOtpRequest,
    ChangePasswordOtpResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RecoverRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyChangePasswordOtpRequest,
    VerifyOtpRequest,
)
from app.services import otp
from app.services.audit import audit
from app.services.emailer import send_otp, send_password_changed_notice
from app.tables import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("fareas.auth")

_OTP_TTL_SECONDS = otp.OTP_TTL_SECONDS
_OTP_MAX_ATTEMPTS = otp.OTP_MAX_ATTEMPTS
_otp_store = otp._store


_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60.0
_login_attempts: dict[str, dict] = {}


def _login_rate_ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"

def _login_rate_ok(request: Request) -> bool:
    ip = _login_rate_ip(request)
    entry = _login_attempts.get(ip)
    if entry is None:
        return True
    if time.monotonic() - entry["first"] >= _LOGIN_WINDOW_SECONDS:
        _login_attempts.pop(ip, None)
        return True
    return entry["count"] < _LOGIN_MAX_ATTEMPTS

def _login_rate_register_failure(request: Request) -> None:
    ip = _login_rate_ip(request)
    entry = _login_attempts.get(ip)
    if entry is None or time.monotonic() - entry["first"] >= _LOGIN_WINDOW_SECONDS:
        _login_attempts[ip] = {"count": 1, "first": time.monotonic()}
    else:
        entry["count"] += 1

def _login_rate_reset(request: Request) -> None:
    _login_attempts.pop(_login_rate_ip(request), None)

def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None

async def _notify_password_changed(user: AppUser) -> None:
    try:
        await send_password_changed_notice(user.email, user.full_name)
    except Exception:
        logger.exception("No se pudo enviar el aviso de clave actualizada a %s", user.email)

def _otp_http_error(exc: otp.OtpError) -> HTTPException:
    if isinstance(exc, otp.OtpCooldownError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Espera {exc.seconds} segundos antes de solicitar otro código",
        )
    if isinstance(exc, otp.OtpAttemptsExceededError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Solicita un código nuevo.",
        )
    if isinstance(exc, otp.OtpInvalidError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código incorrecto")
    if isinstance(exc, otp.OtpNotVerifiedError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verifica primero el código enviado a tu correo",
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="El código expiró o no existe. Solicita uno nuevo.",
    )

def _build_user_out(user: AppUser) -> UserOut:
    return UserOut(
        id=user.id,
        role=user.role.value,
        full_name=user.full_name,
        email=user.email,
        must_change_password=user.must_change_password,
    )

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    if not _login_rate_ok(request):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos; espera un minuto antes de volver a intentarlo",
        )
    lookup = body.email.strip().lower()
    query = select(AppUser).where(
        (AppUser.email == lookup) | (AppUser.code == lookup)
    )
    user = (await db.exec(query)).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        _login_rate_register_failure(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas o usuario inactivo",
        )
    _login_rate_reset(request)
    access = create_access_token(user.id, user.role.value, user.token_version)
    return LoginResponse(access_token=access, user=_build_user_out(user))

@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserPending) -> UserOut:
    return _build_user_out(user)

@router.post("/change-password/otp", response_model=ChangePasswordOtpResponse)
async def request_change_password_otp(
    body: ChangePasswordOtpRequest,
    request: Request,
    user: CurrentUserPending,
    db: DbSession,
) -> ChangePasswordOtpResponse:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tu contraseña es temporal; cámbiala directamente sin código",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta",
        )

    try:
        code = otp.issue(user.id, otp.OtpPurpose.CHANGE_PASSWORD)
    except otp.OtpError as exc:
        raise _otp_http_error(exc) from exc

    await send_otp(user.email, code, purpose=otp.OtpPurpose.CHANGE_PASSWORD)
    await audit(
        db,
        user,
        action="password_change_otp",
        entity="app_user",
        entity_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()

    return ChangePasswordOtpResponse(
        message="Código enviado al correo institucional",
        email=otp.mask_email(user.email),
        expires_in=otp.OTP_TTL_SECONDS,
        resend_in=otp.OTP_RESEND_SECONDS,
    )

@router.post("/change-password/otp/verify", response_model=MessageResponse)
async def verify_change_password_otp(
    body: VerifyChangePasswordOtpRequest,
    user: CurrentUserPending,
) -> MessageResponse:
    try:
        otp.verify(user.id, otp.OtpPurpose.CHANGE_PASSWORD, body.code)
    except otp.OtpError as exc:
        raise _otp_http_error(exc) from exc
    return MessageResponse(message="Código validado. Define tu nueva contraseña")

@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUserPending,
    db: DbSession,
) -> ChangePasswordResponse:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva clave debe ser distinta",
        )

    used_otp = not user.must_change_password
    if used_otp:
        try:
            otp.consume(user.id, otp.OtpPurpose.CHANGE_PASSWORD)
        except otp.OtpError as exc:
            raise _otp_http_error(exc) from exc

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1
    db.add(user)
    await audit(
        db,
        user,
        action="password_changed",
        entity="app_user",
        entity_id=user.id,
        new_value={"method": "otp" if used_otp else "temporary_password"},
        ip_address=_client_ip(request),
    )
    await db.commit()

    access = create_access_token(user.id, user.role.value, user.token_version)
    await _notify_password_changed(user)
    return ChangePasswordResponse(
        message="Contraseña actualizada correctamente",
        access_token=access,
    )

@router.post("/recover", response_model=MessageResponse)
async def recover(body: RecoverRequest, db: DbSession) -> MessageResponse:
    user = (await db.exec(select(AppUser).where(AppUser.email == body.email.lower()))).first()
    if user is not None:
        try:
            code = otp.issue(user.id, otp.OtpPurpose.RECOVER)
        except otp.OtpCooldownError:
            pass
        else:
            await send_otp(user.email, code, purpose=otp.OtpPurpose.RECOVER)
    return MessageResponse(message="Si el correo existe, se envió un código de recuperación")

@router.post("/recover/verify", response_model=MessageResponse)
async def verify_otp(body: VerifyOtpRequest, db: DbSession) -> MessageResponse:
    user = (await db.exec(select(AppUser).where(AppUser.email == body.email.lower()))).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código expirado o inexistente",
        )
    try:
        otp.verify(user.id, otp.OtpPurpose.RECOVER, body.code)
    except otp.OtpError as exc:
        raise _otp_http_error(exc) from exc
    return MessageResponse(message="Código validado. Ahora define tu nueva contraseña")

@router.post("/recover/reset", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: DbSession) -> MessageResponse:
    user = (await db.exec(select(AppUser).where(AppUser.email == body.email.lower()))).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    try:
        otp.consume(user.id, otp.OtpPurpose.RECOVER)
    except otp.OtpError as exc:
        raise _otp_http_error(exc) from exc

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1
    db.add(user)
    await audit(
        db,
        user,
        action="password_reset",
        entity="app_user",
        entity_id=user.id,
        new_value={"method": "recover_otp"},
    )
    await db.commit()
    await _notify_password_changed(user)
    return MessageResponse(message="Contraseña restablecida. Ya puedes iniciar sesión")
