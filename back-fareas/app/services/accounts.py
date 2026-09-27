"""Alta y gestión de cuentas de docentes y estudiantes - RF-02, RF-03, RF-08.

Los routers del catálogo se mantienen delgados: la lógica (validación por
rol, clave temporal, correo, auditoría) vive aquí.
"""
import re
import secrets

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import hash_password
from app.schemas.common import MessageResponse
from app.services import errors
from app.services.audit import audit
from app.services.emailer import send_temporary_credentials
from app.tables import AppUser, UserRole

_DNI_RE = re.compile(r"^\d{8}$")
_CODE_RE = re.compile(r"^\d{6}$")


def _temp_password() -> str:
    """Clave temporal legible: 8 caracteres sin caracteres ambiguos."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def _ensure_unique(db: SQLModelAsyncSession, *, email: str, dni: str | None, code: str | None) -> None:
    clashes: list[str] = []
    if (await db.exec(select(AppUser).where(AppUser.email == email.lower()))).first() is not None:  # type: ignore[arg-type]
        clashes.append(f"el correo {email}")
    if dni and (
        await db.exec(select(AppUser).where(AppUser.dni == dni))  # type: ignore[arg-type]
    ).first() is not None:
        clashes.append(f"el DNI {dni}")
    if code and (
        await db.exec(select(AppUser).where(AppUser.code == code))  # type: ignore[arg-type]
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
    """RF-02/RF-03: crea la cuenta con clave temporal y la envía por correo (RF-08).

    Reglas: docente requiere DNI; estudiante requiere DNI + código de
    matrícula de 6 dígitos + ciclo. ``must_change_password`` queda activo.
    """
    if role is UserRole.ADMIN:
        raise errors.DomainError("El admin no se crea por este endpoint")
    if role is UserRole.DOCENTE:
        if not dni or not _DNI_RE.match(dni):
            raise errors.DomainError("El docente requiere un DNI válido de 8 dígitos")
        code = None
        semester = None
    else:  # estudiante
        if not dni or not _DNI_RE.match(dni):
            raise errors.DomainError("El estudiante requiere un DNI válido de 8 dígitos")
        if not code or not _CODE_RE.match(code):
            raise errors.DomainError("El estudiante requiere un código de matrícula de 6 dígitos")
        if semester is None or not 1 <= semester <= 12:
            raise errors.DomainError("El estudiante requiere un ciclo (semestre) entre 1 y 12")

    email = email.strip().lower()
    if not email.endswith("@unamba.edu.pe"):
        raise errors.DomainError("El correo debe ser institucional (@unamba.edu.pe)")
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
        must_change_password=True,  # RF-11: obliga a cambiarla al primer login
        semester=semester,
    )
    db.add(user)
    await db.flush()  # obtiene user.id sin confirmar todavía

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
    await send_temporary_credentials(email, user.full_name, email, temp_password)  # RF-08
    await db.refresh(user)
    return user


async def resend_credentials(
    db: SQLModelAsyncSession, actor: AppUser, user_id: int, ip: str | None = None
) -> MessageResponse:
    """RF-08: reenvía credenciales con una NUEVA clave temporal."""
    user = await db.get(AppUser, user_id)
    if user is None or user.role is UserRole.ADMIN:
        raise errors.NotFoundError("Cuenta no encontrada")
    temp_password = _temp_password()
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    db.add(user)
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
