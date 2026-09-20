from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.domain.access import ExposurePolicy
from app.domain.enums import CatalogCategory, CatalogStatus
from app.domain.models import CatalogItem
from app.services.event_reservations import EventReservationLedger
from app.services.provisioning import ProvisioningService

from backend.tests.test_event_reservation_ledger import NOW, _plan, _supply


def _catalog(*, version: str):
    item = CatalogItem(
        catalog_item_id="reserved-catalog",
        display_name="Serve LLMs",
        category=CatalogCategory.GUIDED_BUILD,
        version=version,
        status=CatalogStatus.ACTIVE,
        default_hardware_profile="xeon-basic",
        default_quota_profile="standard",
        metadata={
            "max_workshop_seats": 30,
            "allowed_exposure_policies": ["public_code", "internal"],
        },
    )
    return SimpleNamespace(
        get_item=lambda catalog_id: item.model_copy(
            update={"catalog_item_id": catalog_id}
        )
    )


def test_reserved_workshop_order_uses_exact_cluster_release_and_seats():
    supply = _supply()
    plan = _plan("event-a", supply)
    reservation = plan.reservations[0]
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    service = ProvisioningService(
        catalog=_catalog(version=reservation.catalog_release),
        event_reservation_ledger=ledger,
    )

    with patch.object(service, "check_workshop_capacity", return_value=(True, "ok")):
        order = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.PUBLIC_CODE,
            ttl="8h",
        )
        repeated = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.PUBLIC_CODE,
            ttl="8h",
        )

    assert repeated.workshop_id == order.workshop_id
    assert order.cluster_ref == reservation.cluster_ref == "arena"
    assert order.target_cluster == "arena"
    assert order.catalog_item_id == reservation.catalog_id
    assert order.num_users == reservation.resources.seats == 30
    assert order.metadata["catalog_release"] == reservation.catalog_release
    assert order.metadata["event_reservation_id"] == reservation.reservation_id
    consumed = next(
        item
        for item in ledger.list_active(now=NOW)
        if item.reservation_id == reservation.reservation_id
    )
    assert consumed.status == "consumed"
    assert consumed.workshop_id == order.workshop_id


def test_reserved_workshop_retry_does_not_recheck_already_owned_capacity():
    supply = _supply()
    plan = _plan("event-a", supply)
    reservation = plan.reservations[0]
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    service = ProvisioningService(
        catalog=_catalog(version=reservation.catalog_release),
        event_reservation_ledger=ledger,
    )

    with patch.object(
        service,
        "check_workshop_capacity",
        return_value=(True, "reserved capacity"),
    ) as capacity:
        order = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.INTERNAL,
            ttl="8h",
        )
        capacity.reset_mock()
        capacity.return_value = (False, "no free headroom")
        repeated = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.INTERNAL,
            ttl="8h",
        )

    assert repeated == order
    assert capacity.call_count == 0


def test_catalog_drift_fails_before_reservation_consumption():
    supply = _supply()
    plan = _plan("event-a", supply)
    reservation = plan.reservations[0]
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    service = ProvisioningService(
        catalog=_catalog(version="drifted-release"),
        event_reservation_ledger=ledger,
    )

    with pytest.raises(ValueError, match="immutable release"):
        service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.INTERNAL,
            ttl="8h",
        )

    held = next(
        item
        for item in ledger.list_active(now=NOW)
        if item.reservation_id == reservation.reservation_id
    )
    assert held.status == "held"


def test_provisioning_rejects_cluster_or_seat_tampering_after_consumption():
    supply = _supply()
    plan = _plan("event-a", supply)
    reservation = plan.reservations[0]
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    service = ProvisioningService(
        catalog=_catalog(version=reservation.catalog_release),
        event_reservation_ledger=ledger,
    )
    with patch.object(service, "check_workshop_capacity", return_value=(True, "ok")):
        order = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.INTERNAL,
            ttl="8h",
        )

    with pytest.raises(ValueError, match="no longer matches"):
        service.provision_workshop(
            order.model_copy(update={"cluster_ref": "brutus"})
        )
    with pytest.raises(ValueError, match="no longer matches"):
        service.provision_workshop(
            order.model_copy(update={"num_users": order.num_users - 1})
        )


def test_lifecycle_provisions_every_reserved_seat_on_persisted_cluster():
    supply = _supply()
    plan = _plan("event-a", supply)
    reservation = plan.reservations[0]
    ledger = EventReservationLedger()
    ledger.reserve(plan, supply, now=NOW)
    service = ProvisioningService(
        catalog=_catalog(version=reservation.catalog_release),
        event_reservation_ledger=ledger,
    )
    with patch.object(service, "check_workshop_capacity", return_value=(True, "ok")):
        order = service.create_reserved_workshop_order(
            reservation,
            tenant_id="event-tenant",
            exposure_policy=ExposurePolicy.INTERNAL,
            ttl="8h",
        )
        ready = service.provision_workshop(order)

    assert len(ready.session_ids) == reservation.resources.seats
    assert {
        service.get_session(session_id).cluster_ref
        for session_id in ready.session_ids
    } == {reservation.cluster_ref}
