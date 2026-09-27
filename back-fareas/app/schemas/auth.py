"""DTOs del módulo de autenticación (RF-11, RF-12)."""
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Cuerpo del login (RF-11).

    ``email`` acepta el correo institucional (p. ej. admin@unamba.edu.pe)
    O el código de matrícula del estudiante (p. ej. 221181): ambos resuelven
    a la misma cuenta. El campo se llama ``email`` porque ese es el caso
    principal (docentes/admin siempre entran por correo).
    """

    email: str = Field(
        min_length=3,
        max_length=160,
        description="Correo institucional o código de matrícula (estudiantes).",
    )
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    """Datos del usuario que viajan al frontend (sin hashes ni metadatos)."""
    id: int
    role: str
    full_name: str
    email: str
    must_change_password: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class RecoverRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResetPasswordRequest(VerifyOtpRequest):
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str
