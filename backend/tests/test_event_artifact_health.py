"""Cold-pull readiness is separate from registry publication and pre-pull plans."""

from datetime import UTC, datetime, timedelta

import pytest
from app.domain.event_artifact_health import (
    ArtifactColdPullEvidence,
    ArtifactReadinessRequirement,
    ArtifactReleaseReadiness,
    EventArtifactHealthSnapshot,
)
from app.services.event_artifact_health import assess_event_artifact_health
from pydantic import ValidationError

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
IMAGE = "registry.example.com/launchpad/lab@sha256:" + "a" * 64
OTHER_IMAGE = "registry.example.com/launchpad/sidecar@sha256:" + "b" * 64
SNAPSHOT_ID = "sha256:" + "c" * 64


def requirement(**changes):
    values = {
        "cluster_id": "arena",
        "catalog_id": "serve-llms",
        "catalog_release": "2.1.0",
        "image_refs": [IMAGE],
        "expected_node_ids": ["worker-1", "worker-2"],
        "minimum_cold_samples": 3,
        "maximum_cold_pull_p95_seconds": 180,
    }
    values.update(changes)
    return ArtifactReadinessRequirement(**values)


def evidence(image=IMAGE, node="worker-1", **changes):
    values = {
        "image_ref": image,
        "node_id": node,
        "cold_cache_verified": True,
        "cold_samples": 3,
        "failures": 0,
        "cold_pull_p95_seconds": 72,
        "digest_verified": True,
        "signature_verified": True,
    }
    values.update(changes)
    return ArtifactColdPullEvidence(**values)


def snapshot(*, probes=None, observed_at=NOW, **changes):
    values = {
        "snapshot_id": SNAPSHOT_ID,
        "observed_at": observed_at,
        "releases": [
            ArtifactReleaseReadiness(
                cluster_id="arena",
                catalog_id="serve-llms",
                catalog_release="2.1.0",
                registry_reachable=True,
                pulls=probes
                if probes is not None
                else [evidence(node="worker-1"), evidence(node="worker-2")],
            )
        ],
    }
    values.update(changes)
    return EventArtifactHealthSnapshot(**values)


def test_missing_evidence_and_missing_trusted_requirements_fail_closed():
    assert assess_event_artifact_health([requirement()], None, NOW).status == "blocked"
    assert assess_event_artifact_health([], snapshot(), NOW).status == "blocked"


def test_complete_fresh_cold_pull_proof_passes():
    result = assess_event_artifact_health([requirement()], snapshot(), NOW)
    assert result.status == "ready"
    assert result.snapshot_id == SNAPSHOT_ID


@pytest.mark.parametrize(
    "proof,reason",
    [
        ({"cold_cache_verified": False}, "cold-cache"),
        ({"cold_samples": 2}, "samples"),
        ({"failures": 1}, "failures"),
        ({"cold_pull_p95_seconds": 181}, "latency"),
        ({"digest_verified": False}, "digest"),
        ({"signature_verified": False}, "signature"),
    ],
)
def test_unready_node_or_image_fails_closed(proof, reason):
    result = assess_event_artifact_health(
        [requirement()],
        snapshot(probes=[evidence(node="worker-1"), evidence(node="worker-2", **proof)]),
        NOW,
    )
    assert result.status == "blocked"
    assert reason in result.explanation.lower()


def test_registry_reachability_alone_is_not_cold_pull_proof():
    result = assess_event_artifact_health([requirement()], snapshot(probes=[]), NOW)
    assert result.status == "blocked"
    assert "worker-1" in result.explanation


def test_unreachable_registry_blocks_even_when_pull_proof_exists():
    snap = snapshot()
    snap.releases[0].registry_reachable = False
    result = assess_event_artifact_health([requirement()], snap, NOW)
    assert result.status == "blocked"
    assert "registry" in result.explanation


def test_expected_nodes_are_supplied_by_trusted_placement_not_snapshot():
    result = assess_event_artifact_health(
        [requirement(expected_node_ids=["worker-1", "worker-2", "worker-3"])],
        snapshot(),
        NOW,
    )
    assert result.status == "blocked"
    assert "worker-3" in result.explanation


def test_all_expected_immutable_images_must_be_proven_on_each_node():
    result = assess_event_artifact_health(
        [requirement(image_refs=[IMAGE, OTHER_IMAGE])], snapshot(), NOW
    )
    assert result.status == "blocked"
    assert OTHER_IMAGE in result.explanation


def test_exact_cluster_and_catalog_release_are_required():
    for changes in (
        {"cluster_id": "brutus"},
        {"catalog_id": "build-agent"},
        {"catalog_release": "2.1.1"},
    ):
        result = assess_event_artifact_health([requirement(**changes)], snapshot(), NOW)
        assert result.status == "blocked"


def test_stale_or_future_dated_proof_is_rejected():
    assert (
        assess_event_artifact_health(
            [requirement()], snapshot(observed_at=NOW - timedelta(seconds=301)), NOW
        ).status
        == "blocked"
    )
    assert (
        assess_event_artifact_health(
            [requirement()], snapshot(observed_at=NOW + timedelta(seconds=31)), NOW
        ).status
        == "blocked"
    )


def test_duplicate_or_mutable_evidence_is_invalid():
    with pytest.raises(ValidationError):
        requirement(image_refs=["registry.example.com/lab:latest"])
    with pytest.raises(ValidationError):
        requirement(expected_node_ids=["worker-1", "worker-1"])
    with pytest.raises(ValidationError):
        snapshot(probes=[evidence(), evidence()])
    with pytest.raises(ValidationError):
        snapshot(releases=[snapshot().releases[0], snapshot().releases[0]])
