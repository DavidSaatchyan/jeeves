from __future__ import annotations

import base64
import datetime
import io
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import qrcode
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..channels.registry import get_channel, list_all_configs, upsert_channel
from ..db import get_db
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import Tenant
from .deps import _ctx, get_admin_tenant
from .router import router, templates

_CLINIKO_SHARDS = ["au1", "au2", "au3", "au4", "au5", "eu1", "us1", "ca1", "uk1", "nz1", "sg1"]
_KNOWN_SHARDS = set(_CLINIKO_SHARDS)


# ── SSR page ────────────────────────────────────────────────────


@router.get("/integrations", response_class=HTMLResponse)
def integrations_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "integrations_hub.html", context=_ctx(request))


# ── Legacy redirects ────────────────────────────────────────────


@router.get("/channels", response_class=HTMLResponse)
def legacy_channels():
    return RedirectResponse(url="/admin/integrations", status_code=status.HTTP_302_FOUND)


@router.get("/pabau", response_class=HTMLResponse)
def legacy_pabau():
    return RedirectResponse(url="/admin/integrations", status_code=status.HTTP_302_FOUND)


@router.get("/cliniko", response_class=HTMLResponse)
def legacy_cliniko():
    return RedirectResponse(url="/admin/integrations", status_code=status.HTTP_302_FOUND)


# ── API: list all integrations ──────────────────────────────────


@router.get("/api/integrations")
def api_integrations(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    crm_config = tenant.crm_config or {}
    crm_provider = tenant.crm_provider or ""
    crm_connected = crm_provider in ("cliniko", "pabau") and bool(crm_config.get("api_key"))

    channels = list_all_configs(db, tenant.id)
    channel_map = {c["channel_type"]: c for c in channels}

    integrations = [
        {
            "id": "cliniko",
            "name": "Cliniko",
            "category": "crm",
            "status": "connected" if crm_connected and crm_provider == "cliniko" else "not_configured",
            "meta": {
                "shard": crm_config.get("shard", ""),
                "api_key": crm_config.get("api_key", "") or "",
            },
        },
        {
            "id": "pabau",
            "name": "Pabau",
            "category": "crm",
            "status": "connected" if crm_connected and crm_provider == "pabau" else "not_configured",
            "meta": {
                "company_id": crm_config.get("company_id", ""),
            },
        },
        {
            "id": "whatsapp",
            "name": "WhatsApp",
            "category": "channel",
            "status": "connected" if channel_map.get("whatsapp", {}).get("status") == "active" else channel_map.get("whatsapp", {}).get("status", "not_configured"),
            "meta": channel_map.get("whatsapp", {}).get("config_mask", {}),
        },
        {
            "id": "instagram",
            "name": "Instagram",
            "category": "channel",
            "status": "connected" if channel_map.get("instagram", {}).get("status") == "active" else channel_map.get("instagram", {}).get("status", "not_configured"),
            "meta": channel_map.get("instagram", {}).get("config_mask", {}),
        },
        {
            "id": "widget",
            "name": "Web Widget",
            "category": "channel",
            "status": "connected" if channel_map.get("web_widget", {}).get("status") == "active" else channel_map.get("web_widget", {}).get("status", "not_configured"),
            "meta": channel_map.get("web_widget", {}).get("config_mask", {}),
        },
    ]

    return {"integrations": integrations}


# ── Helpers ──────────────────────────────────────────────────────


def _try_shard(api_key: str, shard: str) -> bool:
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "User-Agent": "Jeeves (devs@jeeves.ai)",
    }
    try:
        r = httpx.get(f"https://api.{shard}.cliniko.com/v1/practitioners", headers=headers, timeout=10)
        return r.status_code == 200
    except httpx.RequestError:
        return False


def _shard_from_key(api_key: str) -> str | None:
    if len(api_key) >= 4 and api_key[-4] == "-":
        candidate = api_key[-3:]
        if candidate in _KNOWN_SHARDS:
            return candidate
    return None


def _discover_shard(api_key: str) -> str | None:
    shard = _shard_from_key(api_key)
    if shard and _try_shard(api_key, shard):
        return shard
    with ThreadPoolExecutor(max_workers=len(_CLINIKO_SHARDS)) as ex:
        future_map = {ex.submit(_try_shard, api_key, s): s for s in _CLINIKO_SHARDS}
        for f in as_completed(future_map):
            if f.result():
                return future_map[f]
    return None


class _CrmConfigureBody(BaseModel):
    provider: str
    api_key: str | None = None
    company_id: str | None = None
    webhook_secret: str | None = None


# ── API: CRM configure ─────────────────────────────────────────


