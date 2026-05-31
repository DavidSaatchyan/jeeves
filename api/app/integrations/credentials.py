"""Per-tenant credential resolution for native connectors.
Resolves credentials from NativeConnector (encrypted) for the given tenant + provider.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..crypto import decrypt, ConnectorError
from ..models import NativeConnector

logger = logging.getLogger(__name__)

_PROVIDERS: frozenset[str] = frozenset({
    "zoho", "hubspot", "salesforce", "custom_api",
})


def get_credentials(tenant_id: Any, provider: str, db: Session) -> dict:
    """Fetch per-tenant credentials.

    CRM providers read from CrmConnection.config (JSONB).
    Other providers read from NativeConnector.credentials (encrypted).
    """
    provider = provider.lower()
    if provider not in _PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")

    if provider in {"zoho", "hubspot", "salesforce", "custom_api"}:
        from ..models import CrmConnection
        conn = db.query(CrmConnection).filter(
            CrmConnection.tenant_id == tenant_id,
            CrmConnection.provider == provider,
        ).first()
        if not conn or conn.status != "connected":
            raise ConnectorError(
                provider=provider,
                operation="get_credentials",
                message=f"No connected {provider} connector found for tenant",
            )
        return dict(conn.config or {})

    connector = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant_id,
        NativeConnector.provider == provider,
        NativeConnector.status == "connected",
    ).first()

    if not connector:
        raise ConnectorError(
            provider=provider,
            operation="get_credentials",
            message=f"No connected {provider} connector found for tenant",
        )

    try:
        raw = decrypt(connector.credentials)
        return json.loads(raw)
    except ConnectorError:
        raise
    except Exception as e:
        raise ConnectorError(
            provider=provider,
            operation="decrypt",
            message=f"Failed to decrypt credentials: {e}",
        ) from e
