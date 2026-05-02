"""Built-in mock API for testing integrations without a real external service.

Endpoints (no auth required, tenant-scoped by user_id):
  GET  /mock/customers/{user_id}        — returns fake customer profile
  PATCH /mock/customers/{user_id}/plan  — simulates plan change
  GET  /mock/orders/{order_id}          — returns fake order status
  POST /mock/tickets                    — simulates ticket creation

Use these URLs in the Integrations page to test the full flow end-to-end.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from fastapi import APIRouter

router = APIRouter(prefix="/mock", tags=["mock"])

_PLANS = ["starter", "business", "enterprise"]
_STATUSES = ["active", "trialing", "past_due"]
_ORDER_STATUSES = ["processing", "shipped", "delivered", "cancelled"]


def _fake_customer(user_id: str) -> dict:
    # Deterministic-ish values based on user_id hash so same user always returns same data
    h = abs(hash(user_id))
    return {
        "user_id": user_id,
        "name": "Test User",
        "email": user_id if "@" in user_id else f"{user_id}@example.com",
        "plan": _PLANS[h % len(_PLANS)],
        "status": _STATUSES[h % len(_STATUSES)],
        "orders_count": (h % 20) + 1,
        "subscription_end": (date.today() + timedelta(days=30 + h % 335)).isoformat(),
        "company": "Acme Corp",
    }


@router.get("/customers/{user_id}")
def get_customer(user_id: str):
    return _fake_customer(user_id)


@router.patch("/customers/{user_id}/plan")
def update_plan(user_id: str, body: dict = {}):
    new_plan = body.get("plan", "unknown")
    return {
        "ok": True,
        "user_id": user_id,
        "plan": new_plan,
        "message": f"Plan updated to {new_plan}",
    }


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    h = abs(hash(order_id))
    return {
        "order_id": order_id,
        "status": _ORDER_STATUSES[h % len(_ORDER_STATUSES)],
        "items": (h % 5) + 1,
        "total_usd": round(19.99 + (h % 200), 2),
        "estimated_delivery": (date.today() + timedelta(days=h % 7 + 1)).isoformat(),
    }


@router.post("/tickets")
def create_ticket(body: dict = {}):
    return {
        "ok": True,
        "ticket_id": f"TKT-{random.randint(10000, 99999)}",
        "subject": body.get("subject", "Support request"),
        "status": "open",
    }
