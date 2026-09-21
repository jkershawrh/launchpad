from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

IMMUTABLE_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
IMMUTABLE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_IMAGE = re.compile(r"(?m)^\s*image:\s*[\"']?([^\s\"'{}]+)")
EXECUTION_CLUSTER_MARKERS = (
    "image-registry.openshift-image-registry.svc",
    "default-route-openshift-image-registry",
    ".apps.arena.",
    ".apps.brutus.",
    ".apps.flightpath.",
    ".apps.oberon.",
)
REGISTRY_POLICY_VERSION = "launchpad.redhat.com/artifact-registry-policy/v1"
REQUIRED_REGISTRY_REPOSITORIES = {
    "backend",
    "portal",
    "admin",
    "keycloak",
    "showroom_terminal",
    "showroom_git_cloner",
}
REQUIRED_REGISTRY_CONTROLS = {
    "immutable_digest",
    "vulnerability_scan",
    "sbom",
    "signature",
    "provenance",
    "license_policy",
    "architecture_metadata",
    "backup_restore",
}
REQUIRED_DESTINATION_CHECKS = {
    "credential",
    "certificate",
    "architecture",
    "signature",
    "exact_digest",
    "cold_pull",
    "cache_loss",
}
DESTINATION_QUALIFICATION_VERSION = (
    "launchpad.redhat.com/artifact-destination-qualification/v1"
)
ARTIFACT_RELEASE_EVIDENCE_VERSION = (
    "launchpad.redhat.com/artifact-release-evidence/v1"
)
REQUIRED_RELEASE_CHECKS = {
    "vulnerability_scan",
    "sbom",
    "signature",
    "provenance",
    "license_policy",
    "retention",
}
_INLINE_CREDENTIAL_KEYS = {"auth", "password", "private_key", "secret", "token"}


def _aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _inline_credential_paths(value: Any, path: str = "receipt") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _INLINE_CREDENTIAL_KEYS or normalized.endswith(
                ("_password", "_private_key", "_secret", "_token")
            ):
                findings.append(f"inline credential field is prohibited: {path}.{key}")
            findings.extend(_inline_credential_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_inline_credential_paths(child, f"{path}[{index}]"))
    return findings


def validate_image_reference(
    reference: str,
    approved_repository_prefixes: Iterable[str],
) -> list[str]:
    """Return fail-closed supply-chain violations for one container image."""
    violations: list[str] = []
    if any(marker in reference for marker in EXECUTION_CLUSTER_MARKERS):
        violations.append(f"execution-cluster registry reference is prohibited: {reference}")
    if not IMMUTABLE_IMAGE.fullmatch(reference):
        violations.append(f"image reference must be immutable @sha256: {reference}")
    if not any(reference.startswith(prefix) for prefix in approved_repository_prefixes):
        violations.append(f"image repository is not approved by policy: {reference}")
    return violations


def _catalog_images(metadata: dict[str, Any]) -> list[str]:
    image = (metadata.get("workload_helm_values") or {}).get("image") or {}
    repository = image.get("repository")
    digest = image.get("digest")
    if repository and digest:
        return [f"{repository}@{digest}"]
    return []


def _artifact_images(path: Path) -> list[str]:
    return MANIFEST_IMAGE.findall(path.read_text())


