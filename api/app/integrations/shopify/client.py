from __future__ import annotations

import logging
from typing import Any

import httpx

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_API_VERSION = "2024-01"


def _base_url() -> str:
    shop = _settings.shopify_shop
    return f"https://{shop}/admin/api/{_API_VERSION}/"


def _headers() -> dict[str, str]:
    return {"X-Shopify-Access-Token": _settings.shopify_access_token}


async def get_customer(customer_id: str) -> dict[str, Any] | None:
    url = _base_url() + f"customers/{customer_id}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers())
        if r.is_success:
            return r.json().get("customer")
        logger.warning("shopify get_customer %s: %s", customer_id, r.status_code)
        return None
    except Exception as e:
        logger.error("shopify get_customer failed: %s", e)
        return None


async def get_order(order_id: str) -> dict[str, Any] | None:
    url = _base_url() + f"orders/{order_id}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers())
        if r.is_success:
            return r.json().get("order")
        logger.warning("shopify get_order %s: %s", order_id, r.status_code)
        return None
    except Exception as e:
        logger.error("shopify get_order failed: %s", e)
        return None


async def get_fulfillment(order_id: str) -> list[dict[str, Any]]:
    url = _base_url() + f"orders/{order_id}/fulfillments.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers())
        if r.is_success:
            return r.json().get("fulfillments", [])
        return []
    except Exception as e:
        logger.error("shopify get_fulfillment failed: %s", e)
        return []


async def get_orders_by_customer(customer_id: str, limit: int = 10) -> list[dict[str, Any]]:
    url = _base_url() + "orders.json"
    params = {"customer_id": customer_id, "status": "any", "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=_headers())
        if r.is_success:
            return [
                {
                    "id": o.get("id"),
                    "name": o.get("name"),
                    "financial_status": o.get("financial_status"),
                    "fulfillment_status": o.get("fulfillment_status"),
                    "created_at": o.get("created_at"),
                }
                for o in r.json().get("orders", [])
            ]
        return []
    except Exception as e:
        logger.error("shopify get_orders_by_customer failed: %s", e)
        return []
