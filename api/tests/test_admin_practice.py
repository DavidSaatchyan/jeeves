from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app as _app
from app.models import Tenant


@pytest.fixture
def mock_admin_tenant() -> Tenant:
    t = MagicMock(spec=Tenant)
    t.id = uuid4()
    t.email = "admin@test.com"
    t.name = "Test Clinic"
    return t


@pytest.fixture
def client(mock_admin_tenant: Tenant) -> TestClient:
    def _override():
        return mock_admin_tenant

    _app.dependency_overrides.clear()
    from app.admin.deps import get_admin_tenant

    _app.dependency_overrides[get_admin_tenant] = _override
    with TestClient(_app) as c:
        yield c
    _app.dependency_overrides.clear()


class TestPracticePage:
    def test_returns_200_with_html(self, client: TestClient) -> None:
        resp = client.get("/admin/practice")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    def test_contains_practice_data_title(self, client: TestClient) -> None:
        resp = client.get("/admin/practice")
        assert resp.status_code == 200
        assert "Practice data" in resp.text

    def test_contains_sync_buttons(self, client: TestClient) -> None:
        resp = client.get("/admin/practice")
        assert resp.status_code == 200
        assert "Sync all data" in resp.text
        assert "pmsSyncAllBtn" in resp.text
        for t in ("services", "practitioners", "clinic"):
            assert f"pmsBtn-{t}" in resp.text

    def test_knowledge_page_has_redirect_link(self, client: TestClient) -> None:
        resp = client.get("/admin/knowledge")
        assert resp.status_code == 200
        assert "/admin/practice" in resp.text
        assert "Practice data" in resp.text

    def test_no_crm_tab_in_upload_modal(self, client: TestClient) -> None:
        resp = client.get("/admin/knowledge")
        assert resp.status_code == 200
        assert 'data-utab="crm"' not in resp.text
        assert "Sync from CRM" not in resp.text

    def test_no_crm_badge_in_toolbar(self, client: TestClient) -> None:
        resp = client.get("/admin/knowledge")
        assert resp.status_code == 200
        assert 'id="crmBadge"' not in resp.text
