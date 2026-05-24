from __future__ import annotations

import re

from fastapi import HTTPException


def validate_password_strength(password: str):
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(400, "Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(400, "Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise HTTPException(400, "Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;':\",.<>?/`~\\]", password):
        raise HTTPException(400, "Password must contain at least one special character")


def prepare_password(password: str) -> str:
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
