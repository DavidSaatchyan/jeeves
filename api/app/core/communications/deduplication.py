from __future__ import annotations

from ...shared.idempotency import idempotency_get, idempotency_set

_COMMS_DEDUP_TTL = 86400


async def is_duplicate_communication(communication_id: str) -> bool:
    existing = await idempotency_get(communication_id)
    if existing is not None:
        return True
    await idempotency_set(communication_id, True, ttl=_COMMS_DEDUP_TTL)
    return False
