from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Customer, Message


def _ensure_customer(db: Session, conversation: Conversation, user_display_name: str | None = None) -> None:
    cust = db.scalar(
        select(Customer).where(
            Customer.tenant_id == conversation.tenant_id,
            Customer.email == conversation.user_id,
        )
    )
    if not cust:
        cust = db.scalar(
            select(Customer).where(
                Customer.tenant_id == conversation.tenant_id,
                Customer.phone == conversation.user_id,
            )
        )
    if not cust:
        cust = Customer(
            tenant_id=conversation.tenant_id,
            email=conversation.user_id if "@" in conversation.user_id else None,
            display_name=user_display_name or conversation.user_id,
        )
        db.add(cust)
        db.flush()

    if user_display_name and not cust.display_name:
        cust.display_name = user_display_name
    cust.last_seen_at = datetime.utcnow()
    cust.last_message_at = datetime.utcnow()

    if not conversation.customer_id:
        conversation.customer_id = cust.id


def get_or_create_conversation(
    db: Session,
    tenant_id,
    user_id: str,
    channel: str = "web_widget",
    user_display_name: str | None = None,
) -> Conversation:
    existing = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.channel == channel,
            Conversation.status != "closed",
        )
        .order_by(Conversation.last_message_at.desc())
    )
    if existing:
        _ensure_customer(db, existing, user_display_name)
        return existing

    conv = Conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        user_display_name=user_display_name or user_id,
        channel=channel,
    )
    db.add(conv)
    db.flush()
    _ensure_customer(db, conv, user_display_name)
    return conv


def add_message(
    db: Session,
    conversation: Conversation,
    direction: str,
    content: str,
    content_type: str = "text",
    sender_type: str = "customer",
    operator_id: str | None = None,
) -> Message:
    msg = Message(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=direction,
        content=content,
        content_type=content_type,
        sender_type=sender_type,
        operator_id=operator_id,
    )
    db.add(msg)

    conversation.last_message_preview = content[:120]
    conversation.last_message_at = datetime.utcnow()
    conversation.message_count += 1
    if direction == "incoming":
        conversation.unread_count += 1

    db.flush()
    return msg
