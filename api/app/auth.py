"""Auth: register, login, JWT issuing/validation, API key support, tenant dependency."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import ApiKey, Tenant
from .schemas import AuthOut, LoginIn, RegisterIn, TokenOut

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_key(key: str) -> str:
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()


def _issue(tenant_id: uuid.UUID, kind: str, ttl) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(tenant_id),
        "kind": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def issue_tokens(tenant_id: uuid.UUID) -> tuple[str, str]:
    access = _issue(tenant_id, "access", timedelta(minutes=settings.access_token_ttl_minutes))
    refresh = _issue(tenant_id, "refresh", timedelta(days=settings.refresh_token_ttl_days))
    return access, refresh


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def get_current_tenant(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]

    # API key path: starts with "sk_"
    if token.startswith("sk_"):
        from datetime import datetime
        key_hash = _hash_key(token)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        api_key.last_used_at = datetime.utcnow()
        db.commit()
        tenant = db.get(Tenant, api_key.tenant_id)
        if not tenant:
            raise HTTPException(401, "Tenant not found")
        return tenant

    # JWT path
    payload = decode_token(token)
    if payload.get("kind") != "access":
        raise HTTPException(401, "Wrong token kind")
    tenant = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not tenant:
        raise HTTPException(401, "Tenant not found")
    return tenant


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(Tenant).filter(Tenant.email == body.email).first()
    if exists:
        raise HTTPException(400, "Email already exists")
    from .config import get_yaml_config
    cfg = get_yaml_config().get("billing", {})
    trial_days = int(cfg.get("trial_days", 14))

    tenant = Tenant(
        name=body.tenant_name,
        email=body.email,
        hashed_password=pwd_ctx.hash(body.password),
        trial_ends=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # DEFAULT: email-verification link is only printed to stdout in MVP.
    verify_link = f"{settings.public_base_url}/auth/verify?tid={tenant.id}"
    print(f"[email-stub] Verification link for {tenant.email}: {verify_link}", flush=True)

    access, refresh = issue_tokens(tenant.id)
    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.email == body.email).first()
    if not tenant or not pwd_ctx.verify(body.password, tenant.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    access, refresh = issue_tokens(tenant.id)
    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh_tokens(refresh_token: str, db: Session = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    tid = uuid.UUID(payload["sub"])
    if not db.get(Tenant, tid):
        raise HTTPException(401, "Tenant not found")
    access, refresh = issue_tokens(tid)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.get("/verify")
def verify_email(tid: str, db: Session = Depends(get_db)):
    t = db.get(Tenant, uuid.UUID(tid))
    if not t:
        raise HTTPException(404, "Tenant not found")
    t.email_verified = True
    db.commit()
    return {"ok": True}
