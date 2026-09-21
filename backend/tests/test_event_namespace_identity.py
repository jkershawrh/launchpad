from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.adapters.openshift.sandbox_provisioning import OpenShiftSandboxProvisioner
from app.domain.enums import CatalogCategory, CatalogStatus, LabRequestStatus
from app.domain.models import CatalogItem, LabRequest, Workshop, WorkshopSeat
from app.services.provisioning import ProvisioningService


@pytest.fixture
def event_request():
    return LabRequest(
        tenant_id="event-tenant",
        requester_id="participant-1",
        catalog_item_id="event-lab",
        requested_mode=CatalogCategory.GUIDED_BUILD,
        metadata={
            "event_reservation_id": "reservation-1",
            "workshop_id": "workshop-1",
            "seat_id": "seat-1",
            "target_cluster": "arena",
        },
    )


def _item(*, sandbox=False):
    return CatalogItem(
        catalog_item_id="event-lab",
        display_name="Event Lab",
        category=CatalogCategory.OPEN_SANDBOX if sandbox else CatalogCategory.GUIDED_BUILD,
        status=CatalogStatus.ACTIVE,
        metadata={"operator_workshop": True},
    )


def _namespace_labels(adapter, plan):
    class StopBeforeMutation(Exception):
        pass

    with (
        patch.object(adapter, "_create_namespace", side_effect=StopBeforeMutation) as create,
        pytest.raises(StopBeforeMutation),
    ):
        adapter.provision(plan)
    return (
        create.call_args.args[1]
        if len(create.call_args.args) > 1
        else create.call_args.kwargs["extra_labels"]
    )


@pytest.mark.parametrize("sandbox", [False, True])
def test_event_seat_identity_reaches_namespace_create(event_request, sandbox):
    adapter_type = OpenShiftSandboxProvisioner if sandbox else OpenShiftProvisioningAdapter
    adapter = object.__new__(adapter_type)
    adapter._target = SimpleNamespace(
        cluster_id="arena",
        storage_class="nfs-storage",
        ingress_domain="apps.arena.test",
        console_url="https://console.arena.test",
    )
    if not sandbox:
        adapter._overlay_path = "/tmp/demo"
    plan = adapter.create_plan(event_request, _item(sandbox=sandbox))
    labels = _namespace_labels(adapter, plan)
    assert labels["launchpad.redhat.com/event-reservation-id"] == "reservation-1"
    assert labels["launchpad.redhat.com/workshop-id"] == "workshop-1"
    assert labels["launchpad.redhat.com/seat-id"] == "seat-1"


@pytest.mark.parametrize("sandbox", [False, True])
def test_non_event_request_never_gains_event_reservation_label(event_request, sandbox):
    adapter_type = OpenShiftSandboxProvisioner if sandbox else OpenShiftProvisioningAdapter
    adapter = object.__new__(adapter_type)
    adapter._target = SimpleNamespace(
        cluster_id="arena",
        storage_class="nfs-storage",
        ingress_domain="apps.arena.test",
        console_url="https://console.arena.test",
    )
    if not sandbox:
        adapter._overlay_path = "/tmp/demo"
    request = event_request.model_copy(
        update={"metadata": {"workshop_id": "ordinary-1", "seat_id": "seat-1"}}
    )
    plan = adapter.create_plan(request, _item(sandbox=sandbox))
    labels = _namespace_labels(adapter, plan)
    assert "launchpad.redhat.com/event-reservation-id" not in labels


@pytest.mark.parametrize("sandbox", [False, True])
def test_event_seat_plan_requires_complete_identity(event_request, sandbox):
    adapter_type = OpenShiftSandboxProvisioner if sandbox else OpenShiftProvisioningAdapter
    adapter = object.__new__(adapter_type)
    if not sandbox:
        adapter._overlay_path = "/tmp/demo"
    request = event_request.model_copy(
        update={"metadata": {"event_reservation_id": "reservation-1"}}
    )
    with pytest.raises(ValueError, match="event namespace identity"):
        adapter.create_plan(request, _item(sandbox=sandbox))


@pytest.mark.parametrize("reservation_id", ["reservation-1", None])
def test_workshop_seat_request_carries_reservation_only_for_event(reservation_id):
    workshop = Workshop(
        workshop_id="workshop-1",
        tenant_id="event-tenant",
        catalog_item_id="event-lab",
        num_users=1,
        cluster_ref="arena",
        seats=[
            WorkshopSeat(
                workshop_id="workshop-1",
                seat_id="seat-1",
                seat_number=1,
                participant_id="participant-1",
            )
        ],
        metadata={"event_reservation_id": reservation_id} if reservation_id else {},
    )
    service = ProvisioningService()
    submitted = []

    def reject(request):
        submitted.append(request)
        return request.model_copy(update={"status": LabRequestStatus.REJECTED})

    with patch.object(service, "submit_request", side_effect=reject):
        service._provision_workshop_seat(workshop, 0)

    assert submitted[0].metadata.get("event_reservation_id") == reservation_id
    assert submitted[0].metadata["workshop_id"] == "workshop-1"
    assert submitted[0].metadata["seat_id"] == "seat-1"
