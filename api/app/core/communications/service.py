from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .delivery import send_email
from .templates import (
    render_delay_notification,
    render_delivery_confirmation,
    render_lost_package,
    render_tracking_update,
)
from ...core.timeline.recorder import record_timeline_event

logger = logging.getLogger(__name__)


async def send_communication(db: Session, tenant_id: str, customer_id: str, channel: str,
                             template_name: str, context: dict[str, Any],
                             workflow_id: str | None = None) -> str | None:
    from uuid import uuid4
    from datetime import datetime

    from .deduplication import is_duplicate_communication

    comm_id = uuid4().hex

    if await is_duplicate_communication(comm_id):
        logger.info("duplicate communication skipped: %s", comm_id)
        return None

    templates = {
        "tracking_update": render_tracking_update,
        "delay_notification": render_delay_notification,
        "delivery_confirmation": render_delivery_confirmation,
        "lost_package": render_lost_package,
    }

    renderer = templates.get(template_name)
    if not renderer:
        logger.warning("unknown template: %s", template_name)
        return None

    content = renderer(context)

    if channel == "email":
        success = await send_email(
            to=context.get("email", ""),
            subject=content.get("subject", ""),
            body=content.get("body", ""),
        )
        delivery_status = "sent" if success else "failed"
    elif channel == "widget":
        delivery_status = "queued"
    else:
        logger.warning("unsupported channel: %s", channel)
        return None

    from sqlalchemy import text
    db.execute(
        text("""
            INSERT INTO communications (id, workflow_id, tenant_id, customer_id, channel, template_name,
                delivery_status, direction, message_type, created_at)
            VALUES (:id, :wid, :tid, :cid, :ch, :tpl, :ds, 'outgoing', 'automated', :now)
        """),
        {"id": comm_id, "wid": workflow_id, "tid": tenant_id, "cid": customer_id,
         "ch": channel, "tpl": template_name, "ds": delivery_status, "now": datetime.utcnow()},
    )

    record_timeline_event(
        db=db,
        event_type=f"comms_{delivery_status}",
        entity_type="customer",
        entity_id=customer_id,
        tenant_id=tenant_id,
        payload={"communication_id": comm_id, "channel": channel, "template": template_name},
    )

    return comm_id


async def send_pending_communications(db: Session) -> int:
    from sqlalchemy import text
    from datetime import datetime

    pending = db.execute(
        text("SELECT id, tenant_id, customer_id, channel, template_name FROM communications WHERE status = 'queued'"),
    ).fetchall()

    sent = 0
    for row in pending:
        try:
            db.execute(
                text("UPDATE communications SET status = 'sent', updated_at = :now WHERE id = :id"),
                {"now": datetime.utcnow(), "id": row[0]},
            )
            db.commit()
            sent += 1
        except Exception as e:
            logger.error("failed to send pending comm %s: %s", row[0], e)

    return sent
