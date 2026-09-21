"""Release and placement, not requester or probe data, define artifact expectations."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from app.services.event_artifact_requirements import (
    ArtifactRequirementSourceError,
    TrustedEligibleNodes,
    TrustedReleaseManifest,
    build_event_artifact_requirements,
)

from backend.tests.test_event_reservation_ledger import _record, _supply

NOW = datetime(2026, 9, 19, 18, tzinfo=UTC)
IMAGE = "quay.io/example/serve@sha256:" + "a" * 64
OTHER_IMAGE = "quay.io/example/agent@sha256:" + "b" * 64


class Releases:
    def __init__(self, releases):
        self.releases = releases

    def get_promoted_release(self, catalog_id, catalog_release):
        return self.releases.get((catalog_id, catalog_release))


class Nodes:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_eligible_nodes(self, cluster_id, catalog_id, catalog_release):
        return self.nodes.get((cluster_id, catalog_id, catalog_release))


def sources(*, observed_at=NOW):
    releases = Releases(
        {
            ("serve-llms", "v1"): TrustedReleaseManifest(
                catalog_id="serve-llms",
                catalog_release="v1",
                image_refs=[IMAGE],
                promotion_evidence_id="sha256:" + "c" * 64,
            ),
            ("build-agent", "v2"): TrustedReleaseManifest(
                catalog_id="build-agent",
                catalog_release="v2",
                image_refs=[OTHER_IMAGE],
                promotion_evidence_id="sha256:" + "d" * 64,
            ),
        }
    )
    nodes = Nodes(
        {
            ("arena", "serve-llms", "v1"): TrustedEligibleNodes(
                cluster_id="arena",
                catalog_id="serve-llms",
                catalog_release="v1",
                node_ids=["worker-2", "worker-1"],
                observed_at=observed_at,
            ),
            ("arena", "build-agent", "v2"): TrustedEligibleNodes(
                cluster_id="arena",
                catalog_id="build-agent",
                catalog_release="v2",
                node_ids=["worker-2"],
                observed_at=observed_at,
            ),
        }
    )
    return releases, nodes


def build(record=None, releases=None, nodes=None):
    default_releases, default_nodes = sources()
    return build_event_artifact_requirements(
        record or _record("event-artifacts", _supply()),
        releases or default_releases,
        nodes or default_nodes,
        now=NOW,
    )


def test_exact_allocations_resolve_promoted_images_and_current_eligible_nodes():
    requirements = build()
    assert [(r.cluster_id, r.catalog_id, r.catalog_release) for r in requirements] == [
        ("arena", "build-agent", "v2"),
        ("arena", "serve-llms", "v1"),
    ]
    assert requirements[0].image_refs == [OTHER_IMAGE]
    assert requirements[0].expected_node_ids == ["worker-2"]
    assert requirements[1].image_refs == [IMAGE]
    assert requirements[1].expected_node_ids == ["worker-1", "worker-2"]


@pytest.mark.parametrize("change", ["missing", "wrong_release", "mutable", "empty"])
def test_missing_or_incorrect_promoted_release_fails_closed(change):
    releases, nodes = sources()
    if change == "missing":
        releases.releases.pop(("serve-llms", "v1"))
    elif change == "wrong_release":
        releases.releases[("serve-llms", "v1")] = releases.releases[
            ("serve-llms", "v1")
        ].model_copy(update={"catalog_release": "v9"})
    elif change == "mutable":
        releases.releases[("serve-llms", "v1")] = releases.releases[
            ("serve-llms", "v1")
        ].model_copy(update={"image_refs": ["quay.io/example/serve:latest"]})
    else:
        releases.releases[("serve-llms", "v1")] = releases.releases[
            ("serve-llms", "v1")
        ].model_copy(update={"image_refs": []})
    with pytest.raises(ArtifactRequirementSourceError):
        build(releases=releases, nodes=nodes)


@pytest.mark.parametrize("change", ["missing", "wrong_cluster", "empty", "stale", "future"])
def test_missing_or_incorrect_placement_fails_closed(change):
    releases, nodes = sources()
    key = ("arena", "serve-llms", "v1")
    if change == "missing":
        nodes.nodes.pop(key)
    elif change == "wrong_cluster":
        nodes.nodes[key] = nodes.nodes[key].model_copy(update={"cluster_id": "brutus"})
    elif change == "empty":
        nodes.nodes[key] = nodes.nodes[key].model_copy(update={"node_ids": []})
    elif change == "stale":
        nodes.nodes[key] = nodes.nodes[key].model_copy(
            update={"observed_at": NOW - timedelta(minutes=6)}
        )
    else:
        nodes.nodes[key] = nodes.nodes[key].model_copy(
            update={"observed_at": NOW + timedelta(minutes=1)}
        )
    with pytest.raises(ArtifactRequirementSourceError):
        build(releases=releases, nodes=nodes)


def test_requester_cannot_insert_an_unallocated_release_or_change_cluster():
    record = _record("event-artifacts", _supply())
    record.capacity_preview.allocations[0].cluster_id = "brutus"
    releases, nodes = sources()
    with pytest.raises(ArtifactRequirementSourceError):
        build(record, releases, nodes)


def test_absent_or_duplicate_allocation_fails_closed():
    record = _record("event-artifacts", _supply())
    record.capacity_preview.allocations = record.capacity_preview.allocations[:1]
    with pytest.raises(ArtifactRequirementSourceError):
        build(record)
    record = _record("event-artifacts", _supply())
    record.capacity_preview.allocations.append(record.capacity_preview.allocations[0].model_copy())
    with pytest.raises(ArtifactRequirementSourceError):
        build(record)


def test_contract_prohibits_requester_and_snapshot_as_requirement_sources():
    contract = yaml.safe_load(
        (Path(__file__).parents[2] / "contracts/event-artifact-requirements-v1.yaml").read_text()
    )
    assert contract["schema_version"] == "launchpad.redhat.com/event-artifact-requirements/v1"
    assert contract["output"]["type"] == "ArtifactReadinessRequirement"
    assert {"request_body", "runtime_health_snapshot"}.issubset(
        contract["security"]["forbidden_sources"]
    )
