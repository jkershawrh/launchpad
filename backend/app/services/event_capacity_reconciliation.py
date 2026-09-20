"""Pure, file-backed event capacity forecast and reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from app.domain.capacity_reconciliation import (
    CapacityEvidenceSource,
    CapacityForecast,
    CapacityMeasurement,
    CapacityReconciliation,
    CapacityVariance,
    ForecastCatalog,
    ObservedCapacity,
    ObservedCatalog,
    RecordedEventManifest,
    RecordedPilotPostmortem,
)


def _available(value: float | str, unit: str | None = None) -> CapacityMeasurement:
    return CapacityMeasurement(status="available", value=value, unit=unit)


def _unavailable(reason: str, unit: str | None = None) -> CapacityMeasurement:
    return CapacityMeasurement(
        status="unavailable",
        value=None,
        unit=unit,
        reason=reason,
    )


def build_capacity_forecast(manifest: RecordedEventManifest) -> CapacityForecast:
    spec = manifest.spec
    participants = sum(cohort.participants for cohort in spec.cohorts)
    workshops = sum(len(cohort.lab_refs) for cohort in spec.cohorts)
    seats = sum(cohort.participants * len(cohort.lab_refs) for cohort in spec.cohorts)
    approval = spec.approval
    if not approval.event_owner_approved or not approval.technical_approver_approved:
        raise ValueError("recorded event forecast requires both approvals")
    if approval.approved_seat_environments != seats:
        raise ValueError(
            "recorded event approved "
            f"{approval.approved_seat_environments} seat-environments but requires {seats}"
        )
    if approval.approved_retention_hours != spec.retention.hours:
        raise ValueError("recorded event approved retention does not match forecast retention")
    lab_by_ref = {lab.lab_ref: lab for lab in spec.labs}
    catalog_seats: Counter[str] = Counter()
    for cohort in spec.cohorts:
        for lab_ref in cohort.lab_refs:
            catalog_seats[lab_ref] += cohort.participants

    missing_schedule = [cohort.cohort_id for cohort in spec.cohorts if cohort.starts_at is None]
    wave_schedule = (
        _unavailable("cohort starts_at is not recorded for: " + ", ".join(missing_schedule))
        if missing_schedule
        else _available(len(spec.cohorts), "scheduled waves")
    )

    return CapacityForecast(
        cohort_count=len(spec.cohorts),
        participant_count=participants,
        workshop_count=workshops,
        seat_environments=seats,
        peak_concurrent_participants=max(cohort.participants for cohort in spec.cohorts),
        # Without explicit end/reuse semantics, retained capacity accumulates.
        peak_retained_environments=seats,
        retention_hours=spec.retention.hours,
        provisioning_waves=_available(len(spec.cohorts), "waves"),
        wave_schedule=wave_schedule,
        deployment_class=_unavailable(
            "deployment class is not present in the recorded event manifest"
        ),
        catalogs=[
            ForecastCatalog(
                lab_ref=lab_ref,
                catalog_id=lab_by_ref[lab_ref].catalog_id,
                catalog_release=lab_by_ref[lab_ref].catalog_release,
                seat_environments=catalog_seats[lab_ref],
            )
            for lab_ref in sorted(catalog_seats)
        ],
    )


def reconcile_capacity(
    manifest: RecordedEventManifest,
    postmortem: RecordedPilotPostmortem,
    *,
    manifest_source: str,
    manifest_digest: str,
    postmortem_source: str,
    postmortem_digest: str,
) -> CapacityReconciliation:
    forecast = build_capacity_forecast(manifest)
    summary = postmortem.summary
    not_recorded = "the recorded pilot postmortem does not contain this measurement"
    no_reservations = (
        "the pilot was reconstructed after execution and has no authoritative "
        "event reservation records"
    )
    observed = ObservedCapacity(
        waves=summary.waves,
        workshops_ordered=summary.workshops_ordered,
        workshops_ready_retained=summary.workshops_ready_retained,
        workshops_reclaimed=summary.workshops_reclaimed,
        seats_provisioned=summary.seats_provisioned,
        seats_claimed=summary.seats_claimed,
        seats_unclaimed=summary.seats_unclaimed,
        claim_utilization_percent=summary.claim_utilization_percent,
        catalogs=[
            ObservedCatalog(
                catalog_label=item.name,
                catalog_id=_unavailable(
                    "the postmortem records a display label but no immutable catalog ID"
                ),
                ordered=item.ordered,
                claimed=item.claimed,
                unclaimed=item.unclaimed,
                claim_percent=item.claim_percent,
            )
            for item in postmortem.catalogs
        ],
        clusters=postmortem.clusters,
        models=postmortem.models,
        reservations=_unavailable(no_reservations, "reservations"),
        actual_cpu_millicore_hours=_unavailable(not_recorded, "millicore-hours"),
        actual_memory_mib_hours=_unavailable(not_recorded, "MiB-hours"),
        actual_storage_gib_hours=_unavailable(not_recorded, "GiB-hours"),
        model_requests=_unavailable(not_recorded, "requests"),
        model_input_tokens=_unavailable(not_recorded, "tokens"),
        model_output_tokens=_unavailable(not_recorded, "tokens"),
        model_queue_seconds=_unavailable(not_recorded, "seconds"),
        image_cache_hit_rate=_unavailable(not_recorded, "percent"),
    )
    return CapacityReconciliation(
        schema_version="launchpad.intel.com/capacity-reconciliation/v1",
        event_id=manifest.spec.event_id,
        observed_at=postmortem.snapshot_at,
        sources=[
            CapacityEvidenceSource(role="forecast", path=manifest_source, sha256=manifest_digest),
            CapacityEvidenceSource(
                role="observed", path=postmortem_source, sha256=postmortem_digest
            ),
        ],
        forecast=forecast,
        observed=observed,
        variance=CapacityVariance(
            provisioned_seat_environments=(summary.seats_provisioned - forecast.seat_environments),
            workshop_count=summary.workshops_ordered - forecast.workshop_count,
            unclaimed_seat_environments=summary.seats_unclaimed,
            claim_utilization_percent=summary.claim_utilization_percent,
            reservation_variance=_unavailable(no_reservations, "reservations"),
            actual_resource_variance=_unavailable(
                "actual resource usage was not recorded, so forecast error cannot be calculated"
            ),
            model_demand_variance=_unavailable(
                "model request, token, and queue demand were not recorded"
            ),
        ),
        limitations=[
            "This report reconciles recorded files only and performs no live cluster call.",
            "Provisioned seats are not participant completion evidence.",
            "Catalog display labels are not guessed into immutable catalog IDs.",
            "Resource reservations and actual CPU, memory, storage, model, and cache use are unavailable.",
        ],
    )


def _digest(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _source_name(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def reconcile_capacity_files(
    manifest_path: str | Path,
    postmortem_path: str | Path,
    *,
    root: str | Path | None = None,
) -> CapacityReconciliation:
    manifest_file = Path(manifest_path)
    postmortem_file = Path(postmortem_path)
    manifest_source = manifest_file.read_bytes()
    postmortem_source = postmortem_file.read_bytes()
    manifest = RecordedEventManifest.model_validate(yaml.safe_load(manifest_source.decode("utf-8")))
    postmortem = RecordedPilotPostmortem.model_validate(
        json.loads(postmortem_source.decode("utf-8"))
    )
    root_path = Path(root) if root is not None else None
    return reconcile_capacity(
        manifest,
        postmortem,
        manifest_source=_source_name(manifest_file, root_path),
        manifest_digest=_digest(manifest_source),
        postmortem_source=_source_name(postmortem_file, root_path),
        postmortem_digest=_digest(postmortem_source),
    )
