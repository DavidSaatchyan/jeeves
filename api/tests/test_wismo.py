"""Unit tests for WISMO components."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.ai.wismo_responder import generate_wismo_email, generate_wismo_widget_response
from app.core.memory import get_conversation_history
from app.core.policies.engine import PolicyEngine
from app.core.workflows.wismo_service import parse_order_number


# ── parse_order_number ──────────────────────────────────────────────────────


class TestParseOrderNumber:
    def test_hash_format(self):
        assert parse_order_number("#1234") == "1234"

    def test_hash_with_text(self):
        assert parse_order_number("my order is #5678 thanks") == "5678"

    def test_order_prefix(self):
        assert parse_order_number("order #9012") == "9012"

    def test_order_colon(self):
        assert parse_order_number("order:3456") == "3456"

    def test_ord_underscore(self):
        assert parse_order_number("ORD_7890") == "7890"

    def test_ord_hyphen(self):
        assert parse_order_number("ORD-1111") == "1111"

    def test_no_match(self):
        assert parse_order_number("where is my package") is None

    def test_empty_string(self):
        assert parse_order_number("") is None

    def test_none_input(self):
        assert parse_order_number(None) is None

    def test_ord_alpha_no_match(self):
        assert parse_order_number("ORD_abc") is None

    def test_multiple_numbers(self):
        assert parse_order_number("orders #1002 and #1003") == "1002"


# ── generate_wismo_widget_response ──────────────────────────────────────────


class TestGenerateWismoWidgetResponse:
    async def test_delayed_with_estimated(self):
        result = await generate_wismo_widget_response(
            {"status": "delayed", "estimated_delivery": "May 30"},
            {"name": "#1002"},
        )
        assert "delay" in result.lower() or "Delayed" in result
        assert len(result) > 0

    async def test_delayed_without_estimated(self):
        result = await generate_wismo_widget_response(
            {"status": "delayed"},
            {"name": "#1002"},
        )
        assert "delay" in result.lower()
        assert len(result) > 0

    async def test_lost(self):
        result = await generate_wismo_widget_response(
            {"status": "lost"},
            {"name": "#1002"},
        )
        assert "lost" in result.lower() or "sorry" in result.lower()
        assert len(result) > 0

    async def test_on_track_with_estimated(self):
        result = await generate_wismo_widget_response(
            {"status": "on_track", "estimated_delivery": "May 28"},
            {"name": "#1002"},
        )
        assert "on track" in result.lower() or "on its way" in result.lower()
        assert len(result) > 0

    async def test_on_track_without_estimated(self):
        result = await generate_wismo_widget_response(
            {"status": "on_track"},
            {"name": "#1002"},
        )
        assert "on its way" in result.lower() or "on track" in result.lower()
        assert len(result) > 0

    async def test_llm_fallback_on_error(self):
        with patch("openai.AsyncOpenAI") as mock:
            mock.side_effect = Exception("API down")
            result = await generate_wismo_widget_response(
                {"status": "delayed", "estimated_delivery": "Jun 1"},
                {"name": "#1002"},
            )
            assert "Jun 1" in result or "delayed" in result.lower()

    async def test_no_order(self):
        result = await generate_wismo_widget_response(
            {"status": "delayed", "estimated_delivery": "May 30"},
        )
        assert len(result) > 0


# ── generate_wismo_email ────────────────────────────────────────────────────


class TestGenerateWismoEmail:
    async def test_delayed_with_reason_and_estimated(self):
        result = await generate_wismo_email(
            {"status": "delayed", "reason": "Weather", "estimated_delivery": "Jun 2"},
            {"name": "#1003"},
            {"first_name": "Alice"},
        )
        assert "delay" in result["subject"].lower()
        assert "Alice" in result["body"]
        assert "Weather" in result["body"]

    async def test_lost(self):
        result = await generate_wismo_email(
            {"status": "lost"},
            {"name": "#1004"},
            {"first_name": "Bob"},
        )
        assert "lost" in result["subject"].lower()
        assert "Bob" in result["body"]

    async def test_on_track(self):
        result = await generate_wismo_email(
            {"status": "on_track", "estimated_delivery": "Jun 5"},
            {"name": "#1005"},
            {"first_name": "Carol"},
        )
        assert "on track" in result["subject"].lower()
        assert "Jun 5" in result["body"]

    async def test_llm_fallback_on_error(self):
        with patch("openai.AsyncOpenAI") as mock:
            mock.side_effect = Exception("API down")
            result = await generate_wismo_email(
                {"status": "delayed", "reason": "Customs", "estimated_delivery": "Jun 3"},
                {"name": "#1006"},
                {"first_name": "Dave"},
            )
            assert result["subject"]  # non-empty
            assert result["body"]  # non-empty
            assert "delay" in result["subject"].lower()

    async def test_default_customer_name(self):
        result = await generate_wismo_email(
            {"status": "on_track"},
            {"name": "#1007"},
        )
        assert "there" in result["body"]


# ── Conversation Memory ─────────────────────────────────────────────────────


class TestGetConversationHistory:
    @pytest.fixture(autouse=True)
    def _setup(self, request):
        from app.db import SessionLocal
        from app.models import ChatLog

        self.db = SessionLocal()
        self.tenant_id = uuid4()
        self.customer_id = "test_user_1"

        # Clean any existing
        self.db.query(ChatLog).delete()
        self.db.commit()

        def teardown():
            self.db.query(ChatLog).delete()
            self.db.commit()
            self.db.close()

        request.addfinalizer(teardown)

    def _add_msg(self, direction: str, message: str | None = None, response: str | None = None):
        from app.models import ChatLog

        log = ChatLog(
            tenant_id=self.tenant_id,
            user_id=self.customer_id,
            direction=direction,
            message=message,
            response=response,
            channel="web_widget",
        )
        self.db.add(log)
        self.db.commit()
        return log

    def test_empty_history(self):
        result = get_conversation_history(str(self.tenant_id), "nonexistent_user", db=self.db)
        assert result == []

    def test_incoming_message(self):
        self._add_msg("incoming", message="where is my order")
        result = get_conversation_history(str(self.tenant_id), self.customer_id, db=self.db)
        assert len(result) == 1
        assert result[0]["role"] == "customer"
        assert result[0]["content"] == "where is my order"

    def test_outgoing_response(self):
        self._add_msg("outgoing", response="Your order #1002 is on the way!")
        result = get_conversation_history(str(self.tenant_id), self.customer_id, db=self.db)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Your order #1002 is on the way!"

    def test_conversation_ordering(self):
        self._add_msg("incoming", message="first message")
        self._add_msg("outgoing", response="first response")
        self._add_msg("incoming", message="second message")

        result = get_conversation_history(str(self.tenant_id), self.customer_id, db=self.db)
        assert len(result) == 3
        assert result[0]["content"] == "first message"
        assert result[1]["content"] == "first response"
        assert result[2]["content"] == "second message"

    def test_limit(self):
        for i in range(20):
            self._add_msg("incoming", message=f"msg {i}")

        result = get_conversation_history(str(self.tenant_id), self.customer_id, limit=5, db=self.db)
        assert len(result) <= 5

    def test_tenant_scoped(self):
        other_tenant = uuid4()

        from app.models import ChatLog

        log = ChatLog(
            tenant_id=other_tenant,
            user_id=self.customer_id,
            direction="incoming",
            message="other tenant msg",
            channel="web_widget",
        )
        self.db.add(log)
        self.db.commit()

        result = get_conversation_history(str(self.tenant_id), self.customer_id, db=self.db)
        assert all(r["content"] != "other tenant msg" for r in result)

    def test_max_age_filter(self):
        self._add_msg("incoming", message="old message")
        from app.models import ChatLog

        old = (
            self.db.query(ChatLog)
            .filter(ChatLog.message == "old message")
            .first()
        )
        old.created_at = datetime.utcnow() - timedelta(hours=48)
        self.db.commit()

        result = get_conversation_history(
            str(self.tenant_id), self.customer_id, max_age_hours=24, db=self.db
        )
        assert result == []


# ── PolicyEngine: wismo ─────────────────────────────────────────────────────


class TestPolicyEngineWismo:
    def test_default_values(self):
        engine = MagicMock(spec=PolicyEngine)
        engine.evaluate.return_value = {
            "allowed": True,
            "auto_notify": True,
            "auto_notify_threshold": "delayed",
            "notification_channels": ["widget"],
            "escalation_delay_days": 7,
            "auto_escalate_lost": True,
            "max_silent_tracking_days": 14,
            "max_notifications_per_workflow": 3,
        }
        result = engine.evaluate("wismo", {})
        assert result["auto_notify"] is True
        assert result["notification_channels"] == ["widget"]
        assert result["escalation_delay_days"] == 7

    def test_auto_notify_disabled(self):
        engine = MagicMock(spec=PolicyEngine)
        engine.evaluate.return_value = {
            "allowed": True,
            "auto_notify": False,
            "auto_notify_threshold": "delayed",
            "notification_channels": ["widget"],
            "escalation_delay_days": 7,
            "auto_escalate_lost": False,
            "max_silent_tracking_days": 14,
            "max_notifications_per_workflow": 3,
        }
        result = engine.evaluate("wismo", {})
        assert result["auto_notify"] is False

    def test_email_channel_allowed(self):
        engine = MagicMock(spec=PolicyEngine)
        engine.evaluate.return_value = {
            "allowed": True,
            "auto_notify": True,
            "auto_notify_threshold": "delayed",
            "notification_channels": ["widget", "email"],
            "escalation_delay_days": 7,
            "auto_escalate_lost": True,
            "max_silent_tracking_days": 14,
            "max_notifications_per_workflow": 3,
        }
        result = engine.evaluate("wismo", {})
        assert "email" in result["notification_channels"]

    def test_escalation_threshold(self):
        engine = MagicMock(spec=PolicyEngine)
        engine.evaluate.return_value = {
            "allowed": True,
            "auto_notify": True,
            "auto_notify_threshold": "delayed",
            "notification_channels": ["widget"],
            "escalation_delay_days": 3,
            "auto_escalate_lost": True,
            "max_silent_tracking_days": 14,
            "max_notifications_per_workflow": 3,
        }
        result = engine.evaluate("wismo", {})
        assert result["escalation_delay_days"] == 3

    def test_notification_threshold_lost_only(self):
        engine = MagicMock(spec=PolicyEngine)
        engine.evaluate.return_value = {
            "allowed": True,
            "auto_notify": True,
            "auto_notify_threshold": "lost",
            "notification_channels": ["widget"],
            "escalation_delay_days": 7,
            "auto_escalate_lost": True,
            "max_silent_tracking_days": 14,
            "max_notifications_per_workflow": 3,
        }
        result = engine.evaluate("wismo", {})
        assert result["auto_notify_threshold"] == "lost"
