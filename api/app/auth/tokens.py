from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException

from .router import settings


def _get_redis():
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def revoke_token(jti: str, exp_ts: int):
    r = _get_redis()
    if r:
        r.setex(f"revoked:{jti}", max(exp_ts - int(datetime.utcnow().timestamp()), 1), "1")


def is_token_revoked(jti: str) -> bool:
    r = _get_redis()
    if r:
        return r.exists(f"revoked:{jti}") > 0
    return False


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
