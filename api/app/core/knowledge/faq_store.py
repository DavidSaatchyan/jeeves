from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_FAQ_FILE = Path(_settings.knowledge_dir) / "faq_store.json"


def load_faq_store() -> dict[str, list[dict[str, str]]]:
    if not _FAQ_FILE.exists():
        return {}
    try:
        with _FAQ_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("failed to load FAQ store: %s", e)
        return {}


def save_faq_store(data: dict[str, list[dict[str, str]]]) -> bool:
    try:
        _FAQ_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _FAQ_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error("failed to save FAQ store: %s", e)
        return False


def search_faq_store(query: str, tenant_id: str) -> list[dict[str, str]]:
    store = load_faq_store()
    entries = store.get(tenant_id, [])
    q = query.lower()
    return [
        e for e in entries
        if q in e.get("question", "").lower() or q in e.get("answer", "").lower()
    ]


def add_faq_entry(tenant_id: str, question: str, answer: str) -> bool:
    store = load_faq_store()
    if tenant_id not in store:
        store[tenant_id] = []
    store[tenant_id].append({"question": question, "answer": answer})
    return save_faq_store(store)


def delete_faq_entry(tenant_id: str, index: int) -> bool:
    store = load_faq_store()
    entries = store.get(tenant_id, [])
    if 0 <= index < len(entries):
        entries.pop(index)
        store[tenant_id] = entries
        return save_faq_store(store)
    return False
