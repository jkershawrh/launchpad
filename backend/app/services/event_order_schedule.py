"""Offline validation of approved, serial event-ordering windows.

This is a planning contract. It does not create workshop orders or authorize
reuse of retained seats; execution must recheck schedule and capacity later.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.events import EventManifest


class EventOrderWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort_id: str = Field(min_length=1)
    lab_ref: str = Field(min_length=1)
    not_before: datetime
    not_after: datetime


class EventOrderSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["launchpad.intel.com/event-order-schedule/v1"]
    event_id: str = Field(min_length=1)
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy: Literal["serial_per_event"]
    approved_by: list[str] = Field(min_length=2, max_length=2)
    approved_at: datetime
    windows: list[EventOrderWindow] = Field(min_length=1)


class EventOrderScheduleDecision(BaseModel):
    status: Literal["GREEN-local", "RED"]
    eligible: bool
    event_id: str
    manifest_digest: str
    workshop_count: int
    seat_environments: int
    failures: list[str]


def manifest_scope_digest(manifest: EventManifest) -> str:
    """Bind ordering approval to all manifest fields, not just seat totals."""

    canonical = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def evaluate_event_order_schedule(
    manifest: EventManifest,
    schedule: EventOrderSchedule,
) -> EventOrderScheduleDecision:
    failures: list[str] = []
    digest = manifest_scope_digest(manifest)
    seat_environments = sum(
        cohort.participants * len(cohort.lab_refs) for cohort in manifest.cohorts
    )
    if schedule.event_id != manifest.event_id:
        failures.append("schedule event ID does not match manifest")
    if schedule.manifest_digest != digest:
        failures.append("schedule manifest digest does not match approved scope")
    if not (
        manifest.approval.event_owner_approved
        and manifest.approval.technical_approver_approved
    ):
        failures.append("event owner and technical approver must approve the manifest")
    if manifest.approval.approved_seat_environments != seat_environments:
        failures.append("event approval does not match seat-environment demand")
    if manifest.approval.approved_retention_hours != manifest.retention.hours:
        failures.append("event approval does not match retention policy")
    if (
        set(schedule.approved_by) != {manifest.owner, manifest.technical_approver}
        or len(set(schedule.approved_by)) != 2
    ):
        failures.append("schedule approvers must match distinct event owners")
    if not _aware(schedule.approved_at):
        failures.append("schedule approval must be timezone-aware")

    cohorts = {cohort.cohort_id: cohort for cohort in manifest.cohorts}
    expected = Counter(
        (cohort.cohort_id, lab_ref)
        for cohort in manifest.cohorts
        for lab_ref in cohort.lab_refs
    )
    observed = Counter((window.cohort_id, window.lab_ref) for window in schedule.windows)
    for key in sorted(expected.keys() | observed.keys()):
        if observed[key] != expected[key]:
            failures.append(
                f"ordering window coverage differs for {key[0]}/{key[1]}: "
                f"expected {expected[key]}, found {observed[key]}"
            )

    valid_windows: list[EventOrderWindow] = []
    for window in schedule.windows:
        label = f"{window.cohort_id}/{window.lab_ref}"
        if not _aware(window.not_before) or not _aware(window.not_after):
            failures.append(f"ordering window {label} must be timezone-aware")
            continue
        if window.not_before >= window.not_after:
            failures.append(f"ordering window {label} must end after it starts")
            continue
        cohort = cohorts.get(window.cohort_id)
        if cohort is not None:
            if cohort.starts_at is None:
                failures.append(f"cohort {cohort.cohort_id} has no scheduled start")
            elif not _aware(cohort.starts_at):
                failures.append(f"cohort {cohort.cohort_id} start must be timezone-aware")
            elif window.not_after > cohort.starts_at:
                failures.append(f"ordering window {label} ends after cohort start")
        valid_windows.append(window)

    valid_windows.sort(key=lambda item: (item.not_before, item.not_after))
    for prior, current in pairwise(valid_windows):
        if current.not_before < prior.not_after:
            failures.append(
                "serial event ordering windows overlap: "
                f"{prior.cohort_id}/{prior.lab_ref} and "
                f"{current.cohort_id}/{current.lab_ref}"
            )
    if (
        valid_windows
        and _aware(schedule.approved_at)
        and schedule.approved_at >= valid_windows[0].not_before
    ):
        failures.append("schedule approval must precede every order window")

    return EventOrderScheduleDecision(
        status="RED" if failures else "GREEN-local",
        eligible=not failures,
        event_id=manifest.event_id,
        manifest_digest=digest,
        workshop_count=len(expected),
        seat_environments=seat_environments,
        failures=failures,
    )
