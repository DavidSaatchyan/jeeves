from __future__ import annotations

import logging
from typing import Any

# Expected fields per provider per entity type.
# Used for schema validation logging during sync — does not block ingestion.
HMS_FIELD_SCHEMAS: dict[str, dict[str, set[str]]] = {
    "cliniko": {
        "service": {"id", "name", "item_type", "price"},
        "practitioner": {"id", "first_name", "last_name"},
        "clinic": {"id", "business_name"},
    },
    "pabau": {
        "service": {"id", "name"},
        "practitioner": {"id", "display_name"},
        "clinic": set(),
    },
}


def validate_hms_records(
    provider: str,
    entity_type: str,
    records: list[dict[str, Any]],
) -> list[str]:
    """Check records against expected field schema.

    Logs a warning for each record missing expected fields.
    Returns list of warning messages (for optional inclusion in sync result).
    Does NOT raise — validation is advisory only.
    """
    schema = HMS_FIELD_SCHEMAS.get(provider, {}).get(entity_type)
    if not schema:
        return []
    logger = logging.getLogger("jeeves.hms_schemas")
    warnings: list[str] = []
    for i, record in enumerate(records):
        missing = schema - set(record.keys())
        if missing:
            msg = f"{provider} {entity_type}[{i}] missing fields: {missing}"
            logger.warning(msg)
            warnings.append(msg)
    return warnings
