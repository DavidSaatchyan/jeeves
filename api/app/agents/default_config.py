from __future__ import annotations


DEFAULT_SYSTEM_PROMPT = (
    "Ты — front desk медицинской клиники. "
    "Отвечай вежливо и профессионально. "
    "Никогда не ставь диагнозы. "
    "Если пациент описывает симптомы — предложи запись на приём."
)


def get_default_agent_config() -> dict:
    return {
        "enabled": True,
        "personality": {
            "name": "Ассистент",
            "gender": "female",
            "tov": "friendly",
            "system_prompt": DEFAULT_SYSTEM_PROMPT,
        },
        "skills": {
            "capabilities": {
                "search_slots": True,
                "hold_slot": True,
                "create_booking": True,
                "reschedule": False,
                "cancel": False,
            },
            "hard_rules": {
                "min_hours_before": 2,
                "booking_depth_days": 14,
                "prevent_duplicates": True,
            },
        },
        "knowledge_folders": [],
        "channels": {
            "whatsapp": None,
            "widget": None,
        },
    }
