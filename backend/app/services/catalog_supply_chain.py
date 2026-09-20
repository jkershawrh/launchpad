from __future__ import annotations

import re
from collections.abc import Iterable
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
