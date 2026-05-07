"""CRM connector: read/write via configured REST endpoints + JSONPath mapping.

Extended for Task 7: delegates to native connectors (Shopify, WooCommerce, Stripe)
when NativeConnector rows exist, and supports primary_identifier-based lookup.
"""
from __future__ import annotations

import ipaddress
import socket
import time
import json
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from jsonpath_ng.ext import parse as jp_parse
from sqlalchemy.orm import Session

from .crypto import ConnectorError, decrypt
from .models import CRMActionLog, CRMConfig, NativeConnector
from . import hubspot

_DEFAULT_CAPS = {
    "read_customer": True,
    "update_plan": False,
    "create_ticket": False,
    "require_confirmation": True,
}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _url_safe(url: str) -> None:
    """Raise ConnectorError if URL resolves to a private/internal address."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConnectorError(f"Only http/https allowed: {url}")
    hostname = parsed.hostname or ""
    if hostname.lower() in {"localhost", "metadata", "169.254.169.254"}:
        raise ConnectorError(f"URL not allowed: {url}")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        except (socket.gaierror, ValueError):
            return  # unresolvable — let httpx fail naturally
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            raise ConnectorError(f"URL resolves to a blocked network: {ip}")

# Simple TTL cache for CRM reads: {cache_key: (data, expires_at)}
_customer_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 300  # 5 minutes


def _get_cached(tenant_id: UUID, user_id: str) -> dict | None:
    key = f"{tenant_id}:{user_id}"
    entry = _customer_cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    _customer_cache.pop(key, None)
    return None


def _set_cached(tenant_id: UUID, user_id: str, data: dict):
    key = f"{tenant_id}:{user_id}"
    _customer_cache[key] = (data, time.time() + _CACHE_TTL)


def _invalidate_cache(tenant_id: UUID, user_id: str | None = None):
    if user_id:
        _customer_cache.pop(f"{tenant_id}:{user_id}", None)
    else:
        # Invalidate all entries for this tenant
        to_remove = [k for k in _customer_cache if k.startswith(f"{tenant_id}:")]
        for k in to_remove:
            del _customer_cache[k]


def resolve_identifier(cfg: CRMConfig | None, user_id: str, extra_fields: dict | None = None) -> str:
    """Return the actual lookup value based on CRMConfig.primary_identifier.

    - 'email' → user_id is treated as email
    - 'user_id' → user_id is treated as user_id
    - 'custom' → look up the field name from capabilities['identifier_field'] in extra_fields
    """
    identifier = cfg.primary_identifier if cfg else "email"
    if identifier == "email":
        return user_id
    if identifier == "user_id":
        return user_id
    # custom — use field name from capabilities
    if cfg and cfg.capabilities:
        field_name = cfg.capabilities.get("identifier_field")
        if field_name and extra_fields and field_name in extra_fields:
            return str(extra_fields[field_name])
    # Fallback to user_id
    return user_id


def _get_active_connectors(db: Session, tenant_id: UUID) -> list[NativeConnector]:
    """Return connected native connectors for a tenant."""
    return (
        db.query(NativeConnector)
        .filter(
            NativeConnector.tenant_id == tenant_id,
            NativeConnector.status == "connected",
        )
        .all()
    )


def _get_decrypted_connector(db: Session, tenant_id: UUID, provider: str) -> dict | None:
    """Return decrypted credentials dict for a native connector, or None."""
    nc = (
        db.query(NativeConnector)
        .filter(
            NativeConnector.tenant_id == tenant_id,
            NativeConnector.provider == provider,
            NativeConnector.status == "connected",
        )
        .first()
    )
    if not nc:
        return None
    return json.loads(decrypt(nc.credentials))


def _apply_mapping(data: Any, mapping: dict[str, str]) -> dict[str, Any]:
    out = {}
    for field, expr in (mapping or {}).items():
        try:
            matches = [m.value for m in jp_parse(expr).find(data)]
            out[field] = matches[0] if matches else None
        except Exception:
            out[field] = None
    return out


def _fmt_url(url: str, user_id: str) -> str:
    return (url or "").replace("{id}", user_id).replace("{user_id}", user_id)


def get_config(db: Session, tenant_id: UUID) -> CRMConfig | None:
    return db.get(CRMConfig, tenant_id)


def capabilities(cfg: CRMConfig | None) -> dict[str, Any]:
    data = dict(DEFAULT_CAPABILITIES)
    if cfg and cfg.capabilities:
        data.update(cfg.capabilities)
    return data


def can(cfg: CRMConfig | None, name: str) -> bool:
    return bool(capabilities(cfg).get(name))


def mask_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if not value:
            out[key] = value
        elif key.lower() in {"authorization", "x-api-key", "api-key", "token"}:
            out[key] = "********"
        else:
            out[key] = value
    return out


def merge_headers(existing: dict[str, str] | None, incoming: dict[str, str] | None) -> dict[str, str]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value == "********":
            continue
        if value == "":
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def log_action(
    db: Session,
    tenant_id: UUID,
    user_id: str,
    action: str,
    status: str,
    request: dict | None = None,
    response: Any | None = None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> None:
    db.add(
        CRMActionLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            status=status,
            request=request or {},
            response=response if isinstance(response, dict) else ({"value": response} if response is not None else None),
            error=error,
            latency_ms=latency_ms,
        )
    )
    db.commit()


async def read_customer(
    db: Session,
    tenant_id: UUID,
    user_id: str,
    extra_fields: dict | None = None,
) -> dict:
    """Read customer data from CRM.

    When native connectors (Shopify, WooCommerce, Stripe) are connected,
    delegate to the appropriate connector module using the resolved identifier.
    Falls back to HubSpot or custom REST as before.

    Results are cached for 5 minutes per tenant+user to avoid repeated API calls.

    extra_fields: optional dict from widget.identify() for custom identifier lookup.
    """
    cfg = get_config(db, tenant_id)
    lookup_key = resolve_identifier(cfg, user_id, extra_fields)

    # Check cache first
    cached = _get_cached(tenant_id, lookup_key)
    if cached is not None:
        return cached

    # 1. Try native connectors first
    native_data = await _read_from_native_connectors(db, tenant_id, lookup_key)
    if native_data:
        _set_cached(tenant_id, lookup_key, native_data)
        return native_data

    # 2. Fall back to HubSpot
    if cfg and cfg.provider == "hubspot":
        data = await hubspot.get_customer(db, tenant_id, user_id)
        _set_cached(tenant_id, lookup_key, data)
        return data

    # 3. Fall back to custom REST
    if not cfg or not cfg.read_url:
        return {}
    if not can(cfg, "read_customer"):
        return {}
    url = _fmt_url(cfg.read_url, user_id)
    _url_safe(url)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, headers=cfg.headers or {})
        r.raise_for_status()
        payload = r.json()
    result = _apply_mapping(payload, cfg.read_mapping or {}) | {"raw": payload}
    _set_cached(tenant_id, lookup_key, result)
    return result


async def _read_from_native_connectors(db: Session, tenant_id: UUID, lookup_key: str) -> dict:
    """Query all active native connectors and merge their results.

    Returns merged dict with keys like 'shopify_orders', 'woocommerce_orders', 'stripe_subscription'.
    Returns {} if no native connectors are active.
    """
    connectors = _get_active_connectors(db, tenant_id)
    if not connectors:
        return {}

    merged: dict[str, Any] = {}
    for nc in connectors:
        try:
            creds = json.loads(decrypt(nc.credentials))
            if nc.provider == "shopify":
                from .connectors import shopify as shopify_conn
                orders = await shopify_conn.get_orders_by_email(creds, lookup_key)
                if orders:
                    merged["shopify_orders"] = orders
            elif nc.provider == "woocommerce":
                from .connectors import woocommerce as woo_conn
                orders = await woo_conn.get_orders_by_email(creds, lookup_key)
                if orders:
                    merged["woocommerce_orders"] = orders
                customer = await woo_conn.get_customer(creds, lookup_key)
                if customer:
                    merged["woocommerce_customer"] = customer
            elif nc.provider == "stripe":
                from .connectors import stripe_connector as stripe_conn
                sub = await stripe_conn.get_subscription(creds, lookup_key)
                if sub:
                    merged["stripe_subscription"] = sub
                invoice = await stripe_conn.get_next_invoice(creds, lookup_key)
                if invoice:
                    merged["stripe_next_invoice"] = invoice
        except ConnectorError:
            # Best-effort: skip failing connectors, don't block the whole read
            pass
        except Exception:
            pass

    return merged


async def write_customer(db: Session, tenant_id: UUID, user_id: str, updates: dict) -> dict:
    cfg = get_config(db, tenant_id)
    if not cfg or not cfg.write_url:
        raise RuntimeError("CRM write_url not configured")
    if not can(cfg, "update_plan"):
        raise RuntimeError("CRM update_plan capability is disabled")
    url = _fmt_url(cfg.write_url, user_id)
    _url_safe(url)
    # Build body according to write_mapping: field -> jsonpath like $.data.tariff
    # For MVP we build a nested dict from the jsonpath expression.
    body: dict = {}
    for field, expr in (cfg.write_mapping or {}).items():
        if field not in updates or updates[field] is None:
            continue
        path = str(expr).lstrip("$").lstrip(".")
        parts = [p for p in path.split(".") if p]
        cur = body
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1] if parts else field] = updates[field]
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(url, json=body, headers=cfg.headers or {})
        r.raise_for_status()
    _invalidate_cache(tenant_id, user_id)
    try:
        return r.json()
    except Exception:
        return {"ok": True}


async def test_connection(db: Session, tenant_id: UUID, sample_user_id: str = "test") -> dict:
    cfg = get_config(db, tenant_id)
    if not cfg or not cfg.read_url:
        return {"ok": False, "error": "read_url not set"}
    url = _fmt_url(cfg.read_url, sample_user_id)
    _url_safe(url)
    try:
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=cfg.headers or {})
        latency_ms = int((time.perf_counter() - started) * 1000)
        sample = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500]
        mapped = _apply_mapping(sample, cfg.read_mapping or {}) if isinstance(sample, (dict, list)) else {}
        return {
            "ok": r.status_code < 400,
            "status_code": r.status_code,
            "mapped": mapped,
            "sample": sample,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
