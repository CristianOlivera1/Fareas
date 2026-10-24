import html
import logging
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from aiosmtplib import SMTP

from app.core.config import get_settings

logger = logging.getLogger("fareas.emailer")
_EMAIL_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo-full.png"
_EMAIL_LOGO_CID = "fareas-logo"

_PRIMARY = "#155DFC"
_CANVAS = "#F6F9FF"
_TEXT = "#111827"
_MUTED = "#6B7280"
_BORDER = "#E5E7EB"
_FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

_FROM_FALLBACK = "no-reply@unamba.edu.pe"


def _wrap(*, preheader: str, title: str, content_html: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<body style="margin:0;padding:0;background-color:{_CANVAS};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_CANVAS};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background-color:#FFFFFF;border:1px solid {_BORDER};border-radius:12px;">
<tr><td style="padding:28px 28px 0;">
<img src="cid:{_EMAIL_LOGO_CID}" alt="Fareas" width="200" height="45" style="display:block;width:200px;max-width:100%;height:auto;border:0;">
<p style="margin:4px 0 0;font-family:{_FONT};font-size:12px;color:{_MUTED};">Facultad de Informática - UNAMBA</p>
</td></tr>
<tr><td style="padding:20px 28px 0;">
<h1 style="margin:0;font-family:{_FONT};font-size:18px;font-weight:700;color:{_TEXT};">{title}</h1>
</td></tr>
<tr><td style="padding:12px 28px 0;font-family:{_FONT};font-size:14px;line-height:1.6;color:#374151;">
{content_html}
</td></tr>
<tr><td style="padding:20px 28px 28px;">
<p style="margin:0;padding-top:16px;border-top:1px solid {_BORDER};font-family:{_FONT};font-size:12px;line-height:1.6;color:{_MUTED};">
Si no solicitaste este mensaje, ignóralo. Es una notificación automática, no respondas a este correo.
</p>
</td></tr>
</table>
<p style="margin:16px 0 0;font-family:{_FONT};font-size:11px;color:#9CA3AF;">© Fareas · Facultad de Informática UNAMBA</p>
</td></tr>
</table>
</body>
</html>"""


def _code_box(value: str) -> str:
    return (
        f'<p style="margin:16px 0;padding:14px;background-color:{_CANVAS};'
        f"border:1px solid {_BORDER};border-radius:8px;text-align:center;"
        'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:28px;'
        f'font-weight:700;letter-spacing:8px;color:{_TEXT};">{value}</p>'
    )

def _field_row(label: str, value: str) -> str:
    return (
        f'<p style="margin:12px 0 0;font-family:{_FONT};font-size:12px;color:{_MUTED};">{label}</p>'
        f'<p style="margin:4px 0 0;padding:10px 12px;background-color:{_CANVAS};'
        f"border:1px solid {_BORDER};border-radius:8px;"
        'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px;'
        f'font-weight:700;color:{_TEXT};">{value}</p>'
    )

async def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> bool:
    settings = get_settings()
    if not settings.MAIL_ENABLED:
        logger.info("[MAIL deshabilitado] Para=%s | %s", to, subject)
        return False

    message = EmailMessage()
    message["From"] = formataddr((settings.MAIL_FROM_NAME, settings.MAIL_FROM_ADDRESS))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
        html_part = message.get_payload()[-1]
        html_part.add_related(
            _EMAIL_LOGO_PATH.read_bytes(),
            maintype="image",
            subtype="png",
            cid=f"<{_EMAIL_LOGO_CID}>",
            disposition="inline",
            filename="fareas-logo.png",
        )

    try:
        client = SMTP(
            hostname=settings.MAIL_HOST,
            port=settings.MAIL_PORT,
            start_tls=True,
        )
        async with client:
            await client.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            await client.send_message(message)
        return True
    except Exception:
        logger.exception("Fallo el envío de correo a %s", to)
        return False

async def send_temporary_credentials(to: str, full_name: str, username: str, temp_password: str) -> bool:
    subject = "Fareas UNAMBA - Tu acceso al sistema"
    safe_name = html.escape(full_name)
    safe_user = html.escape(username)
    safe_pass = html.escape(temp_password)

    plain = (
        f"Hola {full_name},\n\n"
        "Se creó tu cuenta en el sistema de control de asistencia de la Facultad de Informática (UNAMBA).\n\n"
        f"Usuario: {username}\n"
        f"Clave temporal: {temp_password}\n\n"
        "Al ingresar por primera vez el sistema te pedirá crear una contraseña propia (RF-11).\n\n"
        "Si no solicitaste esta cuenta, ignora este mensaje.\n\n"
        "- Sistema Fareas, Facultad de Informática UNAMBA"
    )
    content_html = (
        f"<p style=\"margin:0;\">Hola <strong>{safe_name}</strong>,</p>"
        "<p style=\"margin:12px 0 0;\">Se creó tu cuenta en el sistema de control de "
        "asistencia de la Facultad de Informática (UNAMBA).</p>"
        f"{_field_row('Usuario', safe_user)}"
        f"{_field_row('Clave temporal', safe_pass)}"
        "<p style=\"margin:16px 0 0;\">Al ingresar por primera vez el sistema te pedirá "
        "crear una contraseña propia.</p>"
    )
    html_body = _wrap(
        preheader="Tu acceso al sistema Fareas",
        title="Tu acceso al sistema",
        content_html=content_html,
    )
    return await send_email(to, subject, plain, html_body)

async def send_otp(to: str, code: str, purpose: str = "recover") -> bool:
    safe_code = html.escape(code)
    if purpose == "change_password":
        subject = "Fareas UNAMBA - Código para cambiar tu contraseña"
        plain = (
            "Tu código para confirmar el cambio de contraseña es:\n\n"
            f"    {code}\n\n"
            "Caduca en 10 minutos. Si no solicitaste el cambio, ignora este mensaje "
            "y tu contraseña actual seguirá vigente.\n\n"
            "- Sistema Fareas, Facultad de Informática UNAMBA"
        )
        content_html = (
            "<p style=\"margin:0;\">Usá este código para confirmar el cambio de "
            "contraseña de tu cuenta:</p>"
            f"{_code_box(safe_code)}"
            "<p style=\"margin:0;\">Caduca en <strong>10 minutos</strong>. Si no "
            "solicitaste el cambio, ignora este mensaje.</p>"
        )
        title = "Código para cambiar tu contraseña"
    else:
        subject = "Fareas UNAMBA - Código de recuperación"
        plain = (
            "Tu código de recuperación de contraseña es:\n\n"
            f"    {code}\n\n"
            "Caduca en 10 minutos. Si no solicitaste el código, ignora este mensaje.\n\n"
            "- Sistema Fareas, Facultad de Informática UNAMBA"
        )
        content_html = (
            "<p style=\"margin:0;\">Usá este código para restaurar tu contraseña:</p>"
            f"{_code_box(safe_code)}"
            "<p style=\"margin:0;\">Caduca en <strong>10 minutos</strong>.</p>"
        )
        title = "Código de recuperación"

    html_body = _wrap(
        preheader=f"Tu código es {safe_code}",
        title=title,
        content_html=content_html,
    )
    return await send_email(to, subject, plain, html_body)

async def send_notification_email(
    to: str, full_name: str, title: str, message: str, link: str | None = None
) -> bool:
    subject = f"Fareas UNAMBA - {title}"
    safe_name = html.escape(full_name)
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    base = get_settings().FRONTEND_BASE_URL.rstrip("/")
    url = None
    if link:
        url = link if link.startswith(("http://", "https://")) else f"{base}{link}"
    plain = (
        f"Hola {full_name},\n\n"
        f"{message}\n\n"
        + (f"Abre el sistema: {url}\n\n" if url else "")
        + "- Sistema Fareas, Facultad de Informática UNAMBA"
    )
    cta = (
        f'<p style="margin:20px 0 0;"><a href="{html.escape(url)}" '
        'style="display:inline-block;padding:11px 18px;background-color:#155DFC;'
        'color:#FFFFFF;text-decoration:none;border-radius:8px;font-weight:600;">'
        "Ver en Fareas</a></p>"
        if url
        else ""
    )
    content_html = (
        f'<p style="margin:0;">Hola <strong>{safe_name}</strong>,</p>'
        f'<p style="margin:12px 0 0;white-space:pre-line;">{safe_message}</p>'
        f"{cta}"
    )
    html_body = _wrap(
        preheader=safe_title,
        title=safe_title,
        content_html=content_html,
    )
    return await send_email(to, subject, plain, html_body)

async def send_password_changed_notice(to: str, full_name: str) -> bool:
    subject = "Fareas UNAMBA - Tu contraseña fue actualizada"
    safe_name = html.escape(full_name)
    plain = (
        f"Hola {full_name},\n\n"
        "La contraseña de tu cuenta Fareas se actualizó correctamente.\n\n"
        "Si no fuiste tú, restablece tu contraseña de inmediato con la opción "
        "'Olvidé mi contraseña' e informa al administrador.\n\n"
        "- Sistema Fareas, Facultad de Informática UNAMBA"
    )
    content_html = (
        f"<p style=\"margin:0;\">Hola <strong>{safe_name}</strong>,</p>"
        "<p style=\"margin:12px 0 0;\">La contraseña de tu cuenta Fareas se "
        "actualizó correctamente.</p>"
        "<p style=\"margin:16px 0 0;\">Si no fuiste tú, restablece tu contraseña "
        "de inmediato con la opción <strong>Olvidé mi contraseña</strong> e "
        "informa al administrador.</p>"
    )
    html_body = _wrap(
        preheader="Tu contraseña fue actualizada",
        title="Contraseña actualizada",
        content_html=content_html,
    )
    return await send_email(to, subject, plain, html_body)
