from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

import yaml

from app.domain.catalog_intake_discovery import CatalogIntakeDiscoveryReceipt
from app.services.catalog_intake_discovery import _contains_secret
from app.services.catalog_onboarding import (
    CLUSTER_SCOPED_KINDS,
    IMMUTABLE_IMAGE,
    _network_exposure_inventory,
    _walk_mappings,
)

SCHEMA_VERSION = "launchpad.redhat.com/catalog-intake-rendered-output/v1"
MAX_RENDERED_BYTES = 1024 * 1024
MAX_RESOURCES = 500
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_FIELDS = {
    "schema_version",
    "repository_url",
    "revision",
    "catalog_item_id",
    "source_approval_id",
    "discovery_output_hash",
    "renderer_image_digest",
    "render_status",
    "network_egress_denied",
    "workspace_removed",
    "manifest_sha256",
}


def _manifest_findings(output: bytes) -> tuple[list[str], int, int]:
    findings: set[str] = set()
    count = image_count = 0
    if _contains_secret(output):
        findings.add("rendered-secret-pattern")
    if b"{{" in output or b"${" in output:
        findings.add("template-unresolved")
    try:
        documents = list(yaml.safe_load_all(output.decode("utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError):
        return sorted(findings | {"render-output-unparseable"}), 0, 0
    if not documents or len(documents) > MAX_RESOURCES:
        findings.add("render-resource-count-invalid")
    network_inventory: dict[str, list[Any]] = {"network_exposure": []}
    for document in documents[:MAX_RESOURCES]:
        if not isinstance(document, dict):
            findings.add("render-resource-invalid")
            continue
        kind = document.get("kind")
        metadata = document.get("metadata")
        if (
            not isinstance(document.get("apiVersion"), str)
            or not isinstance(kind, str)
            or not isinstance(metadata, dict)
            or not isinstance(metadata.get("name"), str)
        ):
            findings.add("render-resource-invalid")
            continue
        count += 1
        if kind == "Secret":
            findings.add("secret-resource")
        if kind in CLUSTER_SCOPED_KINDS or kind.startswith("Cluster"):
            findings.add("cluster-scoped-resource")
        _network_exposure_inventory(document, "rendered-output", network_inventory)
        for mapping in _walk_mappings(document):
            if any(mapping.get(field) is True for field in ("hostNetwork", "hostPID", "hostIPC")):
                findings.add("host-privilege-required")
            if mapping.get("privileged") is True or isinstance(mapping.get("hostPath"), dict):
                findings.add("host-privilege-required")
            image = mapping.get("image")
            if image is not None:
                image_count += 1
                if not isinstance(image, str) or not IMMUTABLE_IMAGE.fullmatch(image):
                    findings.add("mutable-or-invalid-image")
    if network_inventory["network_exposure"]:
        findings.add("network-exposure-unresolved")
    return sorted(findings), count, image_count


def review_rendered_output(
    discovery: CatalogIntakeDiscoveryReceipt,
    render_receipt: Mapping[str, Any] | None,
    rendered_output: bytes | None,
) -> dict[str, Any]:
    """Review a future isolated render; never grant certification or promotion."""
    findings: set[str] = set()
    resource_count = image_count = 0
    if (
        discovery.status != "passed"
        or discovery.cleanup.result != "pass"
        or not discovery.cleanup.workspace_removed
        or not discovery.output_hash
    ):
        findings.add("discovery-not-proven")
    draft = discovery.draft_intake
    catalog = draft.get("catalog") if isinstance(draft, dict) else None
    catalog_item_id = catalog.get("catalog_item_id") if isinstance(catalog, dict) else None
    if not isinstance(catalog_item_id, str) or not catalog_item_id:
        findings.add("discovery-not-proven")
    if render_receipt is None:
        findings.add("render-receipt-missing")
    elif not isinstance(render_receipt, Mapping):
        findings.add("render-receipt-invalid")
    else:
        if set(render_receipt) != RECEIPT_FIELDS:
            findings.add(
                "render-receipt-extra-fields"
                if set(render_receipt) - RECEIPT_FIELDS
                else "render-receipt-incomplete"
            )
        if render_receipt.get("schema_version") != SCHEMA_VERSION:
            findings.add("render-receipt-schema-mismatch")
        expected = {
            "repository_url": discovery.repository_url,
            "revision": discovery.revision,
            "catalog_item_id": catalog_item_id,
            "source_approval_id": discovery.source_approval_id,
            "discovery_output_hash": discovery.output_hash,
        }
        if any(render_receipt.get(key) != value for key, value in expected.items()):
            findings.add("source-identity-mismatch")
        renderer_digest = render_receipt.get("renderer_image_digest")
        if not isinstance(renderer_digest, str) or not DIGEST.fullmatch(renderer_digest):
            findings.add("renderer-identity-invalid")
        if render_receipt.get("render_status") != "passed":
            findings.add("render-not-passed")
        if (
            render_receipt.get("network_egress_denied") is not True
            or render_receipt.get("workspace_removed") is not True
        ):
            findings.add("render-isolation-unverified")
    if rendered_output is None:
        if render_receipt is not None:
            findings.add("render-output-missing")
    elif (
        not isinstance(rendered_output, bytes)
        or not rendered_output
        or len(rendered_output) > MAX_RENDERED_BYTES
    ):
        findings.add("render-output-size-invalid")
    else:
        digest = "sha256:" + hashlib.sha256(rendered_output).hexdigest()
        if (
            not isinstance(render_receipt, Mapping)
            or render_receipt.get("manifest_sha256") != digest
        ):
            findings.add("render-output-digest-mismatch")
        manifest_findings, resource_count, image_count = _manifest_findings(rendered_output)
        findings.update(manifest_findings)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked" if findings else "review-ready",
        "findings": sorted(findings),
        "resource_count": resource_count,
        "image_count": image_count,
        "release_eligible": False,
    }
