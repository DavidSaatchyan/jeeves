from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from passlib.context import CryptContext

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "jeeves_session"