@router.post("/api/integrations/crm/configure")
def configure_crm(
    body: _CrmConfigureBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    provider = body.provider.strip().lower()
    if provider not in ("cliniko", "pabau"):
        raise HTTPException(status_code=400, detail="Unsupported CRM provider")

    if provider == "cliniko":
        api_key = (body.api_key or "").strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="API Key is required")
        shard = _discover_shard(api_key)
        if not shard:
            return {"ok": True, "connected": False, "message": "Connection failed — check API key"}
        tenant.crm_config = {
            "api_key": api_key,
            "shard": shard,
            "user_agent": "Jeeves (devs@jeeves.ai)",
        }
        tenant.crm_provider = "cliniko"
    else:
        api_key = (body.api_key or "").strip()
        company_id = (body.company_id or "").strip()
        if not api_key or not company_id:
            raise HTTPException(status_code=400, detail="API Key and Company ID are required")
        tenant.crm_config = {
            "api_key": api_key,
            "company_id": company_id,
            "webhook_secret": body.webhook_secret or "",
        }
        tenant.crm_provider = "pabau"

    db.flush()
    db.commit()
    return {"ok": True, "connected": True, "message": f"Connected to {provider.title()}"}


# ── API: CRM test ───────────────────────────────────────────────


@router.post("/api/integrations/crm/test")
def test_crm(
    tenant: Tenant = Depends(get_admin_tenant),
):
    config = tenant.crm_config or {}
    if not config.get("api_key"):
        raise HTTPException(status_code=400, detail="CRM not configured")
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(status_code=400, detail="Could not create CRM adapter")
    try:
        ok = adapter.test_connection()
        if ok:
            return {"ok": True, "message": "Connection successful"}
        raise HTTPException(status_code=502, detail="Connection failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── API: CRM disconnect ─────────────────────────────────────────


@router.post("/api/integrations/crm/disconnect")
def disconnect_crm(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.crm_config = {}
    tenant.crm_provider = "pabau"
    db.flush()
    db.commit()
    return {"ok": True}


# ── API: WhatsApp configure ─────────────────────────────────────


class _WhatsAppConfigureBody(BaseModel):
    phone_number_id: str
    access_token: str
    verify_token: str
    business_phone: str


@router.post("/api/integrations/whatsapp/configure")
def configure_whatsapp(
    body: _WhatsAppConfigureBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    config = {
        "phone_number_id": body.phone_number_id.strip(),
        "access_token": body.access_token.strip(),
        "verify_token": body.verify_token.strip(),
        "business_phone": body.business_phone.strip(),
    }
    upsert_channel(db, tenant.id, "whatsapp", config, status="active")
    db.commit()
    return {"ok": True, "message": "WhatsApp configured and active"}


@router.post("/api/integrations/whatsapp/disconnect")
def disconnect_whatsapp(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    from ..channels.registry import delete_channel
    delete_channel(db, tenant.id, "whatsapp")
    db.commit()
    return {"ok": True}


# ── In-memory QR sessions (MVP — simulated) ─────────────────────
# Real WhatsApp Cloud API QR requires Meta Business proxy;
# for MVP we generate a QR pointing to setup instructions
# and provide manual token entry as the primary flow.


_qr_sessions: dict[str, dict] = {}
_QR_SESSION_TTL = 300  # 5 minutes


@router.post("/api/integrations/whatsapp/qr")
def whatsapp_qr():
    session_id = str(uuid.uuid4())
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data("https://developers.facebook.com/docs/whatsapp/cloud-api/get-started")
    qr.make()
    img = qr.make_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    _qr_sessions[session_id] = {
        "status": "pending",
        "created_at": datetime.datetime.utcnow(),
    }
    return {"qr_code": f"data:image/png;base64,{b64}", "session_id": session_id}


@router.get("/api/integrations/whatsapp/qr/status")
def whatsapp_qr_status(session_id: str = Query(...)):
    session = _qr_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    elapsed = (datetime.datetime.utcnow() - session["created_at"]).total_seconds()
    if elapsed > _QR_SESSION_TTL:
        session["status"] = "expired"
    return {"status": session["status"]}


# ── API: Instagram configure ────────────────────────────────────


class _InstagramConfigureBody(BaseModel):
    access_token: str
    business_page_id: str
    instagram_account_id: str


@router.post("/api/integrations/instagram/configure")
def configure_instagram(
    body: _InstagramConfigureBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    config = {
        "access_token": body.access_token,
        "business_page_id": body.business_page_id,
        "instagram_account_id": body.instagram_account_id,
    }
    upsert_channel(db, tenant.id, "instagram", config, status="active")
    db.commit()
    return {"ok": True, "message": "Instagram connected"}


@router.post("/api/integrations/instagram/disconnect")
def disconnect_instagram(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    from ..channels.registry import delete_channel
    delete_channel(db, tenant.id, "instagram")
    db.commit()
    return {"ok": True}


@router.get("/api/integrations/instagram/auth")
def instagram_auth(request: Request):
    """Redirect to Facebook OAuth dialog."""
    from ..config import get_settings
    settings = get_settings()
    if not settings.facebook_app_id:
        raise HTTPException(status_code=400, detail="Facebook App not configured")
    fb_url = (
        f"https://www.facebook.com/v22.0/dialog/oauth"
        f"?client_id={settings.facebook_app_id}"
        f"&redirect_uri={settings.facebook_redirect_uri or str(request.base_url) + 'admin/api/integrations/instagram/callback'}"
        f"&scope=pages_manage_metadata,pages_messaging,instagram_basic,instagram_manage_messages"
        f"&response_type=code"
    )
    return RedirectResponse(url=fb_url)


@router.get("/api/integrations/instagram/callback")
def instagram_callback(
    request: Request,
    code: str = "",
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    """Exchange Facebook OAuth code for long-lived token."""
    from ..config import get_settings
    settings = get_settings()
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    try:
        r = httpx.post(
            "https://graph.facebook.com/v22.0/oauth/access_token",
            data={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.facebook_app_secret,
                "redirect_uri": settings.facebook_redirect_uri or str(request.base_url) + "admin/api/integrations/instagram/callback",
                "code": code,
            },
            timeout=15,
        )
        r.raise_for_status()
        token_data = r.json()
        access_token = token_data.get("access_token", "")

        # Get Facebook Pages the user manages
        pages_resp = httpx.get(
            f"https://graph.facebook.com/v22.0/me/accounts",
            params={"access_token": access_token},
            timeout=15,
        )
        pages_resp.raise_for_status()
        pages = pages_resp.json().get("data", [])
        if not pages:
            raise HTTPException(status_code=400, detail="No Facebook Pages found")

        page = pages[0]
        page_id = page["id"]
        page_token = page.get("access_token", "")

        # Get Instagram account linked to the page
        ig_resp = httpx.get(
            f"https://graph.facebook.com/v22.0/{page_id}",
            params={"fields": "instagram_business_account", "access_token": page_token},
            timeout=15,
        )
        ig_resp.raise_for_status()
        ig_data = ig_resp.json()
        ig_account_id = ig_data.get("instagram_business_account", {}).get("id", "")

        config = {
            "access_token": page_token,
            "business_page_id": page_id,
            "instagram_account_id": ig_account_id,
        }
        upsert_channel(db, tenant.id, "instagram", config, status="active")
        db.commit()
        return {"ok": True, "connected": True, "instagram_account_id": ig_account_id}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Facebook API error: {e.response.text[:200]}")


# ── API: Widget configure ────────────────────────────────────────


class _WidgetConfigureBody(BaseModel):
    title: str = "Jeeves support"
    subtitle: str = ""
    greeting: str = "Hi. How can I help?"
    accent_color: str = "#5e6ad2"
    position: str = "right"
    email_required: bool = True
    allowed_origins: list[str] = []


@router.post("/api/integrations/widget/configure")
def configure_widget(
    body: _WidgetConfigureBody,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    config = {
        "title": body.title,
        "subtitle": body.subtitle,
        "greeting": body.greeting,
        "accent_color": body.accent_color,
        "position": body.position,
        "email_required": body.email_required,
        "allowed_origins": body.allowed_origins or [],
    }
    upsert_channel(db, tenant.id, "web_widget", config, status="active")
    db.commit()
    return {"ok": True, "message": "Widget settings saved"}


@router.get("/api/integrations/widget/status")
def widget_status(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cfg = get_channel(db, tenant.id, "web_widget")
    if not cfg:
        return {"script_detected": False, "checked_at": None}
    origins = cfg.config.get("allowed_origins", [])
    script_detected = False
    checked_at = None
    if origins:
        import datetime
        try:
            r = httpx.get(origins[0], timeout=5)
            script_detected = "<jeeves-widget" in r.text
            checked_at = datetime.datetime.utcnow().isoformat()
        except Exception:
            pass
    return {"script_detected": script_detected, "checked_at": checked_at}


# ── API: available channels for agent linking ────────────────────


@router.get("/api/integrations/available")
def available_channels(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    channels = list_all_configs(db, tenant.id)
    available = [
        {
            "id": c["channel_type"],
            "label": c["label"],
            "connected": c["status"] == "active",
        }
        for c in channels
        if c["channel_type"] in ("whatsapp", "instagram", "web_widget")
    ]
    return {"channels": available}
