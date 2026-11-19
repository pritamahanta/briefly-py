import asyncio
import re
from collections.abc import Callable
from typing import Any

import resend

from app.config import Settings
from app.services.formatter import Email

ADDRESS_PATTERN = re.compile(r"[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+")

Send = Callable[[dict[str, Any]], Any]


def validate_email_settings(settings: Settings) -> None:
    settings.require_email()
    for name, address in (("EMAIL_FROM", settings.email_from), ("EMAIL_TO", settings.email_to)):
        if not ADDRESS_PATTERN.fullmatch(address):
            raise ValueError(f"{name} must be a single email address.")


def make_resend_send(api_key: str) -> Send:
    def send(params: dict[str, Any]) -> Any:
        resend.api_key = api_key
        return resend.Emails.send(params)

    return send


async def send_email(email: Email, settings: Settings, send: Send | None = None) -> str:
    validate_email_settings(settings)

    for field in ("subject", "html", "text"):
        if not getattr(email, field).strip():
            raise ValueError(f"Email {field} is required.")
    if "\r" in email.subject or "\n" in email.subject:
        raise ValueError("Email subject must be a single line.")

    send = send or make_resend_send(settings.resend_api_key)
    params = {
        "from": settings.email_from,
        "to": [settings.email_to],
        "subject": email.subject,
        "html": email.html,
        "text": email.text,
    }

    try:
        response = await asyncio.to_thread(send, params)
    except Exception as error:
        raise RuntimeError(f"Resend email request failed: {error}") from error

    email_id = response.get("id") if isinstance(response, dict) else None
    if not isinstance(email_id, str) or not email_id.strip():
        raise RuntimeError("Resend did not return an accepted email ID.")

    return email_id