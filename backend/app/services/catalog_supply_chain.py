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
