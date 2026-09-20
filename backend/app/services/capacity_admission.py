"""Thread-safe, pure in-memory whole-workshop capacity admission."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from threading import Lock

from app.domain.capacity_admission import (
    AggregateCapacityReservation,
    CapacityAdmissionDecision,
    CapacityAdmissionRecord,
    CapacityEnvelope,
    CapacityReconciliationSnapshot,
    CapacitySupplySnapshot,
    InferenceCapacity,
    WorkshopCapacityRequest,
)
from app.domain.events import EventResourceVector


class AdmissionIdempotencyConflict(RuntimeError):
    """An idempotency key was reused for a different workshop request."""


class AdmissionReleaseConflict(RuntimeError):
    """A reservation release is missing or carries conflicting evidence."""


def _sha(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fingerprint(request: WorkshopCapacityRequest) -> str:
    return _sha(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


def _zero_inference(model_id: str, model_release: str) -> InferenceCapacity:
    return InferenceCapacity(model_id=model_id, model_release=model_release)


def _plus_infrastructure(
    left: EventResourceVector, right: EventResourceVector
) -> EventResourceVector:
    return left.plus(right)


def _plus_inference(left: InferenceCapacity, right: InferenceCapacity) -> InferenceCapacity:
    if (left.model_id, left.model_release) != (right.model_id, right.model_release):
        raise ValueError("cannot aggregate different model releases")
    return left.model_copy(
        update={
            "concurrent_requests": left.concurrent_requests + right.concurrent_requests,
            "input_tokens_per_minute": (
                left.input_tokens_per_minute + right.input_tokens_per_minute
            ),
            "output_tokens_per_minute": (
                left.output_tokens_per_minute + right.output_tokens_per_minute
            ),
        }
    )


def _remaining_infrastructure(
    capacity: EventResourceVector, used: EventResourceVector
) -> EventResourceVector:
    available = capacity.model_dump()
    consumed = used.model_dump()
    return EventResourceVector(**{key: max(0, available[key] - consumed[key]) for key in available})


def _remaining_inference(capacity: InferenceCapacity, used: InferenceCapacity) -> InferenceCapacity:
    return capacity.model_copy(
        update={
            "concurrent_requests": max(0, capacity.concurrent_requests - used.concurrent_requests),
            "input_tokens_per_minute": max(
                0, capacity.input_tokens_per_minute - used.input_tokens_per_minute
            ),
            "output_tokens_per_minute": max(
                0, capacity.output_tokens_per_minute - used.output_tokens_per_minute
            ),
        }
    )


def _infrastructure_limits(
    demand: EventResourceVector, available: EventResourceVector
) -> list[str]:
    return [f"infrastructure.{item}" for item in demand.exceeds(available)]


def _inference_limits(demand: InferenceCapacity, available: InferenceCapacity) -> list[str]:
    fields = (
        "concurrent_requests",
        "input_tokens_per_minute",
        "output_tokens_per_minute",
    )
    return [
        f"inference.{field}"
        for field in fields
        if getattr(demand, field) > getattr(available, field)
    ]


class OfflineCapacityAdmissionLedger:
    """Atomic local admission ledger used for contract and fault proofs only."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._decisions: dict[str, CapacityAdmissionDecision] = {}
        self._reservations: dict[str, AggregateCapacityReservation] = {}

    def admit(
        self,
        request: WorkshopCapacityRequest,
        supply: CapacitySupplySnapshot,
        *,
        now: datetime | None = None,
    ) -> CapacityAdmissionDecision:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("admission timestamp must include a timezone")
        fingerprint = _fingerprint(request)
        with self._lock:
            existing = self._decisions.get(request.idempotency_key)
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise AdmissionIdempotencyConflict(
                        "idempotency key already belongs to a different request"
                    )
                return existing.model_copy(deep=True)

            decision = self._decide(request, supply, fingerprint, current)
            self._decisions[request.idempotency_key] = decision
            if decision.status == "accepted":
                self._reservations[decision.reservation_id] = AggregateCapacityReservation(
                    reservation_id=decision.reservation_id,
                    decision_id=decision.decision_id,
                    idempotency_key=request.idempotency_key,
                    request_fingerprint=fingerprint,
                    forecast_ref=request.forecast_ref,
                    event_id=request.event_id,
                    workshop_id=request.workshop_id,
                    catalog_id=request.catalog_id,
                    catalog_release=request.catalog_release,
                    cluster_ref=request.cluster_ref,
                    model_id=request.inference_per_seat.model_id,
                    model_release=request.inference_per_seat.model_release,
                    supply_snapshot_id=supply.snapshot_id,
                    policy_id=supply.policy_id,
                    resources=request.demand,
                    created_at=current,
                )
            return decision.model_copy(deep=True)

    def _decide(
        self,
        request: WorkshopCapacityRequest,
        supply: CapacitySupplySnapshot,
        fingerprint: str,
        current: datetime,
    ) -> CapacityAdmissionDecision:
        used = self._active_usage(supply)
        remaining_before = CapacityEnvelope(
            infrastructure=_remaining_infrastructure(supply.infrastructure, used.infrastructure),
            inference=_remaining_inference(supply.inference, used.inference),
        )
        reasons = self._eligibility_reasons(request, supply, current)
        limits: list[str] = []
        if not reasons:
            limits = _infrastructure_limits(
                request.demand.infrastructure, remaining_before.infrastructure
            ) + _inference_limits(request.demand.inference, remaining_before.inference)
            if limits:
                reasons = ["insufficient_aggregate_capacity"]

        accepted = not reasons
        decision_seed = f"{request.idempotency_key}:{fingerprint}:{supply.snapshot_id}"
        decision_id = _sha("decision:" + decision_seed)
        reservation_id = _sha("reservation:" + decision_seed) if accepted else None
        remaining_after = (
            CapacityEnvelope(
                infrastructure=_remaining_infrastructure(
                    remaining_before.infrastructure, request.demand.infrastructure
                ),
                inference=_remaining_inference(
                    remaining_before.inference, request.demand.inference
                ),
            )
            if accepted
            else remaining_before
        )
        return CapacityAdmissionDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            request_fingerprint=fingerprint,
            forecast_ref=request.forecast_ref,
            event_id=request.event_id,
            workshop_id=request.workshop_id,
            catalog_id=request.catalog_id,
            catalog_release=request.catalog_release,
            cluster_ref=request.cluster_ref,
            model_id=request.inference_per_seat.model_id,
            model_release=request.inference_per_seat.model_release,
            supply_snapshot_id=supply.snapshot_id,
            policy_id=supply.policy_id,
            status="accepted" if accepted else "rejected",
            reason_codes=reasons,
            limiting_dimensions=limits,
            requested_seats=request.seats,
            reserved_seats=request.seats if accepted else 0,
            demand=request.demand,
            remaining_before=remaining_before,
            remaining_after=remaining_after,
            reservation_id=reservation_id,
            decided_at=current,
        )

    @staticmethod
    def _eligibility_reasons(
        request: WorkshopCapacityRequest,
        supply: CapacitySupplySnapshot,
        current: datetime,
    ) -> list[str]:
        reasons = []
        if not supply.eligible:
            reasons.append("supply_ineligible")
        if current > supply.valid_until:
            reasons.append("supply_snapshot_stale")
        elif supply.observed_at > current + timedelta(seconds=30):
            reasons.append("supply_snapshot_future_dated")
        if request.cluster_ref != supply.cluster_ref:
            reasons.append("cluster_mismatch")
        if request.catalog_id != supply.catalog_id:
            reasons.append("catalog_mismatch")
        if request.catalog_release != supply.catalog_release:
            reasons.append("catalog_release_mismatch")
        inference = request.inference_per_seat
        if inference.model_id != supply.inference.model_id:
            reasons.append("model_mismatch")
        if inference.model_release != supply.inference.model_release:
            reasons.append("model_release_mismatch")
        return reasons

    def _active_usage(self, supply: CapacitySupplySnapshot) -> CapacityEnvelope:
        infrastructure = EventResourceVector()
        inference = _zero_inference(supply.inference.model_id, supply.inference.model_release)
        for reservation in self._reservations.values():
            if reservation.status != "held" or reservation.cluster_ref != supply.cluster_ref:
                continue
            infrastructure = _plus_infrastructure(
                infrastructure, reservation.resources.infrastructure
            )
            if (
                reservation.model_id,
                reservation.model_release,
            ) == (supply.inference.model_id, supply.inference.model_release):
                inference = _plus_inference(inference, reservation.resources.inference)
        return CapacityEnvelope(infrastructure=infrastructure, inference=inference)

    def list_active_reservations(self) -> list[AggregateCapacityReservation]:
        with self._lock:
            return sorted(
                [
                    item.model_copy(deep=True)
                    for item in self._reservations.values()
                    if item.status == "held"
                ],
                key=lambda item: item.reservation_id,
            )

    def release(
        self,
        reservation_id: str | None,
        *,
        cleanup_evidence_id: str,
        now: datetime | None = None,
    ) -> AggregateCapacityReservation:
        if not reservation_id:
            raise AdmissionReleaseConflict("reservation ID is required")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", cleanup_evidence_id):
            raise AdmissionReleaseConflict("cleanup evidence must be a SHA-256 evidence identifier")
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("release timestamp must include a timezone")
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise AdmissionReleaseConflict("reservation was not found")
            if reservation.status == "released":
                if reservation.cleanup_evidence_id != cleanup_evidence_id:
                    raise AdmissionReleaseConflict(
                        "reservation was released with different cleanup evidence"
                    )
                return reservation.model_copy(deep=True)
            released = reservation.model_copy(
                update={
                    "status": "released",
                    "released_at": current,
                    "cleanup_evidence_id": cleanup_evidence_id,
                }
            )
            self._reservations[reservation_id] = released
            return released.model_copy(deep=True)

    def list_records(self) -> list[CapacityAdmissionRecord]:
        with self._lock:
            return self._records_locked()

    def _records_locked(self) -> list[CapacityAdmissionRecord]:
        records = []
        for decision in self._decisions.values():
            reservation = (
                self._reservations.get(decision.reservation_id) if decision.reservation_id else None
            )
            records.append(
                CapacityAdmissionRecord(
                    decision_id=decision.decision_id,
                    reservation_id=decision.reservation_id,
                    forecast_ref=decision.forecast_ref,
                    event_id=decision.event_id,
                    workshop_id=decision.workshop_id,
                    catalog_id=decision.catalog_id,
                    catalog_release=decision.catalog_release,
                    cluster_ref=decision.cluster_ref,
                    model_id=decision.model_id,
                    model_release=decision.model_release,
                    supply_snapshot_id=decision.supply_snapshot_id,
                    policy_id=decision.policy_id,
                    decision_status=decision.status,
                    reservation_status=reservation.status if reservation else None,
                    requested_seats=decision.requested_seats,
                    reserved_seats=decision.reserved_seats,
                    reason_codes=decision.reason_codes,
                    limiting_dimensions=decision.limiting_dimensions,
                    requested_resources=decision.demand,
                    cleanup_evidence_id=(reservation.cleanup_evidence_id if reservation else None),
                    decided_at=decision.decided_at,
                    released_at=reservation.released_at if reservation else None,
                )
            )
        return sorted(records, key=lambda item: item.decision_id)

    def reconcile(
        self,
        supply: CapacitySupplySnapshot,
        *,
        now: datetime | None = None,
    ) -> CapacityReconciliationSnapshot:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("reconciliation timestamp must include a timezone")
        with self._lock:
            active = self._active_usage(supply)
            exceeded = _infrastructure_limits(
                active.infrastructure, supply.infrastructure
            ) + _inference_limits(active.inference, supply.inference)
            records = [
                item for item in self._records_locked() if item.cluster_ref == supply.cluster_ref
            ]
            return CapacityReconciliationSnapshot(
                schema_version=("launchpad.intel.com/capacity-admission-reconciliation/v1"),
                supply_snapshot_id=supply.snapshot_id,
                policy_id=supply.policy_id,
                cluster_ref=supply.cluster_ref,
                model_id=supply.inference.model_id,
                model_release=supply.inference.model_release,
                status="overcommitted" if exceeded else "balanced",
                active_reservations=sum(1 for item in records if item.reservation_status == "held"),
                active_seats=active.infrastructure.seats,
                active_infrastructure=active.infrastructure,
                active_inference=active.inference,
                exceeded_dimensions=exceeded,
                records=records,
                observed_at=current,
            )
