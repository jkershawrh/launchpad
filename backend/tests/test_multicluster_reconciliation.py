from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.domain.clusters import ClusterTarget
from app.domain.enums import SessionStatus
from app.domain.models import LabSession
from app.services.cluster_registry import ClusterRegistry
from app.services.resource_reconciliation import reconcile_resources


def test_inflight_namespace_label_prevents_remote_orphan_deletion():
    session = LabSession(
        request_id="request-123",
        tenant_id="tenant",
        catalog_item_id="operators",
        cluster_ref="arena",
        status=SessionStatus.PROVISIONING,
        namespace="initial-plan-namespace",
    )
    core = MagicMock()
    core.read_namespace.return_value = SimpleNamespace(
        metadata=SimpleNamespace(
            labels={"launchpad.redhat.com/session-id": "request-123"},
            creation_timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    cleanup = MagicMock()
    service = SimpleNamespace(
        _sessions={session.session_id: session},
        cluster_registry=ClusterRegistry([ClusterTarget(
            cluster_id="arena",
            display_name="Arena",
            ingress_domain="apps.arena.example.com",
            credential_secret="launchpad/arena",
        )]),
        cluster_client_factory=object(),
        cleanup=cleanup,
        _target_clients=lambda cluster_id: SimpleNamespace(core=core),
        _get_cleanup=lambda cluster_id: cleanup,
    )
    with patch(
        "app.services.resource_reconciliation._managed_namespaces",
        return_value=["actual-demo-namespace"],
    ):
        report = reconcile_resources(service)
    cleanup.cleanup.assert_not_called()
    assert report["orphan_namespaces_deleted"] == []


def test_recent_namespace_is_not_deleted_with_stale_session_snapshot():
    core = MagicMock()
    core.read_namespace.return_value = SimpleNamespace(
        metadata=SimpleNamespace(
            labels={"launchpad.redhat.com/session-id": "new-request"},
            creation_timestamp=datetime.now(timezone.utc),
        )
    )
    cleanup = MagicMock()
    service = SimpleNamespace(
        _sessions={},
        cluster_registry=ClusterRegistry([ClusterTarget(
            cluster_id="oberon",
            display_name="Oberon",
            ingress_domain="apps.oberon.example.com",
            local=True,
        )]),
        cluster_client_factory=object(),
        cleanup=cleanup,
        _target_clients=lambda cluster_id: SimpleNamespace(core=core),
        _get_cleanup=lambda cluster_id: cleanup,
    )
    with patch(
        "app.services.resource_reconciliation._managed_namespaces",
        return_value=["new-workshop-namespace"],
    ):
        report = reconcile_resources(service)
    cleanup.cleanup.assert_not_called()
    assert report["orphan_namespaces_deleted"] == []
