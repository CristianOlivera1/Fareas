import re
import secrets

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import hash_password
from app.schemas.common import MessageResponse
from app.services import errors
from app.services.audit import audit
from app.services.emailer import send_temporary_credentials
from app.services.formats import validar_dni, validar_dominio_email, validar_whatsapp
from app.services.refresh_tokens import revoke_all_for_user
from app.tables import AppUser, UserRole

_CODE_RE = re.compile(r"^\d{6}$")


def _temp_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))

async def _ensure_unique(db: SQLModelAsyncSession, *, email: str, dni: str | None, code: str | None) -> None:
    clashes: list[str] = []
    if (await db.exec(select(AppUser).where(AppUser.email == email.lower()))).first() is not None:
        clashes.append(f"el correo {email}")
    if dni and (
        await db.exec(select(AppUser).where(AppUser.dni == dni))
    ).first() is not None:
        clashes.append(f"el DNI {dni}")
    if code and (
        await db.exec(select(AppUser).where(AppUser.code == code))
    ).first() is not None:
        clashes.append(f"el código {code}")
    if clashes:
        raise errors.ConflictError("Ya existe una cuenta con " + ", ".join(clashes))

async def create_account(
    db: SQLModelAsyncSession,
    actor: AppUser,
    *,
    role: UserRole,
    full_name: str,
    email: str,
    dni: str | None = None,
    code: str | None = None,
    whatsapp: str | None = None,
    semester: int | None = None,
    ip: str | None = None,
) -> AppUser:
    if role is UserRole.ADMIN:
        raise errors.DomainError("El admin no se crea por este endpoint")
    if role is UserRole.DOCENTE:
        validar_dni(dni)
        code = None
        semester = None
    else:
        validar_dni(dni)
        if not code or not _CODE_RE.match(code):
            raise errors.DomainError("El estudiante requiere un código de matrícula de 6 dígitos")
        if semester is None or not 1 <= semester <= 12:
            raise errors.DomainError("El estudiante requiere un ciclo (semestre) entre 1 y 12")
    whatsapp = validar_whatsapp(whatsapp)

    try:
        email = validar_dominio_email(email)
    except ValueError as exc:
        raise errors.DomainError(str(exc)) from exc
    await _ensure_unique(db, email=email, dni=dni, code=code)

    temp_password = _temp_password()
    user = AppUser(
        role=role,
        dni=dni,
        code=code,
        email=email,
        full_name=full_name.strip(),
        whatsapp=whatsapp,
        password_hash=hash_password(temp_password),
        must_change_password=True,
        semester=semester,
    )
    db.add(user)
    await db.flush()

    await audit(
        db,
        actor,
        action="cuenta_creada",
        entity="app_user",
        entity_id=user.id,
        new_value={"email": email, "role": role.value, "full_name": user.full_name},
        ip_address=ip,
    )
    await db.commit()
    await send_temporary_credentials(email, user.full_name, email, temp_password)
    await db.refresh(user)
    return user

async def resend_credentials(
    db: SQLModelAsyncSession, actor: AppUser, user_id: int, ip: str | None = None
) -> MessageResponse:
    user = await db.get(AppUser, user_id)
    if user is None or user.role is UserRole.ADMIN:
        raise errors.NotFoundError("Cuenta no encontrada")
    temp_password = _temp_password()
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    user.token_version += 1
    db.add(user)
    await revoke_all_for_user(db, user.id, "temporary_password_resent", commit=False)
    await audit(
        db,
        actor,
        action="credenciales_reenviadas",
        entity="app_user",
        entity_id=user.id,
        ip_address=ip,
    )
    await db.commit()
    await send_temporary_credentials(user.email, user.full_name, user.email, temp_password)
    return MessageResponse(message=f"Credenciales enviadas a {user.email}")
