"""Shopify Admin REST API connector.

Credentials dict: {"shop": "mystore.myshopify.com", "access_token": "..."}
Base URL: https://{shop}/admin/api/2024-01/
"""
from __future__ import annotations

import httpx

from ..crypto import ConnectorError

_API_VERSION = "2024-01"


def _base_url(shop: str) -> str:
    return f"https://{shop}/admin/api/{_API_VERSION}/"


def _headers(access_token: str) -> dict[str, str]:
    return {"X-Shopify-Access-Token": access_token}


async def get_orders_by_email(credentials: dict, email: str) -> list[dict]:
    """GET /orders.json?email={email}&status=any&limit=10"""
    shop = credentials["shop"]
    access_token = credentials["access_token"]
    url = _base_url(shop) + "orders.json"
    params = {"email": email, "status": "any", "limit": 10}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=_headers(access_token))
    except httpx.TimeoutException:
        raise ConnectorError(provider="shopify", operation="get_orders_by_email", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="shopify",
            operation="get_orders_by_email",
            status_code=r.status_code,
            message=r.text[:200],
        )

    data = r.json()
    orders = data.get("orders", [])
    return [
        {
            "id": o.get("id"),
            "name": o.get("name"),
            "financial_status": o.get("financial_status"),
            "fulfillment_status": o.get("fulfillment_status"),
            "tracking_number": _extract_tracking(o),
            "created_at": o.get("created_at"),
        }
        for o in orders
    ]


def _extract_tracking(order: dict) -> str | None:
    """Extract first tracking number from fulfillments, if any."""
    for fulfillment in order.get("fulfillments", []):
        for item in fulfillment.get("tracking_numbers", []):
            return item
        if fulfillment.get("tracking_number"):
            return fulfillment["tracking_number"]
    return None


async def get_order(credentials: dict, order_id: str) -> dict:
    """GET /orders/{order_id}.json"""
    shop = credentials["shop"]
    access_token = credentials["access_token"]
    url = _base_url(shop) + f"orders/{order_id}.json"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_headers(access_token))
    except httpx.TimeoutException:
        raise ConnectorError(provider="shopify", operation="get_order", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="shopify",
            operation="get_order",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json().get("order", {})


async def update_shipping_address(
    credentials: dict,
    order_id: str,
    address: dict,
    idempotency_key: str,
) -> dict:
    """PUT /orders/{order_id}.json with shipping_address."""
    shop = credentials["shop"]
    access_token = credentials["access_token"]
    url = _base_url(shop) + f"orders/{order_id}.json"
    headers = {
        **_headers(access_token),
        "X-Shopify-Idempotency-Key": idempotency_key,
    }
    payload = {"order": {"id": order_id, "shipping_address": address}}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        raise ConnectorError(provider="shopify", operation="update_shipping_address", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="shopify",
            operation="update_shipping_address",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json().get("order", {})


async def cancel_order(
    credentials: dict,
    order_id: str,
    idempotency_key: str,
) -> dict:
    """POST /orders/{order_id}/cancel.json"""
    shop = credentials["shop"]
    access_token = credentials["access_token"]
    url = _base_url(shop) + f"orders/{order_id}/cancel.json"
    headers = {
        **_headers(access_token),
        "X-Shopify-Idempotency-Key": idempotency_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers)
    except httpx.TimeoutException:
        raise ConnectorError(provider="shopify", operation="cancel_order", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="shopify",
            operation="cancel_order",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json().get("order", {})
