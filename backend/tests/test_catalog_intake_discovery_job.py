from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from app.domain.catalog_intake_discovery import (
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)
from app.services.catalog_intake_discovery_job import build_discovery_job_bundle


def _request() -> CatalogIntakeDiscoveryRequest:
    return CatalogIntakeDiscoveryRequest(
        intake_id="intake-example",
        attempt_id="attempt-001",
        repository_url="https://github.com/example/quickstart.git",
        revision="a" * 40,
        catalog_item_id="example-quickstart",
        display_name="Example Quickstart",
        policy_version="1.0.0",
        source_approval_id="approval-001",
        worker_image_digest="sha256:" + "b" * 64,
    )


def _approval() -> CatalogIntakeSourceApproval:
    return CatalogIntakeSourceApproval(
        approval_id="approval-001",
        repository_url="https://github.com/example/quickstart.git",
        revision="a" * 40,
        requested_by="solution-owner",
        approved_by="catalog-reviewer",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        purpose="Quickstart discovery",
    )


def test_job_bundle_enforces_isolated_ephemeral_runtime() -> None:
    bundle = build_discovery_job_bundle(
        _request(),
        source_approval=_approval(),
        namespace="launchpad-system",
        image="quay.io/example/catalog-intake-worker@sha256:" + "b" * 64,
        egress_proxy_url="http://catalog-intake-egress-proxy:8080",
    )
    job = bundle[0]
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]
    security = container["securityContext"]

    assert job["kind"] == "Job"
    assert job["spec"]["backoffLimit"] == 0
    assert job["spec"]["activeDeadlineSeconds"] == 300
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "Never"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert security["readOnlyRootFilesystem"] is True
    assert security["allowPrivilegeEscalation"] is False
    assert security["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["limits"] == {
        "cpu": "1",
        "memory": "1Gi",
        "ephemeral-storage": "1Gi",
    }
    assert pod["volumes"] == [
        {"name": "workspace", "emptyDir": {"sizeLimit": "512Mi"}}
    ]
    assert not any("secret" in str(item).lower() for item in container.get("env", []))


def test_job_bundle_only_allows_dns_and_egress_proxy() -> None:
    bundle = build_discovery_job_bundle(
        _request(),
        source_approval=_approval(),
        namespace="launchpad-system",
        image="quay.io/example/catalog-intake-worker@sha256:" + "b" * 64,
        egress_proxy_url="http://catalog-intake-egress-proxy:8080",
    )
    policy = bundle[1]
    egress = policy["spec"]["egress"]

    assert policy["kind"] == "NetworkPolicy"
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert policy["spec"]["ingress"] == []
    assert len(egress) == 2
    assert egress[0]["ports"] == [
        {"protocol": "UDP", "port": 53},
        {"protocol": "TCP", "port": 53},
    ]
    assert egress[1]["ports"] == [{"protocol": "TCP", "port": 8080}]


def test_job_bundle_rejects_mutable_worker_image_and_external_proxy() -> None:
    with pytest.raises(ValueError, match="immutable digest"):
        build_discovery_job_bundle(
            _request(),
            source_approval=_approval(),
            namespace="launchpad-system",
            image="quay.io/example/catalog-intake-worker:latest",
            egress_proxy_url="http://catalog-intake-egress-proxy:8080",
        )
    with pytest.raises(ValueError, match="in-cluster HTTP service"):
        build_discovery_job_bundle(
            _request(),
            source_approval=_approval(),
            namespace="launchpad-system",
            image="quay.io/example/catalog-intake-worker@sha256:" + "b" * 64,
            egress_proxy_url="https://proxy.example.com",
        )


def test_job_bundle_rejects_worker_image_that_differs_from_approved_digest() -> None:
    with pytest.raises(ValueError, match="approved worker digest"):
        build_discovery_job_bundle(
            _request(),
            source_approval=_approval(),
            namespace="launchpad-system",
            image="quay.io/example/catalog-intake-worker@sha256:" + "c" * 64,
            egress_proxy_url="http://catalog-intake-egress-proxy:8080",
        )


def test_job_bundle_rejects_mismatched_or_expired_source_approval() -> None:
    mismatched = _approval().model_copy(update={"revision": "c" * 40})
    with pytest.raises(ValueError, match="does not authorize"):
        build_discovery_job_bundle(
            _request(),
            source_approval=mismatched,
            namespace="launchpad-system",
            image="quay.io/example/catalog-intake-worker@sha256:" + "b" * 64,
            egress_proxy_url="http://catalog-intake-egress-proxy:8080",
        )

    expired = _approval().model_copy(
        update={"expires_at": datetime(2021, 1, 1, tzinfo=UTC)}
    )
    with pytest.raises(ValueError, match="does not authorize"):
        build_discovery_job_bundle(
            _request(),
            source_approval=expired,
            namespace="launchpad-system",
            image="quay.io/example/catalog-intake-worker@sha256:" + "b" * 64,
            egress_proxy_url="http://catalog-intake-egress-proxy:8080",
            now=datetime(2022, 1, 1, tzinfo=UTC),
        )


def test_worker_container_has_pinned_base_and_no_cluster_tooling() -> None:
    root = Path(__file__).resolve().parents[2]
    containerfile = (root / "backend/Containerfile.catalog-intake-worker").read_text()

    assert "ubi9/python-311@sha256:" in containerfile
    assert "USER 1001" in containerfile
    assert 'ENTRYPOINT ["python", "-m", "app.catalog_intake_worker_main"]' in containerfile
    assert "kubectl" not in containerfile
    assert "openshift-client" not in containerfile
    assert " oc " not in containerfile


def test_worker_contract_remains_analysis_only_and_release_blocked() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = yaml.safe_load(
        (root / "contracts/catalog-intake-discovery-worker-v1.yaml").read_text()
    )

    assert contract["source"]["standard"] == "quickstart-repository"
    assert contract["source"]["approval"] == {
        "object": "CatalogIntakeSourceApproval",
        "issuer": "trusted-intake-controller",
        "self_approval_allowed": False,
        "exact_match_fields": ["approval_id", "repository_url", "revision"],
        "time_bounded": True,
    }
    assert contract["network"]["default"] == "deny"
    assert contract["authority"] == {
        "mode": "analysis-only",
        "may_publish_catalog": False,
        "may_provision": False,
        "may_access_cluster_api": False,
        "may_access_catalog_database": False,
        "may_access_registry_publisher": False,
        "may_use_live_credentials": False,
    }
    assert contract["evidence"]["release_eligible"] is False
    assert contract["evidence"]["live_proofs_required"]
