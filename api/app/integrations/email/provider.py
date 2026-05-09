from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> bool:
        ...


class SendGridProvider(EmailProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def send(self, to: str, subject: str, body: str) -> bool:
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, Content

            sg = sendgrid.SendGridAPIClient(api_key=self.api_key)
            message = Mail(
                from_email=Email("noreply@jeeves.dev"),
                to_emails=to,
                subject=subject,
                plain_text_content=Content("text/plain", body),
            )
            response = sg.send(message)
            if response.status_code in (200, 201, 202):
                logger.info("sendgrid email sent to %s: %s", to, response.status_code)
                return True
            logger.warning("sendgrid returned %s for %s", response.status_code, to)
            return False
        except ImportError:
            logger.error("sendgrid library not installed")
            return False
        except Exception as e:
            logger.error("sendgrid send failed: %s", e)
            return False


class ResendProvider(EmailProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def send(self, to: str, subject: str, body: str) -> bool:
        try:
            import resend

            resend.api_key = self.api_key
            params = {
                "from": "noreply@jeeves.dev",
                "to": to,
                "subject": subject,
                "text": body,
            }
            response = resend.Emails.send(params)
            if response and response.get("id"):
                logger.info("resend email sent to %s: %s", to, response["id"])
                return True
            return False
        except ImportError:
            logger.error("resend library not installed")
            return False
        except Exception as e:
            logger.error("resend send failed: %s", e)
            return False
