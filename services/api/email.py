"""Server-side SMTP delivery for account lifecycle emails."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from .config import settings


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be handed to the configured SMTP server."""


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send a plain-text message without exposing SMTP details to callers."""

    if not settings.email_delivery_configured:
        raise EmailDeliveryError("Email delivery is not configured")

    try:
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = recipient
        # A workspace name may appear in a subject; never accept header lines
        # from user-controlled text.
        message["Subject"] = " ".join(subject.splitlines()).strip()
        message.set_content(body)

        if settings.smtp_ssl:
            client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )

        with client:
            if settings.smtp_starttls:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException, ssl.SSLError, ValueError):
        # SMTP exceptions may include server diagnostics. Do not return or log
        # those details because they can contain addresses or configuration.
        raise EmailDeliveryError("The SMTP server did not accept the message") from None
