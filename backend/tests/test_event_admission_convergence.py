"""The independent event evidence gates must agree before a new hold."""

from datetime import timedelta

from app.domain.event_artifact_health import (
    ArtifactColdPullEvidence,
    ArtifactReadinessRequirement,
    ArtifactReleaseReadiness,
    EventArtifactHealthSnapshot,
)
from app.domain.event_inflight_capacity import (
    EventInflightCapacitySnapshot,
    InflightClusterUsage,
    InflightResourceVector,
)
from app.domain.event_model_health import EventModelHealthSnapshot, ModelRuntimeHealth
from app.services.event_admission_convergence import (
    assess_event_admission_convergence,
    assess_event_admission_with_sources,
)
from app.services.event_artifact_requirements import (
    TrustedEligibleNodes,
    TrustedReleaseManifest,
)
from app.services.event_reservations import build_event_reservation_plan

from backend.tests.test_event_reservation_ledger import NOW, _record, _supply

IMAGE = "registry.example.io/lab@sha256:" + "a" * 64
SNAPSHOT_ID = "sha256:" + "b" * 64


def _evidence(record, supply):
    keys = sorted(
        {
            (item.cluster_id, item.catalog_id, item.catalog_release)
            for item in record.capacity_preview.allocations
        }
    )
    requirements = [
        ArtifactReadinessRequirement(
            cluster_id=cluster_id,
            catalog_id=catalog_id,
            catalog_release=release,
            image_refs=[IMAGE],
            expected_node_ids=["worker-1"],
        )
        for cluster_id, catalog_id, release in keys
    ]
    artifacts = EventArtifactHealthSnapshot(
        snapshot_id=SNAPSHOT_ID,
        observed_at=NOW,
        releases=[
            ArtifactReleaseReadiness(
                cluster_id=item.cluster_id,
                catalog_id=item.catalog_id,
                catalog_release=item.catalog_release,
                registry_reachable=True,
                pulls=[
                    ArtifactColdPullEvidence(
                        image_ref=IMAGE,
                        node_id="worker-1",
                        cold_cache_verified=True,
                        cold_samples=3,
                        failures=0,
                        cold_pull_p95_seconds=45,
                        digest_verified=True,
                        signature_verified=True,
                    )
                ],
            )
            for item in requirements
        ],
    )
    inflight = EventInflightCapacitySnapshot(
        snapshot_id=SNAPSHOT_ID,
        observed_at=NOW,
        clusters=[
            InflightClusterUsage(
                cluster_id="arena",
                accounting_complete=True,
                allocatable=InflightResourceVector(
                    cpu_millicores=90_000,
                    memory_mib=180_000,
                    pods=270,
                    model_slots=90,
                ),
                workloads=[],
            )
        ],
    )
    return requirements, artifacts, inflight


def test_complete_fresh_evidence_allows_a_local_admission_rehearsal():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)

    result = assess_event_admission_convergence(
        record,
        supply,
        [],
        requirements,
        artifacts,
        inflight,
        now=NOW,
    )

    assert result.status == "available"
    assert result.artifact_status == "ready"
    assert result.inflight_status == "available"
    assert result.model_status == "not_required"
    assert result.reservation_count == len(record.capacity_preview.allocations)
    assert result.evidence_ids["capacity_matrix"] == supply.matrix_digest
    assert result.evidence_ids["artifact"] == SNAPSHOT_ID
    assert result.evidence_ids["inflight"] == SNAPSHOT_ID


