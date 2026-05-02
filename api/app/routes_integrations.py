"""Integration management endpoints: native connectors, webhooks, write-back."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .crypto import ConnectorError, decrypt, encrypt
from .db import get_db
from .models import NativeConnector, Tenant, WebhookConfig, WriteBackConfig
from .schemas import (
    IntegrationStatusOut,
    NativeConnectIn,
    NativeConnectOut,
    WebhookConfigIn,
    WebhookConfigOut,
    WriteBackConfigIn,
    WriteBackConfigOut,
)
from .connectors import registry

router = APIRouter(prefix="/integrations", tags=["integrations"])

SUPPORTED_PROVIDERS = {"shopify", "woocommerce", "stripe"}


def _to_native_out(nc: NativeConnector) -> NativeConnectOut:
    return NativeConnectOut(
        provider=nc.provider,
        status=nc.status,
        meta=nc.meta or {},
        created_at=nc.created_at.isoformat(),
        updated_at=nc.updated_at.isoformat(),
    )


def _to_webhook_out(cfg: WebhookConfig) -> WebhookConfigOut:
    return WebhookConfigOut(
        incoming_url=cfg.incoming_url,
        outgoing_url=cfg.outgoing_url,
        field_mapping=cfg.field_mapping or {},
        events=cfg.events or [],
        enabled=cfg.enabled,
        created_at=cfg.created_at.isoformat(),
        updated_at=cfg.updated_at.isoformat(),
    )


def _to_writeback_out(cfg: WriteBackConfig) -> WriteBackConfigOut:
    return WriteBackConfigOut(
        type=cfg.type,
        hubspot_note_enabled=cfg.hubspot_note_enabled,
        hubspot_task_on_escalation=cfg.hubspot_task_on_escalation,
        webhook_url=cfg.webhook_url,
        created_at=cfg.created_at.isoformat(),
        updated_at=cfg.updated_at.isoformat(),
    )


@router.get("", response_model=IntegrationStatusOut)
def list_integrations(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    connectors = (
        db.query(NativeConnector)
        .filter(NativeConnector.tenant_id == tenant.id)
        .all()
    )
    webhook = db.get(WebhookConfig, tenant.id)
    writeback = db.get(WriteBackConfig, tenant.id)
    return IntegrationStatusOut(
        native_connectors=[_to_native_out(c) for c in connectors],
        webhook_config=_to_webhook_out(webhook) if webhook else None,
        writeback_config=_to_writeback_out(writeback) if writeback else None,
    )


@router.post("/native", response_model=NativeConnectOut, status_code=201)
def connect_native(
    body: NativeConnectIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if body.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {body.provider}")

    # Validate required credentials per provider
    _validate_credentials(body.provider, body.credentials)

    now = datetime.now(timezone.utc)
    encrypted = encrypt(json.dumps(body.credentials))

    existing = (
        db.query(NativeConnector)
        .filter(
            NativeConnector.tenant_id == tenant.id,
            NativeConnector.provider == body.provider,
        )
        .first()
    )

    try:
        if existing:
            existing.credentials = encrypted
            existing.status = "connected"
            existing.meta = body.meta
            existing.updated_at = now
        else:
            existing = NativeConnector(
                tenant_id=tenant.id,
                provider=body.provider,
                credentials=encrypted,
                meta=body.meta,
                created_at=now,
                updated_at=now,
            )
            db.add(existing)

        registry.provision_tools(db, tenant.id, body.provider)
        db.commit()
        db.refresh(existing)
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(500, f"Failed to connect: {e}")

    return _to_native_out(existing)


@router.delete("/native/{provider}")
def disconnect_native(
    provider: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}")

    connector = (
        db.query(NativeConnector)
        .filter(
            NativeConnector.tenant_id == tenant.id,
            NativeConnector.provider == provider,
        )
        .first()
    )
    if not connector:
        raise HTTPException(404, f"Provider {provider} not connected")

    try:
        db.delete(connector)
        registry.deprovision_tools(db, tenant.id, provider)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to disconnect: {e}")

    return {"ok": True}


@router.post("/native/{provider}/test")
async def test_native(
    provider: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider: {provider}")

    connector = (
        db.query(NativeConnector)
        .filter(
            NativeConnector.tenant_id == tenant.id,
            NativeConnector.provider == provider,
        )
        .first()
    )
    if not connector:
        raise HTTPException(404, f"Provider {provider} not connected")

    try:
        creds = json.loads(decrypt(connector.credentials))
        ok = await _test_connectivity(provider, creds)
    except ConnectorError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Test failed: {e}"}

    return {"ok": ok}


@router.get("/webhook", response_model=WebhookConfigOut)
def get_webhook_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = db.get(WebhookConfig, tenant.id)
    if not cfg:
        return WebhookConfigOut(
            incoming_url=None,
            outgoing_url=None,
            incoming_secret=None,
            outgoing_secret=None,
            field_mapping={},
            events=[],
            enabled=True,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    return _to_webhook_out(cfg)


@router.post("/webhook", response_model=WebhookConfigOut, status_code=201)
def save_webhook_config(
    body: WebhookConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = db.get(WebhookConfig, tenant.id)
    now = datetime.now(timezone.utc)

    if not cfg:
        cfg = WebhookConfig(tenant_id=tenant.id, created_at=now)
        db.add(cfg)

    cfg.incoming_url = body.incoming_url
    if body.incoming_secret:
        cfg.incoming_secret = encrypt(body.incoming_secret)
    cfg.outgoing_url = body.outgoing_url
    if body.outgoing_secret:
        cfg.outgoing_secret = encrypt(body.outgoing_secret)
    cfg.field_mapping = body.field_mapping
    cfg.events = body.events
    cfg.enabled = body.enabled
    cfg.updated_at = now
    db.commit()
    db.refresh(cfg)
    return _to_webhook_out(cfg)


@router.get("/writeback", response_model=WriteBackConfigOut)
def get_writeback_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = db.get(WriteBackConfig, tenant.id)
    if not cfg:
        return WriteBackConfigOut(
            type="off",
            hubspot_note_enabled=False,
            hubspot_task_on_escalation=False,
            webhook_url=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    return _to_writeback_out(cfg)


@router.post("/writeback", response_model=WriteBackConfigOut, status_code=201)
def save_writeback_config(
    body: WriteBackConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = db.get(WriteBackConfig, tenant.id)
    now = datetime.now(timezone.utc)

    if not cfg:
        cfg = WriteBackConfig(tenant_id=tenant.id, created_at=now)
        db.add(cfg)

    cfg.type = body.type
    cfg.hubspot_note_enabled = body.hubspot_note_enabled
    cfg.hubspot_task_on_escalation = body.hubspot_task_on_escalation
    cfg.webhook_url = body.webhook_url
    cfg.updated_at = now
    db.commit()
    db.refresh(cfg)
    return _to_writeback_out(cfg)


# ---- Internal helpers ----


def _validate_credentials(provider: str, creds: dict) -> None:
    """Raise HTTPException if required keys are missing."""
    required = {
        "shopify": {"shop", "access_token"},
        "woocommerce": {"base_url", "consumer_key", "consumer_secret"},
        "stripe": {"secret_key"},
    }
    missing = required.get(provider, set()) - set(creds.keys())
    if missing:
        raise HTTPException(400, f"Missing credential keys for {provider}: {missing}")


async def _test_connectivity(provider: str, creds: dict) -> bool:
    """Attempt a lightweight API call to verify credentials."""
    if provider == "shopify":
        import httpx
        from .connectors.shopify import get_orders_by_email
        try:
            await get_orders_by_email(creds, "test@example.com")
            return True
        except ConnectorError as e:
            if e.status_code == 401 or e.status_code == 403:
                return False
            # Other errors (e.g. no orders found) still mean connected
            return True
    elif provider == "woocommerce":
        from .connectors.woocommerce import get_orders_by_email
        try:
            await get_orders_by_email(creds, "test@example.com")
            return True
        except ConnectorError as e:
            if e.status_code == 401 or e.status_code == 403:
                return False
            return True
    elif provider == "stripe":
        from .connectors.stripe_connector import get_subscription
        try:
            await get_subscription(creds, "test@example.com")
            return True
        except ConnectorError:
            # Stripe returns empty dict when customer not found, not an error
            return True
    return False
