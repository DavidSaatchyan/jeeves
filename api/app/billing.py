"""Billing (FR-8) — simplified. No Stripe in MVP.

Trial = 14 days OR 100 dialogs, whichever comes first. Past that: API blocked.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status

from .config import get_yaml_config
from .models import Tenant

_cfg = get_yaml_config().get("billing", {})
TRIAL_DIALOGS = int(_cfg.get("trial_dialogs", 100))
PRICE = float(_cfg.get("price_per_resolution_usd", 0.10))


def enforce(tenant: Tenant) -> None:
    """Raise 402 if tenant exceeded trial and isn't active (paid)."""
    over_time = tenant.trial_ends and datetime.utcnow() > tenant.trial_ends
    over_volume = tenant.dialogs_used >= TRIAL_DIALOGS
    if (over_time or over_volume) and not _has_payment(tenant):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Trial exhausted. Please add a payment method to continue.",
        )


def _has_payment(tenant: Tenant) -> bool:
    # DEFAULT: no real payment integration; only operator-flip of is_active extends usage.
    # tenant.is_active means "paid plan enabled" once trial ended.
    return False  # MVP: always requires card after trial


def usage(tenant: Tenant) -> dict:
    return {
        "dialogs_used": tenant.dialogs_used,
        "dialogs_limit": TRIAL_DIALOGS,
        "resolved": tenant.resolved_count,
        "resolution_rate": round(tenant.resolved_count / tenant.dialogs_used, 3) if tenant.dialogs_used else 0,
        "trial_ends": tenant.trial_ends.isoformat() if tenant.trial_ends else None,
        "estimated_charge_usd": round(tenant.resolved_count * PRICE, 2),
    }
