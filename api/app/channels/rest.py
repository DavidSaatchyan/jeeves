"""REST channel: already provided by FastAPI routes (/chat). This adapter
is kept for symmetry with BaseChannel interface."""
from __future__ import annotations

from .base import BaseChannel, Handler


class RestChannel(BaseChannel):
    def __init__(self) -> None:
        self._handler: Handler | None = None

    async def start(self) -> None:
        # FastAPI serves /chat directly; nothing to start.
        return None

    async def send_message(self, user_id: str, message: str) -> None:
        # Outgoing messages for REST users are persisted as chat_logs rows
        # and consumed via /chat/inbox polling or widget SSE.
        return None

    def set_handler(self, handler: Handler) -> None:
        self._handler = handler
