from __future__ import annotations

import hashlib
import re
import secrets
import time
from typing import Any

from ...config import get_yaml_config

PHI_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),             # SSN
    re.compile(r"\+\d{7,15}\b"),                       # international phone
    re.compile(r"\b\d{10}\b"),                          # 10-digit phone (US)
    re.compile(r"\b[\w.-]+@[\w.-]+\.\w{2,}\b"),        # email
    re.compile(r"\bM\s*R\s*\.?\s*\d+\b"),               # medical record number
    re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"),         # name (first + last)
    re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}"),            # date
    re.compile(r"\b\d{5}(?:-\d{4})?\b"),                # ZIP code
]

_PHI_REPLACEMENTS: dict[str, str] = {
    "SSN": "[SSN]",
    "phone": "[PHONE]",
    "email": "[EMAIL]",
    "name": "[NAME]",
    "date": "[DOB]",
    "diagnosis": "[DIAGNOSIS]",
    "address": "[ADDRESS]",
}


def _load_custom_patterns() -> list[re.Pattern]:
    yaml_config = get_yaml_config()
    patterns = yaml_config.get("compliance", {}).get("phi_patterns", {})
    extra: list[re.Pattern] = []
    for label, raw in patterns.items():
        try:
            extra.append(re.compile(raw))
        except re.error:
            pass
    return extra


_CUSTOM_PATTERNS: list[re.Pattern] = []


def _reload_custom_patterns() -> None:
    global _CUSTOM_PATTERNS
    _CUSTOM_PATTERNS = _load_custom_patterns()


def strip_phi(text: str) -> str:
    result = text
    for pattern in PHI_PATTERNS + _CUSTOM_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def mask_phi(data: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
    sensitive_keys = {"ssn", "email", "phone", "dob", "date_of_birth", "passport", "address", "diagnosis"}
    keys_to_mask = fields or [k for k in data if k.lower() in sensitive_keys]
    result = dict(data)
    for key in keys_to_mask:
        if key in result and result[key] is not None:
            result[key] = "[REDACTED]"
    return result


class PHIMinimizer:
    """Class-based API matching PLAN-PHASE2-COMPLIANCE 2.2 spec."""

    @staticmethod
    def strip_phi(text: str) -> str:
        return strip_phi(text)

    @staticmethod
    def make_secure_link(resource_type: str, resource_id: str, expire_seconds: int = 3600) -> str:
        token = secrets.token_urlsafe(32)
        expiry = int(time.time()) + expire_seconds
        h = hashlib.sha256(f"{resource_type}:{resource_id}:{token}:{expiry}".encode()).hexdigest()[:16]
        return f"/s/{resource_type}/{resource_id}?token={token}&expires={expiry}&sig={h}"

    @staticmethod
    def is_phi(text: str) -> bool:
        for pattern in PHI_PATTERNS + _CUSTOM_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def tokenize(resource_type: str, resource_id: str, expire_seconds: int = 3600) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        expiry = int(time.time()) + expire_seconds
        return {
            "token": token,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "expires_at": expiry,
        }
