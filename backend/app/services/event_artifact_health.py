"""Fail-closed, pure evaluation of event cold-pull readiness evidence."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.event_artifact_health import (
    ArtifactReadinessRequirement,
    EventArtifactHealthSnapshot,
)

MAX_ARTIFACT_EVIDENCE_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 30


@dataclass(frozen=True)
class ArtifactHealthAssessment:
    status: str
    explanation: str
    snapshot_id: str | None = None


def assess_event_artifact_health(
    requirements: list[ArtifactReadinessRequirement],
    snapshot: EventArtifactHealthSnapshot | None,
    now: datetime,
) -> ArtifactHealthAssessment:
    """Require recent pull and verification proof for every expected image/node.

    Requirements must come from trusted release manifests and placement, not
    the snapshot. This does not perform or attest a live cluster probe itself.
    """

    if now.tzinfo is None:
        raise ValueError("assessment time must include a timezone")
    if not requirements:
        return ArtifactHealthAssessment("blocked", "Trusted artifact requirements are unavailable")
    keys = [(item.cluster_id, item.catalog_id, item.catalog_release) for item in requirements]
    if len(keys) != len(set(keys)):
        return ArtifactHealthAssessment("blocked", "Duplicate trusted artifact requirements")
    if snapshot is None:
        return ArtifactHealthAssessment("blocked", "Artifact cold-pull evidence is unavailable")
    age_seconds = (now - snapshot.observed_at).total_seconds()
    if age_seconds > MAX_ARTIFACT_EVIDENCE_AGE_SECONDS:
        return ArtifactHealthAssessment(
            "blocked", "Artifact cold-pull evidence is stale", snapshot.snapshot_id
        )
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        return ArtifactHealthAssessment(
            "blocked", "Artifact cold-pull evidence is future-dated", snapshot.snapshot_id
        )

    releases = {
        (item.cluster_id, item.catalog_id, item.catalog_release): item for item in snapshot.releases
    }

    def blocked(reason: str) -> ArtifactHealthAssessment:
        return ArtifactHealthAssessment("blocked", reason, snapshot.snapshot_id)

    for requirement in sorted(
        requirements, key=lambda item: (item.cluster_id, item.catalog_id, item.catalog_release)
    ):
        label = f"{requirement.cluster_id}/{requirement.catalog_id}@{requirement.catalog_release}"
        release = releases.get(
            (requirement.cluster_id, requirement.catalog_id, requirement.catalog_release)
        )
        if release is None:
            return blocked(f"Artifact release evidence is missing: {label}")
        if not release.registry_reachable:
            return blocked(f"Artifact registry is unreachable: {label}")
        pulls = {(pull.image_ref, pull.node_id): pull for pull in release.pulls}
        for image in sorted(requirement.image_refs):
            for node in sorted(requirement.expected_node_ids):
                pull = pulls.get((image, node))
                item_label = f"{label} {image} on {node}"
                if pull is None:
                    return blocked(f"Cold-pull evidence is missing: {item_label}")
                if not pull.cold_cache_verified:
                    return blocked(f"Cold-cache proof is missing: {item_label}")
                if pull.cold_samples < requirement.minimum_cold_samples:
                    return blocked(f"Insufficient cold-pull samples: {item_label}")
                if pull.failures:
                    return blocked(f"Cold-pull failures were observed: {item_label}")
                if pull.cold_pull_p95_seconds > requirement.maximum_cold_pull_p95_seconds:
                    return blocked(f"Cold-pull latency exceeds policy: {item_label}")
                if not pull.digest_verified:
                    return blocked(f"Image digest verification failed: {item_label}")
                if not pull.signature_verified:
                    return blocked(f"Image signature verification failed: {item_label}")

    return ArtifactHealthAssessment(
        "ready", "All expected image/node cold pulls meet readiness policy", snapshot.snapshot_id
    )
