from __future__ import annotations

import logging
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


async def send_email(to: str, subject: str, body: str) -> bool:
    provider = _get_email_provider()
    if not provider:
        logger.warning("no email provider configured, skipping send to %s", to)
        return False

    try:
        return await provider.send(to, subject, body)
    except Exception as e:
        logger.error("email send failed to %s: %s", to, e)
        return False


def _get_email_provider() -> Any | None:
    api_key = _settings.sendgrid_api_key or _settings.resend_api_key
    if not api_key:
        return None

    if _settings.sendgrid_api_key:
        from ...integrations.email.provider import SendGridProvider
        return SendGridProvider(_settings.sendgrid_api_key)

    if _settings.resend_api_key:
        from ...integrations.email.provider import ResendProvider
        return ResendProvider(_settings.resend_api_key)

    return None
