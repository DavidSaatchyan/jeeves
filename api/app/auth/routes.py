from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..config import get_yaml_config
from ..db import get_db
from ..models import Tenant
from ..rate_limit import check_rate_limit
from ..schemas import AuthOut, LoginIn, RefreshIn, RegisterIn, TokenOut
from .deps import _get_client_ip
from .passwords import prepare_password, validate_password_strength
from .router import SESSION_COOKIE, pwd_ctx, router
from .tokens import decode_token, issue_tokens, revoke_token


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("register", ip):
        raise HTTPException(429, "Too many registration attempts. Try again later.")
    validate_password_strength(body.password)
    exists = db.query(Tenant).filter(Tenant.email == body.email).first()
    if exists:
        raise HTTPException(400, "Email already exists")
    cfg = get_yaml_config().get("billing", {})
    trial_days = int(cfg.get("trial_days", 14))

    tenant = Tenant(
        name=body.tenant_name,
        email=body.email,
        hashed_password=pwd_ctx.hash(prepare_password(body.password)),
        email_verified=True,
        trial_ends=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    access, refresh = issue_tokens(tenant.id)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=access,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=900,
        path="/admin",
    )

    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh_tokens(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    revoke_token(payload.get("jti", ""), payload.get("exp", 0))
    tid = uuid.UUID(payload["sub"])
    if not db.get(Tenant, tid):
        raise HTTPException(401, "Tenant not found")
    access, refresh = issue_tokens(tid)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/revoke")
def revoke(body: dict):
    jti = body.get("jti", "")
    exp_ts = body.get("exp_ts", 0)
    if not jti:
        raise HTTPException(400, "jti required")
    revoke_token(jti, exp_ts)
    return {"ok": True}


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("login", ip):
        raise HTTPException(429, "Too many login attempts. Try again later.")
    tenant = db.query(Tenant).filter(Tenant.email == body.email).first()
    if not tenant or not pwd_ctx.verify(prepare_password(body.password), tenant.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    access, refresh = issue_tokens(tenant.id)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=access,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=900,
        path="/admin",
    )

    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)