def build_registry_policy_report(policy_path: Path | str) -> dict[str, Any]:
    """Validate the authoritative artifact-registry contract.

    A structurally complete policy can be GREEN-local while production release
    remains ineligible. Runtime repository grants, signatures, restore, and
    destination cold pulls require separate integration/live evidence.
    """
    path = Path(policy_path)
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise TypeError("artifact registry policy must be a YAML mapping")

    violations: list[str] = []
    gaps: list[str] = []
    if payload.get("api_version") != REGISTRY_POLICY_VERSION:
        violations.append(f"api_version must be {REGISTRY_POLICY_VERSION}")

    authority = payload.get("authority") or {}
    origin = str(authority.get("origin", "")).strip().rstrip("/")
    if not origin or "://" in origin or "@" in origin:
        violations.append("authority origin must be a registry host/organization path")
    if any(marker in origin for marker in EXECUTION_CLUSTER_MARKERS):
        violations.append("execution-cluster registry cannot be authoritative")
    if not authority.get("organization_ownership_approved"):
        gaps.append("organization ownership approval is not recorded")

    repository_payload = payload.get("repositories") or {}
    missing_repositories = sorted(REQUIRED_REGISTRY_REPOSITORIES - set(repository_payload))
    if missing_repositories:
        violations.append(
            "required dedicated repositories are missing: "
            + ", ".join(missing_repositories)
        )
    repositories: dict[str, str] = {}
    for component, contract in sorted(repository_payload.items()):
        if not isinstance(contract, dict):
            violations.append(f"{component} repository contract must be a mapping")
            continue
        repository = str(contract.get("repository", "")).rstrip("/")
        repositories[component] = repository
        if not repository or not repository.startswith(f"{origin}/"):
            violations.append(
                f"{component} repository must be under the authoritative origin"
            )
        if not contract.get("pull_grant_verified"):
            gaps.append(f"{component} pull grant is not verified")
    nonempty_repositories = [item for item in repositories.values() if item]
    if len(nonempty_repositories) != len(set(nonempty_repositories)):
        violations.append("each platform component requires a dedicated repository")

    credentials = payload.get("credentials") or {}
    publisher_permissions = set(
        (credentials.get("ci_publisher") or {}).get("permissions") or []
    )
    pull_permissions = list(
        (credentials.get("execution_cluster_pull") or {}).get("permissions") or []
    )
    human_permissions = set(
        (credentials.get("human_operator") or {}).get("permissions") or []
    )
    if publisher_permissions != {"pull", "push"}:
        violations.append("CI publisher must have only pull and push permissions")
    if pull_permissions != ["pull"]:
        violations.append("execution-cluster credentials must be pull-only")
    if "push" in human_permissions:
        violations.append("human operator credentials must not push production images")
    for role, contract in credentials.items():
        if any(key in (contract or {}) for key in ("token", "password", "auth")):
            violations.append(f"{role} contains an inline credential")

    retention = payload.get("retention") or {}
    if retention.get("delete_while_referenced") is not False:
        violations.append("referenced artifacts must never be deleted")
    if int(retention.get("minimum_rollback_releases") or 0) < 3:
        violations.append("retention must preserve at least three rollback releases")
    if int(retention.get("superseded_release_days") or 0) < 180:
        violations.append("superseded releases must be retained for at least 180 days")

    controls = payload.get("required_controls") or {}
    missing_controls = sorted(
        control for control in REQUIRED_REGISTRY_CONTROLS if controls.get(control) is not True
    )
    if missing_controls:
        violations.append("required controls are disabled: " + ", ".join(missing_controls))
    if not (payload.get("signing") or {}).get("identity_approved"):
        gaps.append("signing identity is not approved")

    destination = payload.get("destination_qualification") or {}
    declared_checks = set(destination.get("required_checks") or [])
    missing_checks = sorted(REQUIRED_DESTINATION_CHECKS - declared_checks)
    if missing_checks:
        violations.append(
            "destination qualification checks are missing: " + ", ".join(missing_checks)
        )
    clusters = destination.get("clusters") or {}
    if not clusters:
        violations.append("destination qualification requires at least one cluster")
    for cluster_id, qualification in sorted(clusters.items()):
        if (qualification or {}).get("status") != "GREEN-live":
            gaps.append(f"{cluster_id} destination qualification is not GREEN-live")
        if not (qualification or {}).get("evidence"):
            gaps.append(f"{cluster_id} destination evidence is missing")

    contract_status = "RED" if violations else "GREEN-local"
    return {
        "contract_status": contract_status,
        "release_eligible": contract_status == "GREEN-local" and not gaps,
        "authority": {
            "provider": authority.get("provider", ""),
            "origin": origin,
            "state": authority.get("state", ""),
        },
        "repositories": repositories,
        "contract_violations": violations,
        "release_gaps": gaps,
        "destination_clusters": sorted(clusters),
    }


