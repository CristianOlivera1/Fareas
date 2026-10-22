"""OTP de 6 dígitos con propósito explícito (RF-12 + cambio de contraseña).

Decisiones de diseño (alcance académico, un solo proceso):

- El código **nunca** se guarda en claro: se almacena su hash argon2id con el
  mismo ``pwdlib`` que las contraseñas.
- La clave del store es ``(user_id, purpose)``. Así un código de recuperación
  no puede usarse para cambiar la contraseña (ni al revés) y dos usuarios con
  el mismo correo (imposible por UNIQUE) no se pisan.
- ``issue()`` aplica un cooldown de 60 s para evitar bombardeo de correos.
- ``verify()`` consume un intento por código incorrecto y marca ``verified``.
- ``consume()`` es de un solo uso: borra la entrada y exige que el código haya
  sido verificado antes. El endpoint que cambia la contraseña llama a
  ``consume()`` dentro de la misma petición, sin ventanas de reutilización.
- Todo vive en memoria (dict) y se pierde al reiniciar el proceso. Es el mismo
  trade-off que ya usaba el proyecto para recuperación; Redis queda fuera del
  alcance (§7 del PLAN).
"""
from __future__ import annotations

import math
import secrets
import time
from dataclasses import dataclass
from enum import StrEnum

from app.core.security import hash_password, verify_password

OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class OtpPurpose(StrEnum):
    """Propósitos válidos. Se guardan como texto para no tocar la BD."""

    RECOVER = "recover"
    CHANGE_PASSWORD = "change_password"


class OtpError(Exception):
    """Base de los errores de negocio del OTP."""


class OtpCooldownError(OtpError):
    """Se pidió un código antes de que terminara el cooldown."""

    def __init__(self, seconds: int) -> None:
        self.seconds = max(1, seconds)
        super().__init__(f"Espera {self.seconds} segundos antes de solicitar otro código")


class OtpExpiredError(OtpError):
    """No existe o ya venció."""


class OtpAttemptsExceededError(OtpError):
    """Se agotaron los intentos; el código se invalida."""


class OtpInvalidError(OtpError):
    """El código no coincide."""


class OtpNotVerifiedError(OtpError):
    """Se intentó consumir un código que aún no fue verificado."""


@dataclass
class _OtpEntry:
    code_hash: str
    expires_at: float
    sent_at: float
    attempts: int = 0
    verified: bool = False


# Clave: (user_id, purpose). Público para que los tests puedan inspeccionarlo.
_store: dict[tuple[int, str], _OtpEntry] = {}


def clear() -> None:
    """Limpia el store (tests y reinicios controlados)."""
    _store.clear()


def issue(user_id: int, purpose: str | OtpPurpose) -> str:
    """Genera y guarda un OTP. Devuelve el código en claro SOLO para enviarlo."""
    now = time.monotonic()
    key = (user_id, str(purpose))
    previous = _store.get(key)
    if previous is not None and previous.expires_at > now:
        elapsed = now - previous.sent_at
        if elapsed < OTP_RESEND_SECONDS:
            raise OtpCooldownError(math.ceil(OTP_RESEND_SECONDS - elapsed))

    code = f"{secrets.randbelow(1_000_000):06d}"
    _store[key] = _OtpEntry(
        code_hash=hash_password(code),
        expires_at=now + OTP_TTL_SECONDS,
        sent_at=now,
    )
    return code


def verify(user_id: int, purpose: str | OtpPurpose, code: str) -> None:
    """Valida el código y lo deja listo para ``consume()``."""
    key = (user_id, str(purpose))
    entry = _store.get(key)
    now = time.monotonic()
    if entry is None or now > entry.expires_at:
        _store.pop(key, None)
        raise OtpExpiredError("Código expirado o inexistente")

    if entry.attempts >= OTP_MAX_ATTEMPTS:
        _store.pop(key, None)
        raise OtpAttemptsExceededError("Demasiados intentos; solicita otro código")

    entry.attempts += 1
    if not verify_password(code, entry.code_hash):
        raise OtpInvalidError("Código incorrecto")
    entry.verified = True


def consume(user_id: int, purpose: str | OtpPurpose) -> None:
    """Consume el OTP verificado (un solo uso)."""
    key = (user_id, str(purpose))
    entry = _store.get(key)
    now = time.monotonic()
    if entry is None or now > entry.expires_at:
        _store.pop(key, None)
        raise OtpExpiredError("El código expiró; solicita uno nuevo")
    if not entry.verified:
        raise OtpNotVerifiedError("Verifica el código antes de continuar")
    _store.pop(key, None)


def mask_email(email: str) -> str:
    """Enmascara la parte local: ``juan.perez@…`` → ``ju********@…``.

    El dominio se conserva para que el usuario reconozca su correo
    institucional sin exponer la dirección completa en pantalla.
    """
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:2] + "*" * (len(local) - 2)
    return f"{masked}@{domain}"
