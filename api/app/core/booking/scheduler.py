from __future__ import annotations


class SlotAlreadyBookedError(Exception):
    """Raised when the slot_token is already taken by another booking."""


class AppointmentNotFoundError(Exception):
    """Raised when appointment does not exist."""
