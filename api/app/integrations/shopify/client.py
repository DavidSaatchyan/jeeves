from __future__ import annotations

import logging
from typing import Any

import httpx

from ...crypto import ConnectorError

logger = logging.getLogger(__name__)

_API_VERSION = "2024-01"


def _base_url(credentials: dict) -> str:
    shop = credentials.get("shop_domain", "")
    return f"https://{shop}/admin/api/{_API_VERSION}/"


def _headers(credentials: dict) -> dict[str, str]:
    return {"X-Shopify-Access-Token": credentials.get("access_token", "")}


async def get_customer(credentials: dict, customer_id: str) -> dict[str, Any] | None:
    url = _base_url(credentials) + f"customers/{customer_id}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("customer")
        logger.warning("shopify get_customer %s: %s", customer_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="shopify", operation="get_customer", message=str(e))


async def get_order(credentials: dict, order_id: str) -> dict[str, Any] | None:
    url = _base_url(credentials) + f"orders/{order_id}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("order")
        logger.warning("shopify get_order %s: %s", order_id, r.status_code)
        return None
    except httpx.RequestError as e:
        raise ConnectorError(provider="shopify", operation="get_order", message=str(e))


async def get_fulfillment(credentials: dict, order_id: str) -> list[dict[str, Any]]:
    url = _base_url(credentials) + f"orders/{order_id}/fulfillments.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers(credentials))
        if r.is_success:
            return r.json().get("fulfillments", [])
        return []
    except httpx.RequestError as e:
        raise ConnectorError(provider="shopify", operation="get_fulfillment", message=str(e))


async def get_orders_by_customer(credentials: dict, customer_id: str, limit: int = 10) -> list[dict[str, Any]]:
    url = _base_url(credentials) + "orders.json"
    params = {"customer_id": customer_id, "status": "any", "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=_headers(credentials))
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
    except httpx.RequestError as e:
        raise ConnectorError(provider="shopify", operation="get_orders_by_customer", message=str(e))
