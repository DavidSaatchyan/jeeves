from __future__ import annotations


class CrmConnectionError(Exception):
    """Generic CRM connection error."""

    def __init__(self, provider: str, operation: str, message: str) -> None:
        self.provider = provider
        self.operation = operation
        self.message = message
        super().__init__(f"[{provider}] {operation}: {message}")


class CrmAuthError(CrmConnectionError):
    """Authentication / token refresh failure."""


class CrmNotFoundError(CrmConnectionError):
    """Resource not found in CRM."""


class CrmRateLimitError(CrmConnectionError):
    """CRM API rate limit exceeded."""
