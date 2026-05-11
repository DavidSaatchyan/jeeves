from __future__ import annotations

from .classifier import classify_failure
from .sentiment import detect_frustration
from .generator import generate_email, generate_widget_message

__all__ = [
    "classify_failure",
    "detect_frustration",
    "generate_email",
    "generate_widget_message",
]
