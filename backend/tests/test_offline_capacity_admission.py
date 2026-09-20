from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.capacity_admission import (
    CapacitySupplySnapshot,
    InferenceCapacity,
    WorkshopCapacityRequest,
)
from app.domain.events import EventResourceVector
from app.services.capacity_admission import (
    AdmissionIdempotencyConflict,
    AdmissionReleaseConflict,
    OfflineCapacityAdmissionLedger,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _supply(*, seats: int = 30, model_slots: int = 30) -> CapacitySupplySnapshot:
    return CapacitySupplySnapshot(
        snapshot_id="sha256:" + "a" * 64,
        policy_id="capacity-policy-v1",
        cluster_ref="arena",
        catalog_id="serve-llms",
        catalog_release="release-v1",
        eligible=True,
        infrastructure=EventResourceVector(
            seats=seats,
            cpu_millicores=seats * 1000,
            memory_mib=seats * 2048,
            pods=seats * 3,
            storage_gib=seats * 10,
            routes=seats * 3,
            model_slots=model_slots,
        ),
        inference=InferenceCapacity(
            model_id="granite-tools",
            model_release="granite-3.2-8b-tools-v1",
            concurrent_requests=model_slots,
            input_tokens_per_minute=model_slots * 1000,
            output_tokens_per_minute=model_slots * 500,
        ),
        observed_at=NOW,
        valid_until=NOW + timedelta(minutes=2),
    )


def _request(
    workshop_id: str,
    *,
    seats: int = 25,
    idempotency_key: str | None = None,
) -> WorkshopCapacityRequest:
    return WorkshopCapacityRequest(
        request_id=f"request-{workshop_id}",
        idempotency_key=idempotency_key or f"admit-{workshop_id}",
        forecast_ref="forecast:event-1:v1",
        event_id="event-1",
        workshop_id=workshop_id,
        catalog_id="serve-llms",
        catalog_release="release-v1",
        cluster_ref="arena",
        seats=seats,
        infrastructure_per_seat=EventResourceVector(
            seats=1,
            cpu_millicores=1000,
            memory_mib=2048,
            pods=3,
            storage_gib=10,
            routes=3,
            model_slots=1,
        ),
        inference_per_seat=InferenceCapacity(
            model_id="granite-tools",
            model_release="granite-3.2-8b-tools-v1",
            concurrent_requests=1,
            input_tokens_per_minute=1000,
            output_tokens_per_minute=500,
        ),
        requested_at=NOW,
    )


def test_whole_workshop_is_rejected_without_partial_reservation():
    ledger = OfflineCapacityAdmissionLedger()

    decision = ledger.admit(_request("workshop-a", seats=31), _supply(), now=NOW)

    assert decision.status == "rejected"
    assert decision.reservation_id is None
    assert decision.requested_seats == 31
    assert decision.reserved_seats == 0
    assert "infrastructure.seats" in decision.limiting_dimensions
    assert ledger.list_active_reservations() == []


def test_concurrent_requests_cannot_overbook_one_supply_snapshot():
    ledger = OfflineCapacityAdmissionLedger()
    supply = _supply(seats=30, model_slots=30)

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(
            executor.map(
                lambda request: ledger.admit(request, supply, now=NOW),
                [_request("workshop-a", seats=20), _request("workshop-b", seats=20)],
            )
        )

    assert sorted(item.status for item in decisions) == ["accepted", "rejected"]
    assert (
        sum(item.resources.infrastructure.seats for item in ledger.list_active_reservations()) == 20
    )
    assert all(item.reserved_seats in {0, 20} for item in decisions)


def test_identical_retry_returns_original_decision_and_changed_payload_conflicts():
    ledger = OfflineCapacityAdmissionLedger()
    supply = _supply()
    request = _request("workshop-a")

    first = ledger.admit(request, supply, now=NOW)
    repeated = ledger.admit(request, supply, now=NOW + timedelta(seconds=30))

    assert repeated == first
    assert len(ledger.list_records()) == 1
    changed = request.model_copy(update={"seats": 24})
    with pytest.raises(AdmissionIdempotencyConflict, match="different request"):
        ledger.admit(changed, supply, now=NOW)


def test_rejected_decision_is_idempotent_and_does_not_turn_into_a_later_hold():
    ledger = OfflineCapacityAdmissionLedger()
    request = _request("workshop-a", seats=31)

    rejected = ledger.admit(request, _supply(seats=30), now=NOW)
    retry = ledger.admit(request, _supply(seats=60, model_slots=60), now=NOW)

    assert retry == rejected
    assert retry.status == "rejected"
    assert ledger.list_active_reservations() == []


def test_exact_model_release_and_fresh_eligible_supply_are_required():
    ledger = OfflineCapacityAdmissionLedger()
    wrong_model = _supply()
    wrong_model.inference.model_release = "different-release"

    model_decision = ledger.admit(_request("wrong-model"), wrong_model, now=NOW)
    stale_decision = ledger.admit(
        _request("stale"),
        _supply(),
        now=NOW + timedelta(minutes=3),
    )
    disabled = _supply()
    disabled.eligible = False
    disabled_decision = ledger.admit(_request("disabled"), disabled, now=NOW)

    assert model_decision.reason_codes == ["model_release_mismatch"]
    assert stale_decision.reason_codes == ["supply_snapshot_stale"]
    assert disabled_decision.reason_codes == ["supply_ineligible"]
    assert ledger.list_active_reservations() == []


def test_model_token_capacity_rejects_entire_workshop_even_when_cluster_fits():
    ledger = OfflineCapacityAdmissionLedger()
    supply = _supply(seats=30, model_slots=30)
    supply.inference.input_tokens_per_minute = 10_000

    decision = ledger.admit(_request("token-heavy", seats=25), supply, now=NOW)

    assert decision.status == "rejected"
    assert decision.limiting_dimensions == ["inference.input_tokens_per_minute"]
    assert ledger.list_active_reservations() == []


def test_cleanup_evidenced_release_is_idempotent_and_frees_capacity():
    ledger = OfflineCapacityAdmissionLedger()
    supply = _supply(seats=25, model_slots=25)
    accepted = ledger.admit(_request("workshop-a"), supply, now=NOW)

    released = ledger.release(
        accepted.reservation_id,
        cleanup_evidence_id="sha256:" + "c" * 64,
        now=NOW + timedelta(minutes=1),
    )
    repeated = ledger.release(
        accepted.reservation_id,
        cleanup_evidence_id="sha256:" + "c" * 64,
        now=NOW + timedelta(minutes=2),
    )

    assert released.status == "released"
    assert repeated == released
    assert ledger.list_active_reservations() == []
    second = ledger.admit(_request("workshop-b"), supply, now=NOW)
    assert second.status == "accepted"


def test_release_rejects_non_digest_or_conflicting_cleanup_evidence():
    ledger = OfflineCapacityAdmissionLedger()
    accepted = ledger.admit(_request("workshop-a"), _supply(), now=NOW)

    with pytest.raises(AdmissionReleaseConflict, match="SHA-256"):
        ledger.release(
            accepted.reservation_id,
            cleanup_evidence_id="operator-says-clean",
            now=NOW + timedelta(minutes=1),
        )
    ledger.release(
        accepted.reservation_id,
        cleanup_evidence_id="sha256:" + "c" * 64,
        now=NOW + timedelta(minutes=1),
    )
    with pytest.raises(AdmissionReleaseConflict, match="different cleanup evidence"):
        ledger.release(
            accepted.reservation_id,
            cleanup_evidence_id="sha256:" + "d" * 64,
            now=NOW + timedelta(minutes=2),
        )


def test_reconciliation_snapshot_preserves_dimensions_and_detects_capacity_drift():
    ledger = OfflineCapacityAdmissionLedger()
    original = _supply(seats=30, model_slots=30)
    decision = ledger.admit(_request("workshop-a", seats=25), original, now=NOW)
    reduced = _supply(seats=20, model_slots=20)
    reduced.snapshot_id = "sha256:" + "d" * 64

    snapshot = ledger.reconcile(reduced, now=NOW + timedelta(minutes=1))

    assert decision.status == "accepted"
    assert snapshot.status == "overcommitted"
    assert "infrastructure.seats" in snapshot.exceeded_dimensions
    assert "inference.concurrent_requests" in snapshot.exceeded_dimensions
    assert snapshot.active_reservations == 1
    assert snapshot.active_seats == 25
    record = snapshot.records[0]
    assert record.event_id == "event-1"
    assert record.workshop_id == "workshop-a"
    assert record.catalog_id == "serve-llms"
    assert record.catalog_release == "release-v1"
    assert record.cluster_ref == "arena"
    assert record.model_id == "granite-tools"
    assert record.model_release == "granite-3.2-8b-tools-v1"
    assert record.forecast_ref == "forecast:event-1:v1"
    assert record.reservation_status == "held"
