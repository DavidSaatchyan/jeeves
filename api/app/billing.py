"""Billing (FR-8) — simplified. No Stripe in MVP.

Plans (from landing page):
  Free: $0/mo, 10 resolved included
  Starter: $19/mo, 500 resolved included
  Pro: $49/mo, 2,000 resolved included
  Enterprise: $149/mo, 25,000 resolved included

Overage: $0.10 per resolved dialog beyond plan limit.
Trial: 14 days or 100 dialogs.
Test widget channel is excluded from all counters at the channel level.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status

from .models import Tenant

PLANS = {
    "free":       {"price_usd": 0,   "resolved_limit": 10},
    "starter":    {"price_usd": 19,  "resolved_limit": 500},
    "pro":        {"price_usd": 49,  "resolved_limit": 2000},
    "enterprise": {"price_usd": 149, "resolved_limit": 25000},
}
TRIAL_DAYS = 14
TRIAL_DIALOGS = 100
OVERAGE_PER_RESOLVED = 0.10


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
    return False


def usage(tenant: Tenant) -> dict:
    plan = "free"
    plan_info = PLANS.get(plan)

    resolved = tenant.resolved_count
    limit = TRIAL_DIALOGS
    overage_charge = 0.0

    if plan_info:
        limit = plan_info["resolved_limit"]
        if resolved > limit:
            overage_charge = (resolved - limit) * OVERAGE_PER_RESOLVED

    trial_ends = None
    trial_days_left = 0
    if tenant.trial_ends:
        trial_ends = tenant.trial_ends.isoformat()
        now = datetime.utcnow()
        trial_days_left = max(0, (tenant.trial_ends - now).days)

    base_charge = plan_info["price_usd"] if plan_info else 0.0

    return {
        "plan": plan,
        "billing_enabled": tenant.is_active,
        "resolved": resolved,
        "dialogs_limit": limit,
        "trial_ends": trial_ends,
        "trial_days_left": trial_days_left,
        "overage_charge_usd": round(overage_charge, 2),
        "estimated_charge_usd": round(base_charge + overage_charge, 2),
    }
