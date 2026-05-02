"""Base channel adapter (FR-5.5).

A new channel = subclass + implement 3 methods. Core stays unchanged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

Handler = Callable[[str, str, str], Awaitable[str]]
# handler(tenant_id, user_id, message) -> response_text


class BaseChannel(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Start listening on the channel."""

    @abstractmethod
    async def send_message(self, user_id: str, message: str) -> None:
        """Send an outgoing message to a user."""

    @abstractmethod
    def set_handler(self, handler: Handler) -> None:
        """Register the incoming-message handler."""
