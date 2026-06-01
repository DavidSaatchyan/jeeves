from __future__ import annotations


class ConnectorError(Exception):
    """Generic connector error."""

    def __init__(self, provider: str, operation: str, message: str) -> None:
        self.provider = provider
        self.operation = operation
        self.message = message
        super().__init__(f"[{provider}] {operation}: {message}")


class ConnectorAuthError(ConnectorError):
    """Authentication failure."""


class ConnectorNotFoundError(ConnectorError):
    """Resource not found."""


class ConnectorRateLimitError(ConnectorError):
    """API rate limit exceeded."""
