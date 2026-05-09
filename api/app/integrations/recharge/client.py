from __future__ import annotations

import logging
from typing import Any

import httpx

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_BASE_URL = "https://api.rechargeapps.com"
_API_VERSION = "2021-01"


def _headers() -> dict[str, str]:
    return {
        "X-Recharge-Access-Token": _settings.recharge_api_key,
        "Content-Type": "application/json",
        "Accept": f"application/json; version={_API_VERSION}",
    }


async def get_subscription(subscription_id: str) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers())
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge get_subscription %s: %s", subscription_id, r.status_code)
        return None
    except Exception as e:
        logger.error("recharge get_subscription failed: %s", e)
        return None


async def pause_subscription(subscription_id: str, pause_note: str = "") -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}"
    payload = {"subscription": {"status": "paused", "pause_note": pause_note}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url, json=payload, headers=_headers())
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge pause_subscription %s: %s", subscription_id, r.status_code)
        return None
    except Exception as e:
        logger.error("recharge pause_subscription failed: %s", e)
        return None


async def skip_next_shipment(subscription_id: str) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/skip"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=_headers())
        if r.is_success:
            return r.json()
        logger.warning("recharge skip_next_shipment %s: %s", subscription_id, r.status_code)
        return None
    except Exception as e:
        logger.error("recharge skip_next_shipment failed: %s", e)
        return None


async def delay_renewal(subscription_id: str, delay_days: int = 7) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/delay"
    payload = {"delay_days": delay_days}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=_headers())
        if r.is_success:
            return r.json()
        logger.warning("recharge delay_renewal %s: %s", subscription_id, r.status_code)
        return None
    except Exception as e:
        logger.error("recharge delay_renewal failed: %s", e)
        return None


async def cancel_subscription(subscription_id: str, cancellation_reason: str = "") -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/cancel"
    payload = {"cancellation_reason": cancellation_reason, "send_cancellation_notification": False}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=_headers())
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge cancel_subscription %s: %s", subscription_id, r.status_code)
        return None
    except Exception as e:
        logger.error("recharge cancel_subscription failed: %s", e)
        return None


async def get_charges(subscription_id: str, limit: int = 10) -> list[dict[str, Any]]:
    url = f"{_BASE_URL}/charges"
    params = {"subscription_id": subscription_id, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=_headers())
        if r.is_success:
            return r.json().get("charges", [])
        return []
    except Exception as e:
        logger.error("recharge get_charges failed: %s", e)
        return []
