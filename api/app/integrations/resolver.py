from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ..models import Tenant
from .base import AbstractCrmConnector
from .cliniko import ClinikoConnector
from .pabau import PabauConnector

CRM_PROVIDERS: dict[str, type[AbstractCrmConnector]] = {
    "pabau": PabauConnector,
    "cliniko": ClinikoConnector,
}


def get_crm_adapter(tenant_id: UUID, db: Session) -> AbstractCrmConnector | None:
    tenant: Tenant | None = db.get(Tenant, tenant_id)
    if not tenant or not tenant.crm_config:
        return None
    provider = tenant.crm_provider or "pabau"
    cls = CRM_PROVIDERS.get(provider)
    if not cls:
        return None
    return cls(tenant.crm_config)


def get_crm_adapter_for_tenant(tenant: Tenant) -> AbstractCrmConnector | None:
    if not tenant.crm_config:
        return None
    provider = tenant.crm_provider or "pabau"
    cls = CRM_PROVIDERS.get(provider)
    if not cls:
        return None
    return cls(tenant.crm_config)
