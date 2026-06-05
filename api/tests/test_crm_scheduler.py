from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from app.models import Tenant


def _make_tenant(
    tenant_id: UUID | None = None,
    crm_config: dict | None = None,
    is_active: bool = True,
) -> Tenant:
    t = Tenant(
        id=tenant_id or uuid4(),
        name="test",
        email="test@example.com",
        is_active=is_active,
        crm_config=crm_config,
    )
    t.id = t.id
    return t


class TestPollAllTenants:
    """Tests for scheduler.poll_all_tenants()."""

    @patch("app.core.scheduler.SessionLocal")
    @patch("app.core.scheduler.get_crm_adapter_for_tenant")
    @patch("app.core.scheduler.poll_crm_changes")
    def test_happy_path(
        self,
        mock_poll: MagicMock,
        mock_get_adapter: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        t1 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        t2 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [t1, t2]
        mock_session_local.return_value = mock_session
        mock_get_adapter.return_value = MagicMock()
        mock_poll.return_value = {
            "services": {"imported": 3, "errors": []},
            "practitioners": {"imported": 2, "errors": []},
            "clinic": {"imported": 1, "errors": []},
        }

        from app.core.scheduler import poll_all_tenants

        poll_all_tenants()

        assert mock_poll.call_count == 2
        mock_poll.assert_any_call(t1.id)
        mock_poll.assert_any_call(t2.id)
        mock_session.close.assert_called_once()

    @patch("app.core.scheduler.SessionLocal")
    @patch("app.core.scheduler.get_crm_adapter_for_tenant")
    @patch("app.core.scheduler.poll_crm_changes")
    def test_skips_tenant_without_crm_config(
        self,
        mock_poll: MagicMock,
        mock_get_adapter: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        t1 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "pabau"})
        t2 = _make_tenant(tenant_id=uuid4(), crm_config=None)
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [t1, t2]
        mock_session_local.return_value = mock_session
        mock_get_adapter.return_value = MagicMock()

        from app.core.scheduler import poll_all_tenants

        poll_all_tenants()

        mock_poll.assert_called_once_with(t1.id)

    @patch("app.core.scheduler.SessionLocal")
    @patch("app.core.scheduler.get_crm_adapter_for_tenant")
    @patch("app.core.scheduler.poll_crm_changes")
    def test_skips_tenant_without_adapter(
        self,
        mock_poll: MagicMock,
        mock_get_adapter: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        t1 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        t2 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [t1, t2]
        mock_session_local.return_value = mock_session
        mock_get_adapter.side_effect = [MagicMock(), None]

        from app.core.scheduler import poll_all_tenants

        poll_all_tenants()

        mock_poll.assert_called_once_with(t1.id)

    @patch("app.core.scheduler.SessionLocal")
    @patch("app.core.scheduler.get_crm_adapter_for_tenant")
    @patch("app.core.scheduler.poll_crm_changes")
    def test_one_tenant_failure_does_not_block_others(
        self,
        mock_poll: MagicMock,
        mock_get_adapter: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        t1 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        t2 = _make_tenant(tenant_id=uuid4(), crm_config={"provider": "cliniko"})
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [t1, t2]
        mock_session_local.return_value = mock_session
        mock_get_adapter.return_value = MagicMock()
        mock_poll.side_effect = [Exception("API error"), {"services": {"imported": 1, "errors": []}, "practitioners": {"imported": 0, "errors": []}, "clinic": {"imported": 0, "errors": []}}]

        from app.core.scheduler import poll_all_tenants

        poll_all_tenants()

        assert mock_poll.call_count == 2
        mock_poll.assert_any_call(t1.id)
        mock_poll.assert_any_call(t2.id)

    @patch("app.core.scheduler.SessionLocal")
    @patch("app.core.scheduler.get_crm_adapter_for_tenant")
    @patch("app.core.scheduler.poll_crm_changes")
    def test_no_active_tenants(
        self,
        mock_poll: MagicMock,
        mock_get_adapter: MagicMock,
        mock_session_local: MagicMock,
    ) -> None:
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session_local.return_value = mock_session

        from app.core.scheduler import poll_all_tenants

        poll_all_tenants()

        mock_poll.assert_not_called()
        mock_get_adapter.assert_not_called()


class TestSetupScheduler:
    """Tests for scheduler.setup_scheduler()."""

    def test_does_nothing_when_worker_type_api(self) -> None:
        with patch.dict(os.environ, {"WORKER_TYPE": "api"}, clear=False):
            from app.core.scheduler import setup_scheduler

            result = setup_scheduler(interval_minutes=30)
            assert result is None

    def test_starts_when_worker_type_scheduler(self) -> None:
        with patch.dict(os.environ, {"WORKER_TYPE": "scheduler"}, clear=False):
            from app.core.scheduler import setup_scheduler, shutdown_scheduler

            try:
                scheduler = setup_scheduler(interval_minutes=30)
                assert scheduler is not None
                assert scheduler.running
            finally:
                shutdown_scheduler()

    def test_idempotent(self) -> None:
        with patch.dict(os.environ, {"WORKER_TYPE": "scheduler"}, clear=False):
            from app.core.scheduler import setup_scheduler, shutdown_scheduler

            try:
                s1 = setup_scheduler(interval_minutes=30)
                s2 = setup_scheduler(interval_minutes=30)
                assert s1 is s2
            finally:
                shutdown_scheduler()


class TestShutdownScheduler:
    """Tests for scheduler.shutdown_scheduler()."""

    def test_shutdown_gracefully(self) -> None:
        with patch.dict(os.environ, {"WORKER_TYPE": "scheduler"}, clear=False):
            from app.core.scheduler import setup_scheduler, shutdown_scheduler

            setup_scheduler(interval_minutes=30)
            shutdown_scheduler()

            from app.core.scheduler import _scheduler

            assert _scheduler is None

    def test_shutdown_idempotent(self) -> None:
        from app.core.scheduler import shutdown_scheduler

        shutdown_scheduler()
        shutdown_scheduler()
