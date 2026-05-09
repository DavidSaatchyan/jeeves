from __future__ import annotations

from typing import Any


async def check_guard_conditions(guards: list[dict[str, Any]]) -> tuple[bool, str]:
    for guard in guards:
        condition = guard.get("condition")
        if callable(condition):
            result = await condition()
            if not result:
                return False, guard.get("reason", "guard_condition_failed")
        elif condition is not None and not condition:
            return False, guard.get("reason", "guard_condition_failed")
    return True, ""
