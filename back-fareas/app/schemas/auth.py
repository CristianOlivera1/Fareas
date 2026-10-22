from pydantic import BaseModel, EmailStr, Field


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

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

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

class RecoverRequest(BaseModel):
    email: EmailStr

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

class ResetPasswordRequest(VerifyOtpRequest):
    new_password: str = Field(min_length=8, max_length=128)

class MessageResponse(BaseModel):
    message: str
