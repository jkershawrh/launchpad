from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.domain.enums import (
    CatalogCategory,
    SessionStatus,
    WorkshopSeatStatus,
    WorkshopStatus,
)
from app.domain.models import LabRequest, Workshop, WorkshopSeat
from app.services.provisioning import ProvisioningService


def test_reconcile_stops_before_mutation_when_lifecycle_fence_is_lost():
    service = SimpleNamespace(
        _sessions={},
        _workshops={},
        cleanup=MagicMock(),
    )

    from app.services.provisioning import LifecycleOwnershipLostError
    from app.services.resource_reconciliation import reconcile_resources

    with pytest.raises(LifecycleOwnershipLostError):
        reconcile_resources(
            service,
            delete_orphans=False,
            lifecycle_guard=lambda: False,
        )

    service.cleanup.assert_not_called()


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


def test_reconcile_deletes_only_managed_namespaces_without_active_session(
    lab_session, monkeypatch
):
    active = lab_session.model_copy(update={"status": SessionStatus.ACTIVE, "namespace": "launchpad-active"})
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {active.session_id: active}
    service.cleanup = MagicMock()
    service._scrub_credentials.side_effect = lambda session: session
    monkeypatch.setenv("LAUNCHPAD_CONTROL_PLANE_ID", "test-primary")

    with patch(
        "app.services.resource_reconciliation._database_available",
        return_value=True,
    ), patch(
        "app.services.resource_reconciliation._managed_namespaces",
        return_value=["launchpad-active", "launchpad-orphan"],
    ), patch("app.services.resource_reconciliation._namespace_exists", return_value=True):
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


def test_reconcile_fails_closed_without_control_plane_identity(
    lab_session, monkeypatch
):
    service = MagicMock(spec=ProvisioningService)
    service._sessions = {}
    service.cleanup = MagicMock()
    monkeypatch.delenv("LAUNCHPAD_CONTROL_PLANE_ID", raising=False)

    with (
        patch(
            "app.services.resource_reconciliation._database_available",
            return_value=True,
        ),
        patch(
            "app.services.resource_reconciliation._managed_namespaces"
        ) as namespaces,
    ):
        from app.services.resource_reconciliation import reconcile_resources

        report = reconcile_resources(service, delete_orphans=True)

    namespaces.assert_not_called()
    service.cleanup.cleanup.assert_not_called()
    assert report["errors"] == [
        "control-plane identity unavailable — orphan deletion skipped"
    ]


def test_managed_namespace_query_is_scoped_to_control_plane_identity():
    core = MagicMock()
    core.list_namespace.return_value.items = []

    from app.services.resource_reconciliation import _managed_namespaces

    assert _managed_namespaces(core, control_plane_id="arena-primary") == []
    core.list_namespace.assert_called_once_with(
        label_selector=(
            "app.kubernetes.io/managed-by=launchpad,"
            "launchpad.redhat.com/control-plane-id=arena-primary"
        )
    )


def test_reconcile_reclaims_active_session_owned_by_completed_workshop(
    lab_session, monkeypatch
):
    workshop = Workshop(
        workshop_id="completed-workshop",
        tenant_id=lab_session.tenant_id,
        catalog_item_id=lab_session.catalog_item_id,
        num_users=1,
        status=WorkshopStatus.COMPLETED,
    )
    request = LabRequest(
        request_id=lab_session.request_id,
        tenant_id=lab_session.tenant_id,
        requester_id="seat-1",
        catalog_item_id=lab_session.catalog_item_id,
        requested_mode=CatalogCategory.QUICK_START,
        metadata={"workshop_id": workshop.workshop_id, "seat_id": "seat-1"},
    )
    late = lab_session.model_copy(
        update={"status": SessionStatus.PROVISIONING, "cluster_ref": "arena"}
    )
    service = SimpleNamespace(
        _sessions={late.session_id: late},
        _requests={request.request_id: request},
        _workshops={workshop.workshop_id: workshop},
        cleanup=MagicMock(),
        _scrub_credentials=lambda session: session,
        _save_session=MagicMock(),
        _reclaim_workshop_session=MagicMock(return_value=None),
    )

    from app.services.resource_reconciliation import reconcile_resources
    monkeypatch.setenv("LAUNCHPAD_CONTROL_PLANE_ID", "test-primary")

    with (
        patch(
            "app.services.resource_reconciliation._database_available",
            return_value=True,
        ),
        patch(
            "app.services.resource_reconciliation._managed_namespaces",
            return_value=[],
        ),
    ):
        report = reconcile_resources(service, delete_orphans=True)

    service._reclaim_workshop_session.assert_called_once_with(late.session_id)
    assert report["late_workshop_sessions_reclaimed"] == [
        {
            "workshop_id": workshop.workshop_id,
            "session_id": late.session_id,
            "cluster_id": "arena",
            "namespace": late.namespace,
        }
    ]
    assert report["errors"] == []


