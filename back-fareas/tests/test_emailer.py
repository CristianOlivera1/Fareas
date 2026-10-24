from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from app.services import emailer


@pytest.mark.asyncio
async def test_send_email_embeds_fareas_logo_in_html_header(monkeypatch: pytest.MonkeyPatch):
    sent_messages: list[EmailMessage] = []

    class StubSmtp:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def login(self, *_args):
            return None

        async def send_message(self, message: EmailMessage):
            sent_messages.append(message)
            return {}

    monkeypatch.setattr(emailer, "SMTP", StubSmtp)
    monkeypatch.setattr(
        emailer,
        "get_settings",
        lambda: SimpleNamespace(
            MAIL_ENABLED=True,
            MAIL_FROM_NAME="Fareas",
            MAIL_FROM_ADDRESS="noreply@example.com",
            MAIL_HOST="smtp.example.com",
            MAIL_PORT=587,
            MAIL_USERNAME="noreply@example.com",
            MAIL_PASSWORD="password",
        ),
    )

    html_body = emailer._wrap(preheader="Código de acceso", title="Tu código", content_html="<p>123456</p>")
    sent = await emailer.send_email("user@example.com", "Tu código", "Tu código es 123456", html_body)

    assert sent is True
    message = sent_messages[0]
    html_part = next(part for part in message.walk() if part.get_content_type() == "text/html")
    assert 'src="cid:fareas-logo"' in html_part.get_content()

    image_part = next(part for part in message.walk() if part.get_content_type() == "image/png")
    assert image_part["Content-ID"] == "<fareas-logo>"
    assert image_part.get_content_disposition() == "inline"
    assert image_part.get_payload(decode=True) == emailer._EMAIL_LOGO_PATH.read_bytes()
