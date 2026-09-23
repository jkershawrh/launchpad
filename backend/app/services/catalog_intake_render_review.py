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
OVERRIDE_SCHEMA_VERSION = "launchpad.redhat.com/catalog-intake-rendered-output/v2"
MAX_RENDERED_BYTES = 1024 * 1024
MAX_RESOURCES = 500
MAX_STRUCTURE_DEPTH = 64
MAX_STRUCTURE_NODES = 10_000
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SIMPLE_SHELL_VARIABLE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
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
OVERRIDE_RECEIPT_FIELDS = RECEIPT_FIELDS | {"helm_values_sha256"}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous rendered mappings before security inventory runs."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise yaml.constructor.ConstructorError(
                    None, None, "unhashable mapping key", key_node.start_mark
                ) from exc
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    None, None, "duplicate mapping key", key_node.start_mark
                )
        return super().construct_mapping(node, deep=deep)


def _structure_issue(value: Any) -> str | None:
    """Bound YAML alias expansion before recursive manifest inspection."""

    active: set[int] = set()
    visited = 0
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    while stack:
        node, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(node))
            continue
        visited += 1
        if depth > MAX_STRUCTURE_DEPTH or visited > MAX_STRUCTURE_NODES:
            return "render-structure-limit-exceeded"
        if not isinstance(node, (dict, list)):
            continue
        identity = id(node)
        if identity in active:
            return "render-structure-cycle"
        active.add(identity)
        stack.append((node, depth, True))
        children = node.values() if isinstance(node, dict) else node
        children = list(children)
        if visited + len(stack) + len(children) > MAX_STRUCTURE_NODES:
            return "render-structure-limit-exceeded"
        stack.extend((child, depth + 1, False) for child in reversed(children))
    return None


def _has_unresolved_substitution(value: Any) -> bool:
    """Allow simple shell variables only in container command/args list items."""

    stack: list[tuple[Any, tuple[str, ...]]] = [(value, ())]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(key, str) and "${" in key:
                    return True
                stack.append((child, (*path, str(key))))
        elif isinstance(node, list):
            stack.extend((child, (*path, "[]")) for child in node)
        elif isinstance(node, str) and "${" in node:
            shell_argument = (
                len(path) >= 4
                and path[-4] in {"containers", "initContainers"}
                and path[-3] == "[]"
                and path[-2] in {"command", "args"}
                and path[-1] == "[]"
            )
            if not shell_argument or "${" in SIMPLE_SHELL_VARIABLE.sub("", node):
                return True
    return False


def _manifest_findings(output: bytes) -> tuple[list[str], int, int]:
    findings: set[str] = set()
    count = image_count = 0
    if _contains_secret(output):
        findings.add("rendered-secret-pattern")
    if b"{{" in output:
        findings.add("template-unresolved")
    try:
        documents = list(yaml.load_all(output.decode("utf-8"), Loader=_UniqueKeyLoader))
    except (UnicodeDecodeError, yaml.YAMLError, RecursionError):
        return sorted(findings | {"render-output-unparseable"}), 0, 0
    if not documents or len(documents) > MAX_RESOURCES:
        findings.add("render-resource-count-invalid")
    for document in documents[:MAX_RESOURCES]:
        issue = _structure_issue(document)
        if issue:
            return sorted(findings | {issue}), 0, 0
        if _has_unresolved_substitution(document):
            findings.add("template-unresolved")
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
    *,
    expected_helm_values_sha256: str | None = None,
) -> dict[str, Any]:
    """Review a future isolated render; never grant certification or promotion."""
    findings: set[str] = set()
    resource_count = image_count = 0
    override_review = expected_helm_values_sha256 is not None
    schema_version = OVERRIDE_SCHEMA_VERSION if override_review else SCHEMA_VERSION
    receipt_fields = OVERRIDE_RECEIPT_FIELDS if override_review else RECEIPT_FIELDS
    if override_review and (
        not isinstance(expected_helm_values_sha256, str)
        or not DIGEST.fullmatch(expected_helm_values_sha256)
    ):
        findings.add("helm-values-digest-invalid")
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
        if set(render_receipt) != receipt_fields:
            findings.add(
                "render-receipt-extra-fields"
                if set(render_receipt) - receipt_fields
                else "render-receipt-incomplete"
            )
        if render_receipt.get("schema_version") != schema_version:
            findings.add("render-receipt-schema-mismatch")
        if override_review:
            actual_hash = render_receipt.get("helm_values_sha256")
            if not isinstance(actual_hash, str) or actual_hash != expected_helm_values_sha256:
                findings.add("helm-values-digest-mismatch")
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
        "schema_version": schema_version,
        "status": "blocked" if findings else "review-ready",
        "findings": sorted(findings),
        "catalog_item_id": catalog_item_id,
        "source_revision": discovery.revision,
        "helm_values_sha256": (
            render_receipt.get("helm_values_sha256")
            if override_review and isinstance(render_receipt, Mapping)
            else None
        ),
        "manifest_sha256": (
            render_receipt.get("manifest_sha256") if isinstance(render_receipt, Mapping) else None
        ),
        "renderer_image_digest": (
            render_receipt.get("renderer_image_digest")
            if isinstance(render_receipt, Mapping)
            else None
        ),
        "resource_count": resource_count,
        "image_count": image_count,
        "release_eligible": False,
    }
