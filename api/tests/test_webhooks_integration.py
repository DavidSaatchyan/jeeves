from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy.orm import Session

from app.integrations.webhooks import _process_webhook


@pytest.mark.asyncio
async def test_process_webhook_delegates_verify_to_adapter():
    tenant_id = str(uuid4())
    payload = json.dumps({"event": "appointment.created", "data": {"id": "a1"}})

    mock_request = MagicMock(spec=Request)
    mock_request.body.return_value = payload.encode()
    mock_request.headers = {"X-Webhook-Signature": "somesig"}

    mock_db = MagicMock(spec=Session)
    mock_tenant = MagicMock()
    mock_tenant.id = uuid4()
    mock_db.get.return_value = mock_tenant
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=uuid4())

    mock_adapter = MagicMock()
    mock_adapter.verify_webhook_signature.return_value = True
    mock_adapter.parse_webhook_event.return_value = {
        "event": "appointment.created",
        "resource": {"id": "a1", "patient_id": "p_ext"},
    }

    with patch("app.integrations.webhooks.get_crm_adapter_for_tenant", return_value=mock_adapter):
        with patch("app.integrations.webhooks._sync_appointment", return_value=MagicMock(id="cached_id")):
            with patch("app.integrations.webhooks._log_audit"):
                result = await _process_webhook(tenant_id, mock_request, mock_db, "pabau", ["X-Webhook-Signature"])

    mock_adapter.verify_webhook_signature.assert_called_once_with(payload.encode(), "somesig")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_process_webhook_rejects_invalid_signature():
    tenant_id = str(uuid4())
    payload = json.dumps({"event": "test"})

    mock_request = MagicMock(spec=Request)
    mock_request.body.return_value = payload.encode()
    mock_request.headers = {"X-Webhook-Signature": "badsig"}

    mock_db = MagicMock(spec=Session)
    mock_tenant = MagicMock()
    mock_tenant.id = uuid4()
    mock_db.get.return_value = mock_tenant

    mock_adapter = MagicMock()
    mock_adapter.verify_webhook_signature.return_value = False

    with patch("app.integrations.webhooks.get_crm_adapter_for_tenant", return_value=mock_adapter):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _process_webhook(tenant_id, mock_request, mock_db, "pabau", ["X-Webhook-Signature"])
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_process_webhook_tries_multiple_sig_headers():
    tenant_id = str(uuid4())
    payload = json.dumps({"event": "test"})

    mock_request = MagicMock(spec=Request)
    mock_request.body.return_value = payload.encode()
    mock_request.headers = {"X-Fallback": "fallsig", "X-Primary": "prisig"}

    mock_db = MagicMock(spec=Session)
    mock_tenant = MagicMock()
    mock_tenant.id = uuid4()
    mock_db.get.return_value = mock_tenant

    mock_adapter = MagicMock()
    mock_adapter.verify_webhook_signature.return_value = True
    mock_adapter.parse_webhook_event.return_value = {"event": "unknown", "resource": {}}

    with patch("app.integrations.webhooks.get_crm_adapter_for_tenant", return_value=mock_adapter):
        await _process_webhook(tenant_id, mock_request, mock_db, "pabau", ["X-Primary", "X-Fallback"])

    mock_adapter.verify_webhook_signature.assert_called_once_with(payload.encode(), "prisig")
