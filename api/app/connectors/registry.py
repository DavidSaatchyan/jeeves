"""Connector registry: canonical tool specs and auto-provisioning/deprovisioning."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..models import AgentTool

TOOL_SPECS: dict[str, list[dict]] = {
    "shopify": [
        {
            "name": "shopify_get_orders",
            "description": "Get Shopify orders for a customer by email. Returns order name, status, tracking, and date.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://shopify/orders",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "shopify_get_order",
            "description": "Get a specific Shopify order by order ID. Returns full order details.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://shopify/orders/{order_id}",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID"}
                },
                "required": ["order_id"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "shopify_update_shipping_address",
            "description": "Update the shipping address of a Shopify order. Requires order ID and the new address dict.",
            "tool_type": "action",
            "method": "PUT",
            "url_template": "native://shopify/orders/{order_id}/shipping_address",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID"},
                    "address": {
                        "type": "object",
                        "description": "New shipping address (first_name, last_name, address1, city, province, country, zip, phone)",
                    },
                },
                "required": ["order_id", "address"],
            },
            "require_confirmation": True,
            "enabled": True,
        },
        {
            "name": "shopify_cancel_order",
            "description": "Cancel a Shopify order. Requires order ID.",
            "tool_type": "action",
            "method": "POST",
            "url_template": "native://shopify/orders/{order_id}/cancel",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Shopify order ID"}
                },
                "required": ["order_id"],
            },
            "require_confirmation": True,
            "enabled": True,
        },
    ],
    "woocommerce": [
        {
            "name": "woocommerce_get_orders",
            "description": "Get WooCommerce orders for a customer by email. Returns order details including status and total.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://woocommerce/orders",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "woocommerce_get_order",
            "description": "Get a specific WooCommerce order by order ID.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://woocommerce/orders/{order_id}",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "WooCommerce order ID"}
                },
                "required": ["order_id"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "woocommerce_update_order_status",
            "description": "Update the status of a WooCommerce order (e.g., processing, completed, cancelled).",
            "tool_type": "action",
            "method": "PUT",
            "url_template": "native://woocommerce/orders/{order_id}/status",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "WooCommerce order ID"},
                    "status": {
                        "type": "string",
                        "description": "New order status: pending, processing, on-hold, completed, cancelled, refunded, failed",
                    },
                },
                "required": ["order_id", "status"],
            },
            "require_confirmation": True,
            "enabled": True,
        },
        {
            "name": "woocommerce_get_customer",
            "description": "Get a WooCommerce customer by email. Returns customer details.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://woocommerce/customers",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
    ],
    "stripe": [
        {
            "name": "stripe_get_subscription",
            "description": "Get the active Stripe subscription for a customer by email. Returns plan name, status, and period end date.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://stripe/subscription",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "stripe_get_next_invoice",
            "description": "Get the upcoming Stripe invoice for a customer by email. Returns amount due, currency, and next payment date.",
            "tool_type": "lookup",
            "method": "GET",
            "url_template": "native://stripe/invoice/upcoming",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Customer email address"}
                },
                "required": ["email"],
            },
            "require_confirmation": False,
            "enabled": True,
        },
        {
            "name": "stripe_cancel_subscription",
            "description": "Cancel a Stripe subscription at the end of the current billing period. Requires subscription ID.",
            "tool_type": "action",
            "method": "POST",
            "url_template": "native://stripe/subscription/{subscription_id}/cancel",
            "headers": {},
            "body_template": {},
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string", "description": "Stripe subscription ID"}
                },
                "required": ["subscription_id"],
            },
            "require_confirmation": True,
            "enabled": True,
        },
    ],
}


def provision_tools(db: Session, tenant_id: uuid.UUID, provider: str) -> list[AgentTool]:
    """Create AgentTool rows for the given provider. Rolls back on failure.

    All created tools are enabled.
    """
    if provider not in TOOL_SPECS:
        raise ValueError(f"Unknown provider: {provider}")

    tools: list[AgentTool] = []
    try:
        for spec in TOOL_SPECS[provider]:
            tool = AgentTool(
                tenant_id=tenant_id,
                **spec,
            )
            db.add(tool)
            tools.append(tool)
        db.flush()
    except Exception:
        for tool in tools:
            db.expunge(tool)
        db.rollback()
        raise

    return tools


def deprovision_tools(db: Session, tenant_id: uuid.UUID, provider: str) -> None:
    """Delete all AgentTool rows for the given provider under the given tenant."""
    tool_names = [spec["name"] for spec in TOOL_SPECS.get(provider, [])]
    if not tool_names:
        return

    db.query(AgentTool).filter(
        AgentTool.tenant_id == tenant_id,
        AgentTool.name.in_(tool_names),
    ).delete(synchronize_session="fetch")
    db.flush()