def evaluate_destination_qualification(
    policy_path: Path | str,
    receipt_path: Path | str,
) -> dict[str, Any]:
    """Evaluate one recorded destination receipt without contacting a cluster.

    The receipt is evidence input, not proof merely because it exists. Every
    required check must be explicitly passed, carry a non-empty evidence
    reference, and agree with the authoritative registry and destination
    contract. Credential values are prohibited from the receipt.
    """

    policy = yaml.safe_load(Path(policy_path).read_text())
    receipt = yaml.safe_load(Path(receipt_path).read_text())
    if not isinstance(policy, dict) or not isinstance(receipt, dict):
        raise TypeError("registry policy and destination receipt must be mappings")

    failures: list[str] = []
    if receipt.get("schema_version") != DESTINATION_QUALIFICATION_VERSION:
        failures.append(f"schema_version must be {DESTINATION_QUALIFICATION_VERSION}")

    destination = policy.get("destination_qualification") or {}
    clusters = destination.get("clusters") or {}
    cluster_id = str(receipt.get("cluster_id", "")).strip()
    cluster_contract = clusters.get(cluster_id)
    if not cluster_id or not isinstance(cluster_contract, dict):
        failures.append("receipt cluster is not declared by registry policy")

    image = str(receipt.get("image", "")).strip()
    origin = str((policy.get("authority") or {}).get("origin", "")).rstrip("/")
    if not IMMUTABLE_IMAGE.fullmatch(image):
        failures.append("receipt image must use an immutable sha256 digest")
    elif not image.startswith(f"{origin}/"):
        failures.append("receipt image is outside the authoritative registry origin")

    architectures = set((cluster_contract or {}).get("architectures") or [])
    architecture = str(receipt.get("architecture", "")).strip()
    if not architectures:
        failures.append("destination policy does not declare supported architectures")
    elif architecture not in architectures:
        failures.append(
            f"receipt architecture {architecture or '<missing>'} is not supported by {cluster_id}"
        )

    if not str(receipt.get("observed_at", "")).strip():
        failures.append("receipt observed_at is required")

    failures.extend(_inline_credential_paths(receipt))

    required = set(destination.get("required_checks") or [])
    checks = receipt.get("checks") or {}
    for name in sorted(required):
        check = checks.get(name)
        if not isinstance(check, dict):
            failures.append(f"required destination check is missing: {name}")
            continue
        if check.get("status") != "passed":
            failures.append(f"destination check did not pass: {name}")
        evidence = check.get("evidence") or []
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ) or not evidence:
            failures.append(f"destination check has no evidence: {name}")

    unexpected = sorted(set(checks) - required)
    return {
        "schema_version": DESTINATION_QUALIFICATION_VERSION,
        "cluster_id": cluster_id,
        "image": image,
        "architecture": architecture,
        "status": "GREEN-integration" if not failures else "RED",
        "eligible": not failures,
        "failures": failures,
        "unexpected_checks": unexpected,
    }


