"""Validadores de formato Perú (R15).

Pydantic field_validators compartidos: DNI (8 dígitos), WhatsApp peruano
(9 dígitos que empiezan en 9) y dominio de correo institucional (R15:
``ALLOWED_EMAIL_DOMAIN`` en .env; vacío = sin validar; el admin está exento).
"""
import re

from app.core.config import get_settings

DNI_RE = re.compile(r"^[0-9]{8}$")
WHATSAPP_PE_RE = re.compile(r"^9[0-9]{8}$")


def validar_dni(dni: str | None) -> str | None:
    """8 dígitos exactos. None pasa (el campo es opcional en el modelo)."""
    if dni is None:
        return None
    if not DNI_RE.match(dni):
        raise ValueError("El DNI debe tener exactamente 8 dígitos")
    return dni


def validar_whatsapp(whatsapp: str | None) -> str | None:
    """Celular peruano: 9 dígitos que empiezan en 9 (ej. 987654321)."""
    if whatsapp is None or whatsapp == "":
        return None
    if not WHATSAPP_PE_RE.match(whatsapp):
        raise ValueError("El WhatsApp debe ser un celular peruano: 9 dígitos que empiezan en 9")
    return whatsapp


def validar_dominio_email(email: str) -> str:
    """R15: correo institucional @<ALLOWED_EMAIL_DOMAIN>.

    Vacío en .env = sin validar (entorno de pruebas). El admin se valida
    aparte (exento): este validador es para docentes y estudiantes.
    """
    dominio = get_settings().ALLOWED_EMAIL_DOMAIN.strip().lower()
    if not dominio:
        return email.lower()
    if not email.lower().endswith(f"@{dominio}"):
        raise ValueError(f"El correo debe ser institucional (@{dominio})")
    return email.lower()
