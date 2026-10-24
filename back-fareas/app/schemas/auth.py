import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.formats import validar_dominio_email

_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _institutional_email(value: str) -> str:
    try:
        return validar_dominio_email(value)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _strong_password(value: str) -> str:
    if not _PASSWORD_PATTERN.fullmatch(value):
        raise ValueError("La contraseña debe tener al menos 8 caracteres e incluir letras y números")
    return value


class InstitutionalEmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _institutional_email(value)


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=160,
        description="Correo institucional o código de matrícula (estudiantes).",
    )
    password: str = Field(min_length=6, max_length=128)

class UserOut(BaseModel):
    id: int
    role: str
    full_name: str
    email: str
    must_change_password: bool
    avatar_url: str | None = None

class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int

class LoginResponse(TokenPairResponse):
    user: UserOut

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _strong_password(value)

class ChangePasswordOtpRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)

class ChangePasswordOtpResponse(BaseModel):
    message: str
    email: str
    expires_in: int
    resend_in: int

class VerifyChangePasswordOtpRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

class ChangePasswordResponse(BaseModel):
    message: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_expires_in: int | None = None

class RecoverRequest(InstitutionalEmailRequest):
    pass

class VerifyOtpRequest(InstitutionalEmailRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

class ResetPasswordRequest(VerifyOtpRequest):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _strong_password(value)

class MessageResponse(BaseModel):
    message: str

class RecoverResponse(MessageResponse):
    resend_in: int
