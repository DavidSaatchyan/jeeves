from __future__ import annotations

import logging
from typing import Any

import httpx

from ...crypto import ConnectorError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.rechargeapps.com"
_API_VERSION = "2021-01"


def _headers(credentials: dict) -> dict[str, str]:
    return {
        "X-Recharge-Access-Token": credentials.get("api_key", ""),
        "Content-Type": "application/json",
        "Accept": f"application/json; version={_API_VERSION}",
    }


async def get_subscription(credentials: dict, subscription_id: str) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge get_subscription %s: %s", subscription_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="get_subscription", message=str(e))


async def pause_subscription(credentials: dict, subscription_id: str, pause_note: str = "") -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}"
    payload = {"subscription": {"status": "paused", "pause_note": pause_note}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url, json=payload, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge pause_subscription %s: %s", subscription_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="pause_subscription", message=str(e))


async def skip_next_shipment(credentials: dict, subscription_id: str) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/skip"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=_headers(credentials))
        if r.is_success:
            return r.json()
        logger.warning("recharge skip_next_shipment %s: %s", subscription_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="skip_next_shipment", message=str(e))


async def delay_renewal(credentials: dict, subscription_id: str, delay_days: int = 7) -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/set_next_charge_date"
    from datetime import datetime, timedelta
    new_date = (datetime.utcnow() + timedelta(days=delay_days)).strftime("%Y-%m-%d")
    payload = {"subscription": {"next_charge_scheduled_at": new_date}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url, json=payload, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge delay_renewal %s: %s", subscription_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="delay_renewal", message=str(e))


async def cancel_subscription(credentials: dict, subscription_id: str, reason: str = "") -> dict[str, Any] | None:
    url = f"{_BASE_URL}/subscriptions/{subscription_id}/cancel"
    payload = {"subscription": {"cancellation_reason": reason or "customer_request"}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("subscription")
        logger.warning("recharge cancel_subscription %s: %s", subscription_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="cancel_subscription", message=str(e))


async def get_charges(credentials: dict, subscription_id: str, limit: int = 5) -> list[dict[str, Any]]:
    url = f"{_BASE_URL}/charges"
    params = {"subscription_id": subscription_id, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("charges", [])
        return []
    except httpx.RequestError as e:
        raise ConnectorError(provider="recharge", operation="get_charges", message=str(e))
