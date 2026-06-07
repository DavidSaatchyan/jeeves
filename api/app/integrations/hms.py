from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class HmsConnector(ABC):
    """HMS (Healthcare Management System) connector — practice data sync interface.

    Thin adapter that wraps CRM-specific API calls into 3 entity types
    (services, practitioners, clinics) for sync to knowledge base.
    """

    provider: str

    @abstractmethod
    def fetch_services(self, updated_since: str | None = None) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def fetch_practitioners(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def fetch_clinics(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        ...