def evaluate_artifact_release_evidence(
    policy_path: Path | str,
    receipt_path: Path | str,
) -> dict[str, Any]:
    """Evaluate one source-to-image release evidence bundle.

    The evaluator is deliberately offline. It proves that a receipt is complete
    and internally consistent; registry ownership, signature verification, and
    destination pulls still need authentic integration or live evidence.
    """

    policy = yaml.safe_load(Path(policy_path).read_text())
    receipt = yaml.safe_load(Path(receipt_path).read_text())
    if not isinstance(policy, dict) or not isinstance(receipt, dict):
        raise TypeError("registry policy and release evidence must be mappings")

    failures: list[str] = []
    if receipt.get("schema_version") != ARTIFACT_RELEASE_EVIDENCE_VERSION:
        failures.append(f"schema_version must be {ARTIFACT_RELEASE_EVIDENCE_VERSION}")

    component = str(receipt.get("component", "")).strip()
    repository_contract = (policy.get("repositories") or {}).get(component)
    if not component or not isinstance(repository_contract, dict):
        failures.append("component is not declared by registry policy")
        expected_repository = ""
    else:
        expected_repository = str(repository_contract.get("repository", "")).rstrip("/")

    image = str(receipt.get("image", "")).strip()
    if not IMMUTABLE_IMAGE.fullmatch(image):
        failures.append("image must use an immutable sha256 digest")
    image_repository = image.split("@", 1)[0]
    if not expected_repository or image_repository != expected_repository:
        failures.append("image does not match the component repository")

    source = receipt.get("source") or {}
    if not str(source.get("repository", "")).strip():
        failures.append("source repository is required")
    if not IMMUTABLE_GIT_SHA.fullmatch(str(source.get("revision", ""))):
        failures.append("source revision must be an immutable 40-character Git SHA")
    if source.get("tree_dirty") is not False:
        failures.append("source tree must be clean")

    architectures = receipt.get("architectures") or []
    if not isinstance(architectures, list) or not architectures or not all(
        isinstance(item, str) and item.strip() for item in architectures
    ):
        failures.append("at least one image architecture is required")

    build = receipt.get("build") or {}
    for field in ("builder_identity", "workflow_url", "completed_at"):
        if not str(build.get(field, "")).strip():
            failures.append(f"build {field} is required")
    completed_at = _aware_timestamp(build.get("completed_at"))
    if build.get("completed_at") and completed_at is None:
        failures.append("build completed_at must be a timezone-aware ISO 8601 timestamp")

    failures.extend(_inline_credential_paths(receipt))

    checks = receipt.get("checks") or {}
    for name in sorted(REQUIRED_RELEASE_CHECKS):
        check = checks.get(name)
        if not isinstance(check, dict):
            failures.append(f"required release check is missing: {name}")
            continue
        if check.get("status") != "passed":
            failures.append(f"release check did not pass: {name}")
        evidence = check.get("evidence") or []
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            failures.append(f"release check has no evidence: {name}")

    vulnerability = checks.get("vulnerability_scan") or {}
    if vulnerability.get("subject_image") != image:
        failures.append("vulnerability scan subject image does not match release image")
    for severity in ("critical", "high"):
        field = f"{severity}_findings"
        count = vulnerability.get(field)
        if type(count) is not int or count < 0:
            failures.append(f"vulnerability scan {field} must be integer zero")
        elif count > 0:
            failures.append(f"vulnerability scan contains {severity} findings")

    for name in ("sbom", "provenance"):
        check = checks.get(name) or {}
        if not str(check.get("artifact", "")).strip():
            failures.append(f"{name} artifact reference is required")
        if not re.fullmatch(r"[0-9a-f]{64}", str(check.get("sha256", ""))):
            failures.append(f"{name} sha256 digest is invalid")

    if (checks.get("sbom") or {}).get("subject_image") != image:
        failures.append("sbom subject image does not match release image")

    signature = checks.get("signature") or {}
    if not str(signature.get("identity", "")).strip():
        failures.append("signature identity is required")
    if signature.get("verified") is not True:
        failures.append("signature verification did not pass")
    if signature.get("subject_image") != image:
        failures.append("signature subject image does not match release image")

    provenance = checks.get("provenance") or {}
    if provenance.get("verified") is not True:
        failures.append("provenance verification did not pass")
    for field, expected, label in (
        ("subject_image", image, "subject image does not match release image"),
        (
            "source_repository",
            source.get("repository"),
            "source repository does not match release source",
        ),
        (
            "source_revision",
            source.get("revision"),
            "source revision does not match release source",
        ),
        (
            "builder_identity",
            build.get("builder_identity"),
            "builder identity does not match release build",
        ),
    ):
        if not provenance.get(field) or provenance.get(field) != expected:
            failures.append(f"provenance {label}")

    retention = checks.get("retention") or {}
    minimum_releases = int(
        (policy.get("retention") or {}).get("minimum_rollback_releases") or 0
    )
    retained = int(retention.get("rollback_releases_retained", 0) or 0)
    if retained < minimum_releases:
        failures.append("retention proof preserves fewer releases than policy")
    if not str(retention.get("protected_until", "")).strip():
        failures.append("retention protected_until is required")
    protected_until = _aware_timestamp(retention.get("protected_until"))
    if retention.get("protected_until") and protected_until is None:
        failures.append(
            "retention protected_until must be a timezone-aware ISO 8601 timestamp"
        )
    if completed_at is not None and protected_until is not None:
        required_days = int((policy.get("retention") or {}).get("superseded_release_days") or 0)
        if protected_until < completed_at + timedelta(days=required_days):
            failures.append("retention protected_until is earlier than policy requires")

    unexpected = sorted(set(checks) - REQUIRED_RELEASE_CHECKS)
    return {
        "schema_version": ARTIFACT_RELEASE_EVIDENCE_VERSION,
        "component": component,
        "source_revision": str(source.get("revision", "")),
        "image": image,
        "architectures": architectures,
        "status": "GREEN-local" if not failures else "RED",
        "eligible": not failures,
        "failures": failures,
        "unexpected_checks": unexpected,
    }