def test_trusted_release_and_node_sources_join_before_admission_rehearsal():
    supply = _supply()
    record = _record("event-converge", supply)
    _requirements, artifacts, inflight = _evidence(record, supply)

    class Releases:
        def get_promoted_release(self, catalog_id, catalog_release):
            return TrustedReleaseManifest(
                catalog_id=catalog_id,
                catalog_release=catalog_release,
                image_refs=[IMAGE],
                promotion_evidence_id=SNAPSHOT_ID,
            )

    class Nodes:
        def get_eligible_nodes(self, cluster_id, catalog_id, catalog_release):
            return TrustedEligibleNodes(
                cluster_id=cluster_id,
                catalog_id=catalog_id,
                catalog_release=catalog_release,
                node_ids=["worker-1"],
                observed_at=NOW,
            )

    accepted = assess_event_admission_with_sources(
        record, supply, [], Releases(), Nodes(), artifacts, inflight, now=NOW
    )
    assert accepted.status == "available"

    class MissingReleases:
        def get_promoted_release(self, _catalog_id, _catalog_release):
            return None

    blocked = assess_event_admission_with_sources(
        record, supply, [], MissingReleases(), Nodes(), artifacts, inflight, now=NOW
    )
    assert blocked.status == "blocked"
    assert blocked.artifact_status == "blocked"
    assert "missing" in blocked.explanation


def test_missing_evidence_blocks_without_falling_back_to_certified_seats():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    for art, physical, reason in [
        (None, inflight, "Artifact"),
        (artifacts, None, "In-flight"),
    ]:
        result = assess_event_admission_convergence(
            record, supply, [], requirements, art, physical, now=NOW
        )
        assert result.status == "blocked"
        assert reason in result.explanation


def test_stale_artifact_evidence_blocks_even_when_matrix_and_physical_fit():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    stale = artifacts.model_copy(update={"observed_at": NOW - timedelta(minutes=6)})
    result = assess_event_admission_convergence(
        record, supply, [], requirements, stale, inflight, now=NOW
    )
    assert result.status == "blocked"
    assert result.artifact_status == "blocked"
    assert "stale" in result.explanation


def test_model_dependent_event_requires_exact_serving_probe_at_convergence():
    supply = _supply()
    supply.clusters[0].certified_models = ["granite-8b"]
    record = _record("event-converge", supply)
    record.manifest.labs[0].required_models = ["granite-8b"]
    requirements, artifacts, inflight = _evidence(record, supply)
    missing = assess_event_admission_convergence(
        record, supply, [], requirements, artifacts, inflight, now=NOW
    )
    assert missing.status == "blocked"
    assert missing.model_status == "blocked"
    healthy = EventModelHealthSnapshot(
        snapshot_id=SNAPSHOT_ID,
        observed_at=NOW,
        models=[
            ModelRuntimeHealth(
                cluster_id="arena",
                model_id="granite-8b",
                ready_replicas=1,
                route_exposed=True,
                probe_success=True,
            )
        ],
    )
    accepted = assess_event_admission_convergence(
        record,
        supply,
        [],
        requirements,
        artifacts,
        inflight,
        now=NOW,
        model_health=healthy,
    )
    assert accepted.status == "available"
    assert accepted.model_status == "ready"


def test_trusted_artifact_requirements_must_cover_exact_allocations():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    result = assess_event_admission_convergence(
        record, supply, [], requirements[:1], artifacts, inflight, now=NOW
    )
    assert result.status == "blocked"
    assert "artifact requirement" in result.explanation.lower()


def test_physical_pressure_blocks_even_when_certified_matrix_fits():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    inflight.clusters[0].allocatable.cpu_millicores = 59_000
    result = assess_event_admission_convergence(
        record, supply, [], requirements, artifacts, inflight, now=NOW
    )
    assert result.status == "blocked"
    assert "cpu_millicores" in result.explanation


def test_existing_same_event_hold_requires_reconciliation_not_second_candidate():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    held = build_event_reservation_plan(
        record, supply, expires_at=NOW + timedelta(hours=1), now=NOW
    ).reservations
    result = assess_event_admission_convergence(
        record, supply, held, requirements, artifacts, inflight, now=NOW
    )
    assert result.status == "blocked"
    assert "existing" in result.explanation


def test_naive_admission_clock_fails_closed():
    supply = _supply()
    record = _record("event-converge", supply)
    requirements, artifacts, inflight = _evidence(record, supply)
    result = assess_event_admission_convergence(
        record,
        supply,
        [],
        requirements,
        artifacts,
        inflight,
        now=NOW.replace(tzinfo=None),
    )
    assert result.status == "blocked"
    assert "timezone" in result.explanation
