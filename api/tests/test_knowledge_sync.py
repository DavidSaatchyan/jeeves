"""Tests for CRM sync endpoints POST /knowledge/sync/crm and GET /knowledge/sync/crm/status."""
from __future__ import annotations

from typing import Generator
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


from app.auth.deps import get_current_tenant
from app.models import Tenant

@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.provider = "cliniko"
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
    adapter.fetch_services.return_value = [
        {"id": 1, "name": "Consult", "item_type": "Service", "price": 15000, "description": "Checkup", "duration_in_minutes": 30},
        {"id": 2, "name": "XRay", "item_type": "Service", "price": 20000},
    ]
    adapter.fetch_practitioners.return_value = [
        {"id": "p1", "display_name": "Dr. Smith", "first_name": "Dr.", "last_name": "Smith"},
    ]
    adapter.fetch_clinics.return_value = [
        {"id": "b1", "business_name": "Test Clinic", "name": "Test Clinic"},
    ]
    return adapter


@pytest.fixture
def client_with_adapter(client: TestClient, mock_adapter):
    _index_clinic = MagicMock(side_effect=lambda tid, clinic, bid: 1 if clinic else 0)
    patches = [
        patch("app.knowledge.sync.get_hms_adapter_for_tenant", return_value=mock_adapter),
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
        with patch("app.knowledge.sync.get_hms_adapter_for_tenant", return_value=None):
            resp = client.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 400
        assert "No CRM" in resp.json()["detail"]

    def test_sync_with_errors_handles_partial_failure(self, client_with_adapter: TestClient, mock_adapter):
        mock_adapter.fetch_services.side_effect = Exception("Cliniko API error")
        resp = client_with_adapter.post("/knowledge/sync/crm", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["services"]["errors"]) > 0
        assert "Cliniko API error" in data["services"]["errors"][0]

    def test_empty_businesses_returns_zero_clinic(self, client_with_adapter: TestClient, mock_adapter):
        mock_adapter.fetch_clinics.return_value = []
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


@pytest.fixture
def seeded_tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def seeded_client(app: FastAPI, seeded_tenant_id: UUID) -> Generator[TestClient, None, None]:
    from sqlalchemy import delete as sa_delete

    from app.db import SessionLocal
    from app.models import HmsClinic, HmsPractitioner, HmsService

    db = SessionLocal()
    try:
        svc1 = HmsService(
            tenant_id=seeded_tenant_id, external_id="s1", name="Consultation",
            description="Initial consult", price_cents=15000, duration_minutes=30,
        )
        svc2 = HmsService(
            tenant_id=seeded_tenant_id, external_id="s2", name="X-Ray",
            description="Digital X-Ray", price_cents=20000, duration_minutes=15,
        )
        prac1 = HmsPractitioner(
            tenant_id=seeded_tenant_id, external_id="p1", display_name="Dr. Smith",
            title="Dentist", description="General dentist",
        )
        clinic1 = HmsClinic(
            tenant_id=seeded_tenant_id, external_id="c1", business_name="Test Clinic",
            address="123 Main St", city="Springfield", state="IL", postcode="62701",
            country="US", phone="555-0100", email="clinic@example.com", website="https://example.com",
        )
        db.add_all([svc1, svc2, prac1, clinic1])
        db.commit()
    finally:
        db.close()

    def _override_tenant():
        t = Tenant(id=seeded_tenant_id, name="seeded", email="seeded@example.com")
        return t

    app.dependency_overrides[get_current_tenant] = _override_tenant

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()

    db = SessionLocal()
    try:
        db.execute(sa_delete(HmsService).where(HmsService.tenant_id == seeded_tenant_id))
        db.execute(sa_delete(HmsPractitioner).where(HmsPractitioner.tenant_id == seeded_tenant_id))
        db.execute(sa_delete(HmsClinic).where(HmsClinic.tenant_id == seeded_tenant_id))
        db.commit()
    finally:
        db.close()


class TestPreviewCrmType:
    """Tests for GET /knowledge/sync/crm/{type} preview endpoint."""

    def test_returns_services(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {r["name"] for r in data}
        assert "Consultation" in names
        assert "X-Ray" in names
        assert all("updated_at" in r for r in data)

    def test_returns_practitioners(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/practitioners")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["display_name"] == "Dr. Smith"
        assert data[0]["title"] == "Dentist"

    def test_returns_clinic(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/clinic")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["business_name"] == "Test Clinic"
        assert data[0]["email"] == "clinic@example.com"

    def test_unknown_type_returns_404(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/unknown_type")
        assert resp.status_code == 404
        assert "Unknown type" in resp.json()["detail"]

    def test_empty_list_when_no_data(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/services")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCrmCounts:
    """Tests for GET /knowledge/sync/crm/counts."""

    def test_returns_zero_when_no_data(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/counts")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"services": 0, "practitioners": 0, "clinic": 0}

    def test_returns_counts_from_seeded_data(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/counts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["services"] == 2
        assert data["practitioners"] == 1
        assert data["clinic"] == 1

    def test_has_correct_keys(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/counts")
        assert set(resp.json().keys()) == {"services", "practitioners", "clinic"}


class TestCrmTable:
    """Tests for GET /knowledge/sync/crm/{type}/table."""

    def test_returns_paginated_services(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["per_page"] == 50
        assert len(data["rows"]) == 2

    def test_respects_per_page(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?per_page=1")
        data = resp.json()
        assert len(data["rows"]) == 1
        assert data["total"] == 2
        assert data["page"] == 1

    def test_page_2_returns_remaining(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?per_page=1&page=2")
        data = resp.json()
        assert len(data["rows"]) == 1
        assert data["page"] == 2

    def test_sort_by_name_desc(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?sort=name&order=desc")
        data = resp.json()
        names = [r["name"] for r in data["rows"]]
        assert names == sorted(names, reverse=True)

    def test_sort_by_name_asc(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?sort=name&order=asc")
        data = resp.json()
        names = [r["name"] for r in data["rows"]]
        assert names == sorted(names)

    def test_search_filters_rows(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?search=Consult")
        data = resp.json()
        assert data["total"] == 1
        assert data["rows"][0]["name"] == "Consultation"

    def test_search_empty_returns_no_results(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/services/table?search=NoMatchXYZ")
        data = resp.json()
        assert data["total"] == 0
        assert data["rows"] == []

    def test_unknown_type_returns_404(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/unknown/table")
        assert resp.status_code == 404

    def test_returns_practitioners_table(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/practitioners/table")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_returns_clinic_table(self, seeded_client: TestClient):
        resp = seeded_client.get("/knowledge/sync/crm/clinic/table")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_empty_when_no_data(self, client: TestClient):
        resp = client.get("/knowledge/sync/crm/services/table")
        data = resp.json()
        assert data["total"] == 0
        assert data["rows"] == []