def build_supply_chain_report(
    policy_path: Path | str,
    repository_root: Path | str,
    *,
    artifact_root: Path | str | None = None,
) -> dict[str, Any]:
    """Validate the immutable image/content contract for promoted catalogs.

    This is intentionally a local promotion gate. Pullability, signatures,
    architecture compatibility, and cold-cache behavior remain integration and
    live certification gates.
    """
    policy_file = Path(policy_path)
    policy = yaml.safe_load(policy_file.read_text())
    if not isinstance(policy, dict):
        raise TypeError("catalog artifact policy must be a YAML mapping")
    root = Path(repository_root)
    artifacts = Path(artifact_root) if artifact_root is not None else root
    approved = policy.get("approved_repository_prefixes") or policy.get("approved_registries", [])
    if not approved:
        raise ValueError("catalog artifact policy requires approved repository prefixes")

    try:
        policy_label = str(policy_file.relative_to(root))
    except ValueError:
        policy_label = str(policy_file)
    result: dict[str, Any] = {
        "status": "GREEN-local",
        "policy": policy_label,
        "catalog_count": 0,
        "image_count": 0,
        "catalogs": {},
        "violations": [],
    }
    configured = policy.get("catalogs")
    if not isinstance(configured, dict) or not configured:
        raise ValueError("catalog artifact policy requires at least one catalog")

    for catalog_id, contract in configured.items():
        catalog_path = root / contract["catalog_path"]
        catalog_violations: list[str] = []
        images: list[str] = []
        if not catalog_path.is_file():
            catalog_violations.append(f"catalog file does not exist: {catalog_path}")
            catalog = {}
        else:
            catalog = yaml.safe_load(catalog_path.read_text()) or {}
        if catalog.get("catalog_item_id") != catalog_id:
            catalog_violations.append(
                f"catalog identity mismatch: expected {catalog_id}, "
                f"found {catalog.get('catalog_item_id')}"
            )
        metadata = catalog.get("metadata") or {}
        content_ref = str(metadata.get("showroom_content_ref", ""))
        immutable_content = bool(IMMUTABLE_GIT_SHA.fullmatch(content_ref))
        if not immutable_content:
            catalog_violations.append(
                f"{catalog_id} showroom_content_ref must be an immutable 40-character Git SHA"
            )
        images.extend(_catalog_images(metadata))

        for relative in contract.get("artifact_paths", []):
            artifact_path = artifacts / relative
            if not artifact_path.is_file():
                catalog_violations.append(f"artifact file does not exist: {artifact_path}")
                continue
            images.extend(_artifact_images(artifact_path))

        images = sorted(set(images))
        if not images:
            catalog_violations.append(f"{catalog_id} has no recorded runtime images")
        for image in images:
            catalog_violations.extend(validate_image_reference(image, approved))

        result["catalogs"][catalog_id] = {
            "catalog_path": str(catalog_path.relative_to(root)),
            "showroom_content_ref": content_ref,
            "showroom_content_ref_is_immutable": immutable_content,
            "images": images,
            "violations": catalog_violations,
        }
        result["violations"].extend(
            f"{catalog_id}: {violation}" for violation in catalog_violations
        )

    result["catalog_count"] = len(result["catalogs"])
    result["image_count"] = sum(len(catalog["images"]) for catalog in result["catalogs"].values())
    if result["violations"]:
        result["status"] = "RED"
    return result