def test_reconcile_completes_nonterminal_workshop_when_every_session_is_reclaimed(
    lab_session,
):
    workshop_id = "stale-ready-workshop"
    reclaimed = lab_session.model_copy(
        update={
            "status": SessionStatus.RECLAIMED,
            "maas_api_key": None,
            "resources": {},
        }
    )
    workshop = Workshop(
        workshop_id=workshop_id,
        tenant_id=reclaimed.tenant_id,
        catalog_item_id=reclaimed.catalog_item_id,
        num_users=1,
        status=WorkshopStatus.READY,
        session_ids=[reclaimed.session_id],
        seats=[
            WorkshopSeat(
                workshop_id=workshop_id,
                seat_number=1,
                status="ready",
                session_id=reclaimed.session_id,
            )
        ],
    )
    access = MagicMock()
    service = SimpleNamespace(
        _sessions={reclaimed.session_id: reclaimed},
        _workshops={workshop_id: workshop},
        cleanup=None,
        public_access_service=access,
        _save_session=MagicMock(),
        _save_workshop=MagicMock(),
    )

    from app.services.resource_reconciliation import reconcile_resources

    report = reconcile_resources(service, delete_orphans=False)

    saved = service._save_workshop.call_args.args[0]
    assert saved.status == WorkshopStatus.COMPLETED
    assert saved.completed_at is not None
    assert saved.seats[0].status.value == "reclaimed"
    assert report["workshops_reconciled"] == [
        {
            "workshop_id": workshop_id,
            "cluster_id": None,
            "session_count": 1,
        }
    ]
    access.expire_order.assert_called_once_with(workshop_id)


def test_reconcile_does_not_complete_workshop_with_an_active_session(lab_session):
    workshop_id = "still-active-workshop"
    workshop = Workshop(
        workshop_id=workshop_id,
        tenant_id=lab_session.tenant_id,
        catalog_item_id=lab_session.catalog_item_id,
        num_users=1,
        status=WorkshopStatus.READY,
        session_ids=[lab_session.session_id],
        seats=[
            WorkshopSeat(
                workshop_id=workshop_id,
                seat_number=1,
                status="ready",
                session_id=lab_session.session_id,
            )
        ],
    )
    service = SimpleNamespace(
        _sessions={lab_session.session_id: lab_session},
        _workshops={workshop_id: workshop},
        cleanup=None,
        _save_session=MagicMock(),
        _save_workshop=MagicMock(),
    )

    from app.services.resource_reconciliation import reconcile_resources

    report = reconcile_resources(service, delete_orphans=False)

    service._save_workshop.assert_not_called()
    assert report["workshops_reconciled"] == []


def test_reconcile_marks_partially_reclaimed_legacy_workshop_reclaiming(
    lab_session,
):
    workshop_id = "legacy-partial-ttl-workshop"
    reclaimed = lab_session.model_copy(
        update={
            "session_id": "reclaimed-seat-session",
            "status": SessionStatus.RECLAIMED,
            "maas_api_key": None,
            "resources": {},
        }
    )
    active = lab_session.model_copy(
        update={"session_id": "active-seat-session", "status": SessionStatus.READY}
    )
    workshop = Workshop(
        workshop_id=workshop_id,
        tenant_id=lab_session.tenant_id,
        catalog_item_id=lab_session.catalog_item_id,
        num_users=2,
        status=WorkshopStatus.READY,
        session_ids=[reclaimed.session_id, active.session_id],
        seats=[
            WorkshopSeat(
                workshop_id=workshop_id,
                seat_number=1,
                status=WorkshopSeatStatus.READY,
                session_id=reclaimed.session_id,
            ),
            WorkshopSeat(
                workshop_id=workshop_id,
                seat_number=2,
                status=WorkshopSeatStatus.READY,
                session_id=active.session_id,
            ),
        ],
    )
    access = MagicMock()
    service = SimpleNamespace(
        _sessions={reclaimed.session_id: reclaimed, active.session_id: active},
        _workshops={workshop_id: workshop},
        cleanup=None,
        public_access_service=access,
        _save_session=MagicMock(),
        _save_workshop=MagicMock(),
    )

    from app.services.resource_reconciliation import reconcile_resources

    report = reconcile_resources(service, delete_orphans=False)

    saved = service._save_workshop.call_args.args[0]
    assert saved.status == WorkshopStatus.RECLAIMING
    assert saved.seats[0].status == WorkshopSeatStatus.RECLAIMED
    assert saved.seats[1].status == WorkshopSeatStatus.READY
    assert report["workshops_reclaiming"] == [
        {
            "workshop_id": workshop_id,
            "cluster_id": None,
            "session_count": 2,
        }
    ]
    access.expire_order.assert_called_once_with(workshop_id)


def test_reconcile_normalizes_unstarted_seat_in_completed_workshop():
    workshop_id = "terminal-seat-repair"
    workshop = Workshop(
        workshop_id=workshop_id,
        tenant_id="terminal-seat-repair",
        catalog_item_id="inference-overdrive-quickstart",
        num_users=1,
        status=WorkshopStatus.COMPLETED,
        seats=[
            WorkshopSeat(
                workshop_id=workshop_id,
                seat_number=1,
                status=WorkshopSeatStatus.PENDING,
            )
        ],
    )
    access = MagicMock()
    service = SimpleNamespace(
        _sessions={},
        _workshops={workshop_id: workshop},
        cleanup=None,
        public_access_service=access,
        _save_session=MagicMock(),
        _save_workshop=MagicMock(),
    )

    from app.services.resource_reconciliation import reconcile_resources

    report = reconcile_resources(service, delete_orphans=False)

    saved = service._save_workshop.call_args.args[0]
    assert saved.status == WorkshopStatus.COMPLETED
    assert saved.seats[0].status == WorkshopSeatStatus.RECLAIMED
    assert report["workshops_reconciled"] == [
        {
            "workshop_id": workshop_id,
            "cluster_id": None,
            "session_count": 0,
        }
    ]
    access.expire_order.assert_called_once_with(workshop_id)
