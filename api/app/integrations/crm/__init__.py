from __future__ import annotations

from typing import Any

from .base import AbstractCrmConnector
from .custom_api import CustomApiAdapter
from .zoho import ZohoCRMAdapter

_registry: dict[str, type[AbstractCrmConnector]] = {}


def register_crm_provider(provider: str, cls: type[AbstractCrmConnector]) -> None:
    _registry[provider] = cls


def get_crm_adapter(provider: str, config: dict[str, Any]) -> AbstractCrmConnector:
    from ...crypto import ConnectorError
    cls = _registry.get(provider)
    if cls is None:
        raise ConnectorError(provider=provider, operation="get_adapter", message=f"Unknown CRM provider: {provider}")
    return cls(config)


def list_crm_providers() -> list[str]:
    return list(_registry.keys())


register_crm_provider("zoho", ZohoCRMAdapter)
register_crm_provider("custom_api", CustomApiAdapter)

try:
    from .hubspot import HubSpotAdapter  # noqa: F811
    register_crm_provider("hubspot", HubSpotAdapter)
except ImportError:
    pass

try:
    from .salesforce import SalesforceAdapter  # noqa: F811
    register_crm_provider("salesforce", SalesforceAdapter)
except ImportError:
    pass


__all__ = [
    "AbstractCrmConnector",
    "get_crm_adapter",
    "list_crm_providers",
    "register_crm_provider",
]
