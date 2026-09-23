"""Local, exact-match admission for one draft catalog image candidate.

This check cannot publish a catalog item or qualify a release. It deliberately
does not modify the platform or pilot artifact-registry policies.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

POLICY_VERSION = "launchpad.redhat.com/catalog-intake-candidate-policy/v1"
IMAGE = re.compile(r"^ghcr\.io/[^\s@]+@sha256:[0-9a-f]{64}$")
SOURCE = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RENDER_SCHEMA = "launchpad.redhat.com/catalog-intake-rendered-output/v2"
RENDER_ATTESTATION_STATUS_SCHEMA = (
    "launchpad.redhat.com/catalog-intake-render-attestation-status/v1"
)


def _get(mapping: Any, *keys: str) -> Any:
    value = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _candidate_helm_values(intake: dict[str, Any]) -> dict[str, Any] | None:
    """Return the exact, bounded values admitted to the candidate renderer."""

    workload = _get(intake, "runtime", "workload")
    values = _get(workload, "helm_values")
    if not isinstance(workload, dict) or not isinstance(values, dict):
        return None
    if set(values) != {"app", "model"}:
        return None
    app = values.get("app")
    model = values.get("model")
    secret = workload.get("runtime_secret_name")
    if (
        not isinstance(app, dict)
        or set(app) != {"image"}
        or not isinstance(app.get("image"), str)
        or not IMAGE.fullmatch(app["image"])
        or model != {"endpointFromSecret": True}
        or not isinstance(secret, str)
        or not secret
    ):
        return None
    return {
        "app": {"image": app["image"]},
        "model": {"endpointFromSecret": True, "existingSecret": secret},
    }


def candidate_helm_values_sha256(intake: dict[str, Any]) -> str | None:
    """Hash the approved renderer values using the versioned canonical encoding."""

    values = _candidate_helm_values(intake)
    if values is None:
        return None
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def review_candidate_admission(
    policy: dict[str, Any],
    intake: dict[str, Any],
    pull_evidence: dict[str, Any],
    render_review: dict[str, Any] | None = None,
    render_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return coded local findings; always deny release authority."""

    findings: set[str] = set()
    catalog_id = policy.get("catalog_item_id")
    cluster = policy.get("cluster")
    image = policy.get("image")
    revision = policy.get("source_revision")

    if policy.get("api_version") != POLICY_VERSION:
        findings.add("candidate-policy-version-invalid")
    if policy.get("release_eligible") is not False:
        findings.add("candidate-policy-must-not-release")
    if not isinstance(catalog_id, str) or policy.get("scope") != f"{catalog_id}-only":
        findings.add("candidate-scope-invalid")
    if catalog_id != _get(intake, "catalog", "catalog_item_id"):
        findings.add("catalog-identity-mismatch")
    if _get(intake, "catalog", "status") != "draft":
        findings.add("candidate-must-remain-draft")
    if not isinstance(revision, str) or not SOURCE.fullmatch(revision):
        findings.add("source-revision-invalid")
    for component in ("showroom", "workload"):
        if revision != _get(intake, "sources", component, "revision"):
            findings.add("source-revision-mismatch")
    if not isinstance(image, str) or not IMAGE.fullmatch(image):
        findings.add("candidate-image-invalid")
    if image != _get(intake, "runtime", "workload", "helm_values", "app", "image"):
        findings.add("candidate-image-mismatch")
    if cluster != "arena" or cluster != pull_evidence.get("cluster"):
        findings.add("cluster-evidence-mismatch")
    if policy.get("required_model") != "granite-3.2-8b-tools" or _get(
        intake, "runtime", "required_models"
    ) != [policy.get("required_model")]:
        findings.add("candidate-model-mismatch")
    workload = _get(intake, "runtime", "workload") or {}
    model_values = _get(workload, "helm_values", "model") or {}
    if model_values.get("endpoint"):
        findings.add("literal-model-endpoint-prohibited")
    expected_sources = {
        "endpoint": {"source": "model_endpoint", "model": policy.get("required_model")},
        "name": {"source": "requested_model"},
        "api-key": {"source": "maas_api_key"},
    }
    if (
        model_values.get("endpointFromSecret") is not True
        or workload.get("runtime_secret_name") != policy.get("runtime_secret_name")
        or workload.get("runtime_secret_value_path") != "model.existingSecret"
        or workload.get("runtime_secret_sources") != expected_sources
    ):
        findings.add("model-runtime-secret-missing")
    if policy.get("exposure_policy") != "internal" or _get(
        intake, "runtime", "allowed_exposure_policies"
    ) != ["internal"]:
        findings.add("exposure-not-internal-only")
    if (
        policy.get("max_workshop_seats") != 1
        or _get(intake, "certification", "max_workshop_seats") != 1
    ):
        findings.add("candidate-seat-limit-exceeded")
    if pull_evidence.get("status") != "passed" or pull_evidence.get("image") != image:
        findings.add("pull-evidence-not-passed")
    if (
        pull_evidence.get("cleanup") != "passed"
        or pull_evidence.get("namespace_absent_after_cleanup") is not True
    ):
        findings.add("pull-cleanup-not-passed")
    if pull_evidence.get("release_eligible") is not False:
        findings.add("pull-evidence-release-state-invalid")

    if not isinstance(render_review, dict):
        findings.add("render-review-missing")
    else:
        if render_review.get("schema_version") != RENDER_SCHEMA:
            findings.add("render-review-schema-mismatch")
        if render_review.get("status") != "review-ready" or render_review.get("findings") != []:
            findings.add("render-review-not-ready")
        if render_review.get("release_eligible") is not False:
            findings.add("render-review-release-state-invalid")
        if render_review.get("catalog_item_id") != catalog_id:
            findings.add("render-review-catalog-mismatch")
        if render_review.get("source_revision") != revision:
            findings.add("render-review-source-mismatch")
        expected_values_hash = candidate_helm_values_sha256(intake)
        if (
            expected_values_hash is None
            or render_review.get("helm_values_sha256") != expected_values_hash
        ):
            findings.add("render-review-values-mismatch")
        if not isinstance(render_review.get("manifest_sha256"), str) or not DIGEST.fullmatch(
            render_review["manifest_sha256"]
        ):
            findings.add("render-review-manifest-invalid")
        if not isinstance(render_review.get("renderer_image_digest"), str) or not DIGEST.fullmatch(
            render_review["renderer_image_digest"]
        ):
            findings.add("render-review-renderer-invalid")

    if not isinstance(render_attestation, dict):
        findings.add("render-attestation-missing")
    else:
        if render_attestation.get("schema_version") != RENDER_ATTESTATION_STATUS_SCHEMA:
            findings.add("render-attestation-schema-mismatch")
        if (
            render_attestation.get("status") != "GREEN-local-authenticated"
            or render_attestation.get("authenticated") is not True
            or render_attestation.get("findings") != []
        ):
            findings.add("render-attestation-not-ready")
        if render_attestation.get("release_eligible") is not False:
            findings.add("render-attestation-release-state-invalid")
        if render_attestation.get("producer_id") != policy.get("trusted_render_producer_id"):
            findings.add("render-attestation-producer-mismatch")
        if render_attestation.get("catalog_item_id") != catalog_id:
            findings.add("render-attestation-catalog-mismatch")
        if render_attestation.get("source_revision") != revision:
            findings.add("render-attestation-source-mismatch")
        render_reference = policy.get("render_evidence")
        expected_review_hash = (
            "sha256:" + render_reference.get("sha256", "")
            if isinstance(render_reference, dict)
            else None
        )
        if (
            not isinstance(expected_review_hash, str)
            or not DIGEST.fullmatch(expected_review_hash)
            or render_attestation.get("render_review_sha256") != expected_review_hash
        ):
            findings.add("render-attestation-review-mismatch")

    return {
        "status": "RED" if findings else "GREEN-local-candidate",
        "catalog_item_id": catalog_id,
        "cluster": cluster,
        "findings": sorted(findings),
        "release_eligible": False,
    }
