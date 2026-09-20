"""PostgreSQL transaction boundary for aggregate workshop admission."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from app.domain.capacity_admission import (
    AggregateCapacityReservation,
    CapacityAdmissionDecision,
    CapacityAdmissionRecord,
    CapacitySupplySnapshot,
    WorkshopCapacityRequest,
)
from app.services.capacity_admission import (
    AdmissionIdempotencyConflict,
    AdmissionReleaseConflict,
    _fingerprint,
    build_capacity_admission_decision,
)
from app.storage.stores import PersistenceUnavailableError, _decode_json, _get_sync_conn

_SERIALIZATION_ERRORS = {"40001", "40P01"}


def _record(
    decision: CapacityAdmissionDecision,
    reservation: AggregateCapacityReservation | None,
) -> CapacityAdmissionRecord:
    return CapacityAdmissionRecord(
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
        cleanup_evidence_id=reservation.cleanup_evidence_id if reservation else None,
        decided_at=decision.decided_at,
        released_at=reservation.released_at if reservation else None,
    )


class PostgresCapacityAdmissionStore:
    """Durable, serializable whole-workshop admission across API processes."""

    def __init__(self, *, serialization_retries: int = 3) -> None:
        self._serialization_retries = max(1, serialization_retries)

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
        for attempt in range(self._serialization_retries):
            conn = _get_sync_conn()
            if not conn:
                raise PersistenceUnavailableError(
                    "durable capacity admission persistence is unavailable"
                )
            try:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    for lock_key in sorted(
                        (
                            f"capacity-admission-cluster:{request.cluster_ref}",
                            f"capacity-admission-key:{request.idempotency_key}",
                        )
                    ):
                        cur.execute(
                            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                            (lock_key,),
                        )
                    cur.execute(
                        """SELECT request_fingerprint, data
                           FROM capacity_admission_decisions
                           WHERE idempotency_key = %s FOR UPDATE""",
                        (request.idempotency_key,),
                    )
                    row = cur.fetchone()
                    if row:
                        if row[0] != fingerprint:
                            raise AdmissionIdempotencyConflict(
                                "idempotency key already belongs to a different request"
                            )
                        decision = CapacityAdmissionDecision.model_validate(_decode_json(row[1]))
                        conn.commit()
                        return decision

                    cur.execute(
                        """SELECT data FROM aggregate_capacity_reservations
                           WHERE cluster_ref = %s AND status = 'held'
                           ORDER BY reservation_id FOR UPDATE""",
                        (request.cluster_ref,),
                    )
                    active = [
                        AggregateCapacityReservation.model_validate(_decode_json(item[0]))
                        for item in cur.fetchall()
                    ]
                    decision = build_capacity_admission_decision(
                        request, supply, active, now=current
                    )
                    cur.execute(
                        """INSERT INTO capacity_admission_decisions
                           (decision_id, idempotency_key, request_fingerprint,
                            workshop_id, cluster_ref, status, decided_at, data)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                        (
                            decision.decision_id,
                            decision.idempotency_key,
                            decision.request_fingerprint,
                            decision.workshop_id,
                            decision.cluster_ref,
                            decision.status,
                            decision.decided_at,
                            json.dumps(decision.model_dump(mode="json")),
                        ),
                    )
                    if decision.status == "accepted":
                        reservation = AggregateCapacityReservation(
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
                        cur.execute(
                            """INSERT INTO aggregate_capacity_reservations
                               (reservation_id, decision_id, idempotency_key,
                                workshop_id, cluster_ref, model_id, model_release,
                                status, created_at, data)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                                       %s::jsonb)""",
                            (
                                reservation.reservation_id,
                                reservation.decision_id,
                                reservation.idempotency_key,
                                reservation.workshop_id,
                                reservation.cluster_ref,
                                reservation.model_id,
                                reservation.model_release,
                                reservation.status,
                                reservation.created_at,
                                json.dumps(reservation.model_dump(mode="json")),
                            ),
                        )
                conn.commit()
                return decision
            except (AdmissionIdempotencyConflict, AdmissionReleaseConflict):
                conn.rollback()
                raise
            except Exception as exc:
                conn.rollback()
                if getattr(exc, "pgcode", None) in _SERIALIZATION_ERRORS and (
                    attempt + 1 < self._serialization_retries
                ):
                    continue
                raise PersistenceUnavailableError(
                    "failed to persist aggregate capacity admission"
                ) from exc
            finally:
                conn.close()
        raise PersistenceUnavailableError("capacity admission retries exhausted")

    def list_active_reservations(self) -> list[AggregateCapacityReservation]:
        conn = _get_sync_conn()
        if not conn:
            raise PersistenceUnavailableError(
                "durable capacity admission persistence is unavailable"
            )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data FROM aggregate_capacity_reservations
                       WHERE status = 'held' ORDER BY reservation_id"""
                )
                return [
                    AggregateCapacityReservation.model_validate(_decode_json(row[0]))
                    for row in cur.fetchall()
                ]
        except Exception as exc:
            raise PersistenceUnavailableError(
                "failed to read aggregate capacity reservations"
            ) from exc
        finally:
            conn.close()

    def list_records(self) -> list[CapacityAdmissionRecord]:
        conn = _get_sync_conn()
        if not conn:
            raise PersistenceUnavailableError(
                "durable capacity admission persistence is unavailable"
            )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT d.data, r.data
                       FROM capacity_admission_decisions d
                       LEFT JOIN aggregate_capacity_reservations r
                         ON r.decision_id = d.decision_id
                       ORDER BY d.decision_id"""
                )
                return [
                    _record(
                        CapacityAdmissionDecision.model_validate(_decode_json(row[0])),
                        AggregateCapacityReservation.model_validate(_decode_json(row[1]))
                        if row[1] is not None
                        else None,
                    )
                    for row in cur.fetchall()
                ]
        except Exception as exc:
            raise PersistenceUnavailableError("failed to read capacity admission records") from exc
        finally:
            conn.close()

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
        conn = _get_sync_conn()
        if not conn:
            raise PersistenceUnavailableError(
                "durable capacity admission persistence is unavailable"
            )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"capacity-reservation:{reservation_id}",),
                )
                cur.execute(
                    """SELECT data FROM aggregate_capacity_reservations
                       WHERE reservation_id = %s FOR UPDATE""",
                    (reservation_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise AdmissionReleaseConflict("reservation was not found")
                reservation = AggregateCapacityReservation.model_validate(_decode_json(row[0]))
                if reservation.status == "released":
                    if reservation.cleanup_evidence_id != cleanup_evidence_id:
                        raise AdmissionReleaseConflict(
                            "reservation was released with different cleanup evidence"
                        )
                    conn.commit()
                    return reservation
                released = reservation.model_copy(
                    update={
                        "status": "released",
                        "released_at": current,
                        "cleanup_evidence_id": cleanup_evidence_id,
                    }
                )
                cur.execute(
                    """UPDATE aggregate_capacity_reservations
                       SET status = 'released', released_at = %s,
                           cleanup_evidence_id = %s, data = %s::jsonb
                       WHERE reservation_id = %s AND status = 'held'""",
                    (
                        current,
                        cleanup_evidence_id,
                        json.dumps(released.model_dump(mode="json")),
                        reservation_id,
                    ),
                )
            conn.commit()
            return released
        except AdmissionReleaseConflict:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            raise PersistenceUnavailableError(
                "failed to release aggregate capacity reservation"
            ) from exc
        finally:
            conn.close()
