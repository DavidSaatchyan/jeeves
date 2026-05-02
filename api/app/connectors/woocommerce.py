"""WooCommerce REST API v3 connector.

Credentials dict: {"base_url": "https://mystore.com", "consumer_key": "ck_...", "consumer_secret": "cs_..."}
Base URL: {base_url}/wp-json/wc/v3/
Auth: HTTP Basic (consumer_key:consumer_secret)
"""
from __future__ import annotations

import httpx

from ..crypto import ConnectorError


def _base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/wp-json/wc/v3/"


def _auth(credentials: dict) -> tuple[str, str]:
    return (credentials["consumer_key"], credentials["consumer_secret"])


async def get_orders_by_email(credentials: dict, email: str) -> list[dict]:
    """GET /orders?search={email}&per_page=10"""
    url = _base_url(credentials["base_url"]) + "orders"
    params = {"search": email, "per_page": 10}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, auth=_auth(credentials))
    except httpx.TimeoutException:
        raise ConnectorError(provider="woocommerce", operation="get_orders_by_email", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="woocommerce",
            operation="get_orders_by_email",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json()


async def get_order(credentials: dict, order_id: str) -> dict:
    """GET /orders/{order_id}"""
    url = _base_url(credentials["base_url"]) + f"orders/{order_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, auth=_auth(credentials))
    except httpx.TimeoutException:
        raise ConnectorError(provider="woocommerce", operation="get_order", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="woocommerce",
            operation="get_order",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json()


async def update_order_status(credentials: dict, order_id: str, status: str) -> dict:
    """PUT /orders/{order_id} with {"status": status}"""
    url = _base_url(credentials["base_url"]) + f"orders/{order_id}"
    payload = {"status": status}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.put(url, json=payload, auth=_auth(credentials))
    except httpx.TimeoutException:
        raise ConnectorError(provider="woocommerce", operation="update_order_status", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="woocommerce",
            operation="update_order_status",
            status_code=r.status_code,
            message=r.text[:200],
        )

    return r.json()


async def get_customer(credentials: dict, email: str) -> dict:
    """GET /customers?email={email}&per_page=1, returns first result or {}"""
    url = _base_url(credentials["base_url"]) + "customers"
    params = {"email": email, "per_page": 1}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, auth=_auth(credentials))
    except httpx.TimeoutException:
        raise ConnectorError(provider="woocommerce", operation="get_customer", message="timeout")

    if not r.is_success:
        raise ConnectorError(
            provider="woocommerce",
            operation="get_customer",
            status_code=r.status_code,
            message=r.text[:200],
        )

    results = r.json()
    if isinstance(results, list) and results:
        return results[0]
    return {}
