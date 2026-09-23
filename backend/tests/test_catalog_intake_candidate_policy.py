from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
from app.adapters.openshift.provisioning import OpenShiftProvisioningAdapter
from app.services.catalog_intake_candidate_policy import (
    candidate_helm_values_sha256,
    review_candidate_admission,
)
from app.services.catalog_onboarding import build_catalog_item, validate_intake

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/catalog-intake-candidate-policy.yaml"
INTAKE = ROOT / "catalog-onboarding/hybrid-fraud-detection.yaml"


def _load() -> tuple[dict, dict, dict]:
    policy = yaml.safe_load(POLICY.read_text())
    intake = yaml.safe_load(INTAKE.read_text())
    probe = yaml.safe_load((ROOT / policy["pull_evidence"]["path"]).read_text())
    return policy, intake, probe


def _bind_model_runtime(intake: dict) -> None:
    workload = intake["runtime"]["workload"]
    workload["helm_values"]["model"] = {"endpointFromSecret": True}
    workload["runtime_secret_name"] = "fraud-model-runtime"
    workload["runtime_secret_value_path"] = "model.existingSecret"
    workload["runtime_secret_sources"] = {
        "endpoint": {"source": "model_endpoint", "model": "granite-3.2-8b-tools"},
        "name": {"source": "requested_model"},
        "api-key": {"source": "maas_api_key"},
    }


def _render_review(policy: dict, intake: dict) -> dict:
    return {
        "schema_version": "launchpad.redhat.com/catalog-intake-rendered-output/v2",
        "status": "review-ready",
        "findings": [],
        "catalog_item_id": policy["catalog_item_id"],
        "source_revision": policy["source_revision"],
        "helm_values_sha256": candidate_helm_values_sha256(intake),
        "manifest_sha256": "sha256:" + "a" * 64,
        "renderer_image_digest": "sha256:" + "b" * 64,
        "release_eligible": False,
    }


def test_current_candidate_stays_blocked_without_bound_render_review():
    policy, intake, probe = _load()
    report = review_candidate_admission(policy, intake, probe)
    assert report["status"] == "RED"
    assert report["findings"] == ["render-review-missing"]
    assert report["release_eligible"] is False


def test_exact_v2_render_review_advances_only_to_local_candidate():
    policy, intake, probe = _load()
    report = review_candidate_admission(policy, intake, probe, _render_review(policy, intake))

    assert report == {
        "status": "GREEN-local-candidate",
        "catalog_item_id": "hybrid-fraud-detection",
        "cluster": "arena",
        "findings": [],
        "release_eligible": False,
    }


def test_render_review_must_bind_exact_candidate_source_values_and_manifest():
    policy, intake, probe = _load()
    mutations = (
        ("schema_version", "launchpad.redhat.com/catalog-intake-rendered-output/v1"),
        ("status", "blocked"),
        ("catalog_item_id", "other-lab"),
        ("source_revision", "0" * 40),
        ("helm_values_sha256", "sha256:" + "0" * 64),
        ("manifest_sha256", "invalid"),
        ("renderer_image_digest", "invalid"),
        ("release_eligible", True),
    )

    for field, value in mutations:
        render_review = _render_review(policy, intake)
        render_review[field] = value
        report = review_candidate_admission(policy, intake, probe, render_review)
        assert report["status"] == "RED", field
        assert any(finding.startswith("render-review-") for finding in report["findings"]), field


def test_correct_secret_contract_is_locally_reviewable_but_never_released():
    policy, intake, probe = _load()
    _bind_model_runtime(intake)
    report = review_candidate_admission(policy, intake, probe, _render_review(policy, intake))
    assert report["status"] == "GREEN-local-candidate"
    assert report["findings"] == []
    assert report["release_eligible"] is False


def test_bound_intake_passes_contract_and_resolves_runtime_secret_per_seat():
    _policy, intake, _probe = _load()
    _bind_model_runtime(intake)
    report = validate_intake(intake)
    assert report["checks"]["intake_contract"] == "pass"
    metadata = build_catalog_item(intake)["metadata"]
    sources = metadata["workload_runtime_secret_sources"]
    runtime = OpenShiftProvisioningAdapter._resolve_workload_runtime_secret(
        sources,
        {
            "model_endpoints": {"granite-3.2-8b-tools": "http://granite.fleet-llm-d.svc:8080/v1"},
            "requested_models": ["granite-3.2-8b-tools"],
            "maas_api_key": "sk-seat-ephemeral",
        },
    )
    assert runtime == {
        "endpoint": "http://granite.fleet-llm-d.svc:8080/v1",
        "name": "granite-3.2-8b-tools",
        "api-key": "sk-seat-ephemeral",
    }
    assert metadata["workload_runtime_secret_value_path"] == "model.existingSecret"
    assert metadata["workload_helm_values"]["model"] == {"endpointFromSecret": True}


def test_other_catalog_digest_or_source_cannot_inherit_exception():
    policy, intake, probe = _load()
    for mutation in (
        ("catalog", "catalog_item_id", "other-lab"),
        ("sources", "revision", "0" * 40),
        ("image", None, "ghcr.io/other/app@sha256:" + "a" * 64),
    ):
        changed = deepcopy(intake)
        section, key, value = mutation
        if section == "catalog":
            changed["catalog"][key] = value
        elif section == "sources":
            changed["sources"]["workload"][key] = value
        else:
            changed["runtime"]["workload"]["helm_values"]["app"]["image"] = value
        report = review_candidate_admission(policy, changed, probe)
        assert report["status"] == "RED"
        assert report["release_eligible"] is False


def test_public_or_multiseat_candidate_is_rejected():
    policy, intake, probe = _load()
    intake["runtime"]["allowed_exposure_policies"].append("public_code")
    intake["certification"]["max_workshop_seats"] = 25
    report = review_candidate_admission(policy, intake, probe)
    assert "exposure-not-internal-only" in report["findings"]
    assert "candidate-seat-limit-exceeded" in report["findings"]


def test_model_requirement_must_match_canary_target():
    policy, intake, probe = _load()
    intake["runtime"]["required_models"] = []
    report = review_candidate_admission(policy, intake, probe)
    assert "candidate-model-mismatch" in report["findings"]


def test_model_runtime_requires_a_generated_secret_not_literal_helm_values():
    policy, intake, probe = _load()
    report = review_candidate_admission(policy, intake, probe)
    assert "model-runtime-secret-missing" not in report["findings"]

    intake["runtime"]["workload"]["runtime_secret_sources"] = {}
    intake["runtime"]["workload"]["helm_values"].setdefault("model", {})["endpoint"] = (
        "http://example.invalid/v1"
    )
    report = review_candidate_admission(policy, intake, probe)
    assert "model-runtime-secret-missing" in report["findings"]
    assert "literal-model-endpoint-prohibited" in report["findings"]


def test_unverified_pull_or_cleanup_is_rejected():
    policy, intake, probe = _load()
    probe["status"] = "blocked"
    probe["cleanup"] = "failed"
    report = review_candidate_admission(policy, intake, probe)
    assert "pull-evidence-not-passed" in report["findings"]
    assert "pull-cleanup-not-passed" in report["findings"]


def test_policy_cannot_set_release_eligibility_or_another_cluster():
    policy, intake, probe = _load()
    policy["release_eligible"] = True
    policy["cluster"] = "brutus"
    report = review_candidate_admission(policy, intake, probe)
    assert "candidate-policy-must-not-release" in report["findings"]
    assert "cluster-evidence-mismatch" in report["findings"]
