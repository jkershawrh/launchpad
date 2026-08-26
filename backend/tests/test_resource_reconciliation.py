from unittest.mock import MagicMock, patch

from app.domain.enums import SessionStatus
from app.services.provisioning import ProvisioningService


def test_reconcile_marks_cleanup_failed_reclaimed_when_namespace_is_gone(lab_session):
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {lab_session.session_id: lab_session.model_copy(update={"status": SessionStatus.CLEANUP_FAILED})}
    service._save_session = MagicMock()
    service._scrub_credentials.side_effect = lambda session: session
    service.cleanup = MagicMock()
    service._scrub_credentials.side_effect = lambda session: session

    with patch("app.services.resource_reconciliation._namespace_exists", return_value=False):
        from app.services.resource_reconciliation import reconcile_resources
        report = reconcile_resources(service, delete_orphans=False)

    assert report["sessions_reconciled"] == 1
    service._save_session.assert_called_once()
    assert service._save_session.call_args.args[0].status == SessionStatus.RECLAIMED


def test_reconcile_deletes_only_managed_namespaces_without_active_session(lab_session):
    active = lab_session.model_copy(update={"status": SessionStatus.ACTIVE, "namespace": "launchpad-active"})
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {active.session_id: active}
    service.cleanup = MagicMock()
    service._scrub_credentials.side_effect = lambda session: session

    with patch("app.services.resource_reconciliation._managed_namespaces", return_value=["launchpad-active", "launchpad-orphan"]), \
         patch("app.services.resource_reconciliation._namespace_exists", return_value=True):
        from app.services.resource_reconciliation import reconcile_resources
        report = reconcile_resources(service, delete_orphans=True)

    service.cleanup.cleanup.assert_called_once_with("launchpad-orphan")
    assert report["orphan_namespaces_deleted"] == ["launchpad-orphan"]


def test_reconcile_never_deletes_namespace_referenced_by_terminal_session(lab_session):
    reclaimed = lab_session.model_copy(update={"status": SessionStatus.RECLAIMED, "namespace": "launchpad-reclaimed"})
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {reclaimed.session_id: reclaimed}
    service.cleanup = MagicMock()

    with patch("app.services.resource_reconciliation._managed_namespaces", return_value=["launchpad-reclaimed"]):
        from app.services.resource_reconciliation import reconcile_resources
        report = reconcile_resources(service, delete_orphans=True)

    service.cleanup.cleanup.assert_not_called()
    assert report["orphan_namespaces_deleted"] == []


def test_reconcile_fails_closed_when_database_is_unavailable(lab_session):
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {}
    service.cleanup = MagicMock()

    with patch("app.services.resource_reconciliation._database_available", return_value=False), \
         patch("app.services.resource_reconciliation._managed_namespaces") as namespaces:
        from app.services.resource_reconciliation import reconcile_resources
        report = reconcile_resources(service, delete_orphans=True)

    namespaces.assert_not_called()
    service.cleanup.cleanup.assert_not_called()
    assert report["errors"] == ["database unavailable — orphan deletion skipped"]
