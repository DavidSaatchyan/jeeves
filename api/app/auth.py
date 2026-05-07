"""Auth: register, login, JWT issuing/validation, API key support, tenant dependency."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import ApiKey, Tenant
from .rate_limit import check_rate_limit
from .schemas import AuthOut, LoginIn, RefreshIn, RegisterIn, TokenOut

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Redis-backed token denylist ──────────────────────────────────────────────

def _get_redis():
    """Return a Redis client if available, else None."""
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def revoke_token(jti: str, exp_ts: int) -> None:
    """Add a token's jti to the Redis denylist, TTL'd to the token's expiry."""
    r = _get_redis()
    if r:
        r.setex(f"revoked:{jti}", max(exp_ts - int(datetime.utcnow().timestamp()), 1), "1")


def is_token_revoked(jti: str) -> bool:
    r = _get_redis()
    if r:
        return r.exists(f"revoked:{jti}") > 0
    return False


# ── helpers ──────────────────────────────────────────────────────────────────

def _validate_password_strength(password: str) -> None:
    """Enforce: min 12 chars, at least one uppercase, one lowercase, one digit, one special."""
    if len(password) < 12:
        raise HTTPException(400, "Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(400, "Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(400, "Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise HTTPException(400, "Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;':\",.<>?/`~\\]", password):
        raise HTTPException(400, "Password must contain at least one special character")


def _prepare_password(password: str) -> str:
    """Truncate to 72 bytes — bcrypt limit."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


def _hash_key(key: str) -> str:
    import hashlib
    import hmac
    pepper = settings.jwt_secret
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


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
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if is_token_revoked(payload.get("jti", "")):
            raise HTTPException(401, "Token has been revoked")
        return payload
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
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has expired")
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


def issue_email_verify_token(tenant_id: uuid.UUID) -> str:
    """Create a short-lived signed token for email verification."""
    now = datetime.utcnow()
    payload = {
        "sub": str(tenant_id),
        "purpose": "email_verify",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("register", ip):
        raise HTTPException(429, "Too many registration attempts. Try again later.")
    _validate_password_strength(body.password)
    exists = db.query(Tenant).filter(Tenant.email == body.email).first()
    if exists:
        raise HTTPException(400, "Email already exists")
    from .config import get_yaml_config
    cfg = get_yaml_config().get("billing", {})
    trial_days = int(cfg.get("trial_days", 14))

    tenant = Tenant(
        name=body.tenant_name,
        email=body.email,
        hashed_password=pwd_ctx.hash(_prepare_password(body.password)),
        email_verified=False,
        trial_ends=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # Signed email-verification token (24h expiry)
    verify_token = issue_email_verify_token(tenant.id)
    verify_link = f"{settings.public_base_url}/auth/verify?token={verify_token}"
    print(f"[email-stub] Verification link for {tenant.email}: {verify_link}", flush=True)

    access, refresh = issue_tokens(tenant.id)
    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("login", ip):
        raise HTTPException(429, "Too many login attempts. Try again later.")
    tenant = db.query(Tenant).filter(Tenant.email == body.email).first()
    if not tenant or not pwd_ctx.verify(_prepare_password(body.password), tenant.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    access, refresh = issue_tokens(tenant.id)
    return AuthOut(tenant_id=tenant.id, access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh_tokens(body: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    # Revoke the old refresh token (rotation)
    revoke_token(payload.get("jti", ""), payload.get("exp", 0))
    tid = uuid.UUID(payload["sub"])
    if not db.get(Tenant, tid):
        raise HTTPException(401, "Tenant not found")
    access, refresh = issue_tokens(tid)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/revoke")
def revoke(body: dict):
    """Revoke a token by its JTI. Useful for logout / key rotation."""
    jti = body.get("jti", "")
    exp_ts = body.get("exp_ts", 0)
    if not jti:
        raise HTTPException(400, "jti required")
    revoke_token(jti, exp_ts)
    return {"ok": True}


@router.get("/verify")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Verification link expired")
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid verification token")
    if payload.get("purpose") != "email_verify":
        raise HTTPException(400, "Wrong token purpose")
    t = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not t:
        raise HTTPException(404, "Tenant not found")
    t.email_verified = True
    db.commit()
    # Revoke the verify token after use
    revoke_token(payload.get("jti", ""), payload.get("exp", 0))
    return {"ok": True}
