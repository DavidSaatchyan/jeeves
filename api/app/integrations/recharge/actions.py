from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .client import get_subscription
from ..credentials import get_credentials

__all__ = [
    "fetch_subscription_state",
]


async def fetch_subscription_state(tenant_id: Any, subscription_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    return await get_subscription(creds, subscription_id)
