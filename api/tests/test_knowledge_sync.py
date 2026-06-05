"""Tests for CRM sync endpoints POST /knowledge/sync/crm and GET /knowledge/sync/crm/status."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.get_billable_items.return_value = [
        {"id": 1, "name": "Consult", "price": 15000},
        {"id": 2, "name": "XRay", "price": 20000},
    ]
    adapter.get_appointment_types.return_value = [
        {"id": 10, "description": "Checkup", "duration_in_minutes": 30},
    ]
    adapter.get_appointment_type_billable_items.return_value = [
        {"billable_item_id": {"id": 1}, "appointment_type_id": {"id": 10}},
    ]
    adapter.get_practitioners.return_value = [
        {"id": "p1", "display_name": "Dr. Smith"},
    ]
    adapter.get_businesses.return_value = [
        {"id": "b1", "business_name": "Test Clinic"},
    ]
    return adapter


@pytest.fixture
def client_with_adapter(client: TestClient, mock_adapter):
    _index_clinic = MagicMock(side_effect=lambda tid, clinic, bid: 1 if clinic else 0)
    patches = [
        patch("app.knowledge.sync.get_crm_adapter_for_tenant", return_value=mock_adapter),
        patch("app.knowledge.sync.crm_indexer.index_services", return_value=2),
        patch("app.knowledge.sync.crm_indexer.index_practitioners", return_value=1),
        patch("app.knowledge.sync.crm_indexer.index_clinic", _index_clinic),
    ]
    for p in patches:
        p.start()
    yield client
    for p in patches:
        p.stop()


class TestSyncCrmGetStatus:
    def test_returns_status_structure(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "last_sync_at" in data
        assert "crm_provider" in data
        assert "services" in data
        assert "practitioners" in data
        assert "clinic" in data

    def test_returns_defaults_when_no_sync(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/status")
        data = resp.json()
        assert data["services"]["count"] == 0
        assert data["practitioners"]["last_sync"] is None


class TestSyncCrmPost:
    def test_sync_all_types(self, client_with_adapter: TestClient, mock_adapter):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        assert "practitioners" in data
        assert "clinic" in data
        assert "batch_id" in data
        assert data["services"]["imported"] == 2
        assert data["practitioners"]["imported"] == 1
        assert data["clinic"]["imported"] == 1

    def test_sync_services_only(self, client_with_adapter: TestClient):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={"types": ["services"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        assert "practitioners" not in data
        assert "clinic" not in data
        assert data["services"]["imported"] == 2

    def test_sync_practitioners_only(self, client_with_adapter: TestClient, mock_adapter):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={"types": ["practitioners"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "practitioners" in data
        assert "services" not in data
        assert data["practitioners"]["imported"] == 1

    def test_sync_clinic_only(self, client_with_adapter: TestClient):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={"types": ["clinic"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "clinic" in data
        assert data["clinic"]["imported"] == 1

    def test_no_crm_returns_400(self, client: TestClient):
        with patch("app.knowledge.sync.get_crm_adapter_for_tenant", return_value=None):
            resp = client.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 400
        assert "No CRM adapter" in resp.json()["detail"]

    def test_sync_with_errors_handles_partial_failure(self, client_with_adapter: TestClient, mock_adapter):
        mock_adapter.get_billable_items.side_effect = Exception("Cliniko API error")
        resp = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["services"]["errors"]) > 0
        assert "Cliniko API error" in data["services"]["errors"][0]

    def test_empty_businesses_returns_zero_clinic(self, client_with_adapter: TestClient, mock_adapter):
        mock_adapter.get_businesses.return_value = []
        resp = client_with_adapter.post("/knowledge/sync/crm", json={})
        data = resp.json()
        assert data["clinic"]["imported"] == 0

    def test_sync_updates_last_sync_in_db(self, client_with_adapter: TestClient):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 200
        # Status should now have last_sync_at
        status_resp = client_with_adapter.get("/knowledge/sync/crm/status")
        data = status_resp.json()
        assert data["last_sync_at"] is not None


class TestSyncCrmEdgeCases:
    def test_empty_types_list(self, client_with_adapter: TestClient):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={"types": []})
        assert resp.status_code == 200
        data = resp.json()
        assert "services" not in data
        assert "practitioners" not in data
        assert "clinic" not in data
        assert "batch_id" in data

    def test_invalid_type_ignored(self, client_with_adapter: TestClient):
        resp = client_with_adapter.post("/knowledge/sync/crm", json={"types": ["invalid_type"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "services" not in data
        assert "invalid_type" not in data

    def test_duplicate_sync_does_not_error(self, client_with_adapter: TestClient):
        resp1 = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp1.status_code == 200
        resp2 = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp2.status_code == 200
