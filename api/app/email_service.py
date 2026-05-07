"""Email delivery service — sends transactional emails via SMTP."""
from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Optional

from .config import get_settings


def _get_smtp_connection() -> Optional[smtplib.SMTP]:
    settings = get_settings()
    host = getattr(settings, "smtp_host", "")
    if not host:
        return None
    port = int(getattr(settings, "smtp_port", "587"))
    user = getattr(settings, "smtp_user", "")
    password = getattr(settings, "smtp_password", "")
    use_tls = getattr(settings, "smtp_use_tls", "true").lower() != "false"

    try:
        ctx = ssl.create_default_context() if use_tls else None
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
        if user and password:
            server.login(user, password)
        return server
    except Exception as e:
        print(f"[email] SMTP connection failed: {e}", flush=True)
        return None


def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email. Returns True on success, False otherwise."""
    settings = get_settings()
    from_addr = getattr(settings, "smtp_from", "noreply@jeeves.ai")

    server = _get_smtp_connection()
    if not server:
        print(f"[email-stub] Would send to {to}: {subject}", flush=True)
        return False

    try:
        msg = MIMEText(html_body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to

        server.sendmail(from_addr, [to], msg.as_string())
        server.quit()
        print(f"[email] Sent to {to}: {subject}", flush=True)
        return True
    except Exception as e:
        print(f"[email] Send failed: {e}", flush=True)
        try:
            server.quit()
        except Exception:
            pass
        return False


def send_verification_email(to: str, verify_link: str, tenant_name: str) -> bool:
    """Send email verification link."""
    subject = "Verify your Jeeves account"
    html = f"""\
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2 style="color:#6366f1;">Welcome to Jeeves</h2>
      <p>Hi {tenant_name},</p>
      <p>Please verify your email address by clicking the button below:</p>
      <p style="margin:24px 0;">
        <a href="{verify_link}"
           style="background:#6366f1;color:#fff;padding:12px 24px;
                  border-radius:8px;text-decoration:none;font-weight:600;">
          Verify Email
        </a>
      </p>
      <p style="color:#6b7280;font-size:13px;">
        Or copy this link:<br/>{verify_link}
      </p>
      <p style="color:#6b7280;font-size:12px;margin-top:24px;">
        If you didn't create this account, just ignore this email.
      </p>
    </div>
    """
    return send_email(to, subject, html)
