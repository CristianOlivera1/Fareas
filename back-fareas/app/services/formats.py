import re

from app.core.config import get_settings

DNI_RE = re.compile(r"^[0-9]{8}$")
WHATSAPP_PE_RE = re.compile(r"^9[0-9]{8}$")


def validar_dni(dni: str | None) -> str | None:
    if dni is None:
        return None
    if not DNI_RE.match(dni):
        raise ValueError("El DNI debe tener exactamente 8 dígitos")
    return dni

def validar_whatsapp(whatsapp: str | None) -> str | None:
    if whatsapp is None or whatsapp == "":
        return None
    if not WHATSAPP_PE_RE.match(whatsapp):
        raise ValueError("El WhatsApp debe ser un celular peruano: 9 dígitos que empiezan en 9")
    return whatsapp

def validar_dominio_email(email: str) -> str:
    dominio = get_settings().ALLOWED_EMAIL_DOMAIN.strip().lower()
    if not dominio:
        return email.lower()
    if not email.lower().endswith(f"@{dominio}"):
        raise ValueError(f"El correo debe ser institucional (@{dominio})")
    return email.lower()
