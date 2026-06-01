from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import CalendarConnection, Tenant
from .deps import get_admin_tenant
from .router import router

logger = logging.getLogger(__name__)


@router.get("/calendar/connect/google")
def google_oauth_start(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Redirect to Google OAuth consent screen."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google Calendar is not configured")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise HTTPException(
            status_code=400,
            detail="google-auth-oauthlib is not installed. Run: pip install google-auth-oauthlib",
        )

    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=settings.google_redirect_uri,
    )
    flow.redirect_uri = settings.google_redirect_uri

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(tenant.id),
    )
    return {"authorization_url": authorization_url}


@router.get("/calendar/oauth/google/callback")
def google_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback. State contains the tenant_id."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google Calendar is not configured")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise HTTPException(
            status_code=400,
            detail="google-auth-oauthlib is not installed. Run: pip install google-auth-oauthlib",
        )

    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=settings.google_redirect_uri,
    )
    flow.redirect_uri = settings.google_redirect_uri

    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    tenant_id = UUID(state) if state else None

    if not tenant_id:
        raise HTTPException(status_code=400, detail="Missing tenant_id in OAuth state")

    existing = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.tenant_id == tenant_id,
            CalendarConnection.provider == "google",
        )
    ).scalar_one_or_none()

    if existing:
        existing.access_token = credentials.token
        existing.refresh_token = credentials.refresh_token or existing.refresh_token
        existing.token_expiry = credentials.expiry
        existing.status = "connected"
        existing.updated_at = datetime.utcnow()
    else:
        conn = CalendarConnection(
            tenant_id=tenant_id,
            provider="google",
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_expiry=credentials.expiry,
            calendar_id="primary",
            status="connected",
        )
        db.add(conn)

    db.commit()
    return RedirectResponse(url="/admin/connections", status_code=302)


@router.get("/api/calendar/status")
def calendar_status(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Return calendar connection status."""
    conn = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()

    if not conn:
        return {"connected": False, "provider": None, "calendar_id": None}

    return {
        "connected": conn.status == "connected",
        "provider": conn.provider,
        "calendar_id": conn.calendar_id,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
    }


@router.post("/api/calendar/disconnect")
def calendar_disconnect(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Disconnect calendar provider."""
    conn = db.execute(
        select(CalendarConnection).where(
            CalendarConnection.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()

    if conn:
        db.delete(conn)
        db.commit()

    return {"ok": True}
