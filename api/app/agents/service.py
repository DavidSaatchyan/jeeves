from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..shared.inbox_writer import add_message, get_or_create_conversation
from ..shared.moderation import moderate
from ..shared.rate_limit import check_rate_limit
from ..shared.timer import timed
from ..models import ChatLog
from .registry import dispatch

logger = logging.getLogger("jeeves.agents.service")


@dataclass
class ProcessMessageResult:
    blocked: bool = False
    block_reason: str = ""
    rate_limited: bool = False
    response: str | None = None
    escalate: bool = False
    intent: str | None = None
    conversation_id: str | None = None
    is_new_conversation: bool = False
    latency_ms: int = 0
    citations: list[dict] = field(default_factory=list)


@timed("process_message")
async def process_message(
    *,
    tenant_id: str,
    customer_id: str,
    message: str,
    channel: str,
    db: Session,
    agent_id: str = "incoming_line",
    contact_name: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> ProcessMessageResult:
    flagged, category = moderate(message)
    if flagged:
        logger.info("msg blocked by moderation: channel=%s customer=%s reason=%s", channel, customer_id, category)
        return ProcessMessageResult(blocked=True, block_reason=category)

    if not await check_rate_limit(channel, customer_id):
        logger.info("rate limited: channel=%s customer=%s", channel, customer_id)
        return ProcessMessageResult(rate_limited=True)

    start = datetime.utcnow()
    result = await dispatch(
        agent_id,
        tenant_id=tenant_id,
        customer_id=customer_id,
        message=message,
        db=db,
        history=conversation_history,
    )
    latency = int((datetime.utcnow() - start).total_seconds() * 1000)

    if result.response:
        conv = get_or_create_conversation(db, tenant_id, customer_id, channel, user_display_name=contact_name)
        is_new = conv.created_at == conv.updated_at
        add_message(db, conv, "incoming", message)
        add_message(db, conv, "outgoing", result.response)
        conv_id = str(conv.id)
    else:
        conv_id = None
        is_new = False

    log = ChatLog(
        tenant_id=tenant_id,
        user_id=customer_id,
        direction="incoming",
        message=message,
        response=result.response,
        resolution="escalated" if result.escalate else "resolved",
        channel=channel,
        latency_ms=latency,
    )
    db.add(log)
    db.commit()

    return ProcessMessageResult(
        response=result.response,
        escalate=result.escalate,
        intent=result.intent,
        conversation_id=conv_id,
        is_new_conversation=is_new,
        latency_ms=latency,
        citations=result.citations,
    )
