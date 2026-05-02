"""HubSpot OAuth connector and normalized customer lookup."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from sqlalchemy.orm import Session

from .config import get_settings
from .models import CRMConfig, CRMConnection

settings = get_settings()

AUTH_URL = "https://app.hubspot.com/oauth/authorize"
TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
CONTACT_SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
SCOPES = ["oauth", "crm.objects.contacts.read", "crm.objects.companies.read"]


def enabled() -> bool:
    return bool(settings.hubspot_client_id and settings.hubspot_client_secret)


def issue_state(tenant_id: UUID) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(tenant_id),
        "kind": "hubspot_oauth_state",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_state(state: str) -> UUID:
    payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("kind") != "hubspot_oauth_state":
        raise ValueError("wrong state kind")
    return UUID(payload["sub"])


def authorization_url(tenant_id: UUID) -> str:
    params = {
        "client_id": settings.hubspot_client_id,
        "redirect_uri": settings.hubspot_redirect_uri,
        "scope": " ".join(SCOPES),
        "state": issue_state(tenant_id),
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.hubspot_client_id,
                "client_secret": settings.hubspot_client_secret,
                "redirect_uri": settings.hubspot_redirect_uri,
                "code": code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()


async def refresh_access_token(db: Session, conn: CRMConnection) -> str:
    if conn.expires_at > datetime.utcnow() + timedelta(minutes=2):
        return conn.access_token
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.hubspot_client_id,
                "client_secret": settings.hubspot_client_secret,
                "refresh_token": conn.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        data = r.json()
    conn.access_token = data["access_token"]
    conn.refresh_token = data.get("refresh_token") or conn.refresh_token
    conn.expires_at = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 1800)))
    conn.scopes = data.get("scope", "").split()
    conn.updated_at = datetime.utcnow()
    db.commit()
    return conn.access_token


def get_connection(db: Session, tenant_id: UUID) -> CRMConnection | None:
    return (
        db.query(CRMConnection)
        .filter(
            CRMConnection.tenant_id == tenant_id,
            CRMConnection.provider == "hubspot",
            CRMConnection.status == "connected",
        )
        .order_by(CRMConnection.updated_at.desc())
        .first()
    )


def save_connection(db: Session, tenant_id: UUID, token_data: dict[str, Any]) -> CRMConnection:
    existing = get_connection(db, tenant_id)
    conn = existing or CRMConnection(tenant_id=tenant_id, provider="hubspot")
    conn.status = "connected"
    conn.access_token = token_data["access_token"]
    conn.refresh_token = token_data["refresh_token"]
    conn.expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in", 1800)))
    conn.scopes = token_data.get("scope", "").split()
    conn.updated_at = datetime.utcnow()
    if not existing:
        db.add(conn)

    cfg = db.get(CRMConfig, tenant_id)
    if not cfg:
        cfg = CRMConfig(tenant_id=tenant_id)
        db.add(cfg)
    cfg.provider = "hubspot"
    cfg.capabilities = {
        "read_customer": True,
        "update_plan": False,
        "create_ticket": False,
        "require_confirmation": True,
    }
    db.commit()
    db.refresh(conn)
    return conn


def disconnect(db: Session, tenant_id: UUID) -> None:
    conn = get_connection(db, tenant_id)
    if conn:
        conn.status = "disconnected"
        conn.updated_at = datetime.utcnow()
    cfg = db.get(CRMConfig, tenant_id)
    if cfg and cfg.provider == "hubspot":
        cfg.provider = "custom_rest"
    db.commit()


def status(db: Session, tenant_id: UUID) -> dict[str, Any]:
    conn = get_connection(db, tenant_id)
    return {
        "configured": enabled(),
        "connected": bool(conn),
        "expires_at": conn.expires_at.isoformat() if conn else None,
        "scopes": conn.scopes if conn else [],
    }


async def get_customer(db: Session, tenant_id: UUID, user_id: str) -> dict[str, Any]:
    conn = get_connection(db, tenant_id)
    if not conn:
        return {}
    token = await refresh_access_token(db, conn)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            CONTACT_SEARCH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {"propertyName": "email", "operator": "EQ", "value": user_id}
                        ]
                    }
                ],
                "properties": [
                    "email",
                    "firstname",
                    "lastname",
                    "company",
                    "lifecyclestage",
                    "plan",
                    "tariff",
                    "subscription_plan",
                ],
                "limit": 1,
            },
        )
        r.raise_for_status()
        data = r.json()
    rows = data.get("results") or []
    if not rows:
        return {"found": False, "source": "hubspot"}
    contact = rows[0]
    props = contact.get("properties") or {}
    name = " ".join(p for p in [props.get("firstname"), props.get("lastname")] if p).strip()
    return {
        "found": True,
        "source": "hubspot",
        "hubspot_contact_id": contact.get("id"),
        "email": props.get("email"),
        "name": name or None,
        "company": props.get("company"),
        "lifecycle_stage": props.get("lifecyclestage"),
        "tariff": props.get("tariff") or props.get("plan") or props.get("subscription_plan"),
        "raw": contact,
    }
