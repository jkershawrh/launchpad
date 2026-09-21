from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from app.domain.catalog_intake_discovery import (
    CatalogIntakeCleanupReceipt,
    CatalogIntakeDiscoveryReceipt,
)
from app.services.catalog_intake_render_review import review_rendered_output

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://github.com/example/support-assistant.git"
REVISION = "a" * 40
SAFE_MANIFEST = (
    "apiVersion: apps/v1\nkind: Deployment\n"
    "metadata:\n  name: support-assistant\n"
    "spec:\n  template:\n    spec:\n      containers:\n"
    "        - name: app\n"
    "          image: quay.io/example/support@sha256:" + "b" * 64 + "\n"
).encode()


def _discovery() -> CatalogIntakeDiscoveryReceipt:
    now = datetime.now(UTC)
    return CatalogIntakeDiscoveryReceipt(
        intake_id="intake-support",
        attempt_id="attempt-1",
        idempotency_key="sha256:" + "c" * 64,
        repository_url=SOURCE,
        revision=REVISION,
        policy_version="1.0.0",
        source_approval_id="approval-1",
        worker_image_digest="sha256:" + "d" * 64,
        started_at=now,
        finished_at=now,
        status="passed",
        scan_summary={"files_scanned": 10, "bytes_scanned": 1000},
        output_hash="sha256:" + "e" * 64,
        draft_intake={"catalog": {"catalog_item_id": "support-assistant"}},
        cleanup=CatalogIntakeCleanupReceipt(
            receipt_id="sha256:" + "f" * 64,
            attempt_id="attempt-1",
            workspace_removed=True,
            result="pass",
        ),
    )


def _render_receipt(manifests: bytes = SAFE_MANIFEST) -> dict:
    return {
        "schema_version": "launchpad.redhat.com/catalog-intake-rendered-output/v1",
        "repository_url": SOURCE,
        "revision": REVISION,
        "catalog_item_id": "support-assistant",
        "source_approval_id": "approval-1",
        "discovery_output_hash": "sha256:" + "e" * 64,
        "renderer_image_digest": "sha256:" + "1" * 64,
        "render_status": "passed",
        "network_egress_denied": True,
        "workspace_removed": True,
        "manifest_sha256": "sha256:" + hashlib.sha256(manifests).hexdigest(),
    }


def test_missing_render_receipt_stays_blocked() -> None:
    report = review_rendered_output(_discovery(), None, None)

    assert report["status"] == "blocked"
    assert report["findings"] == ["render-receipt-missing"]
    assert report["release_eligible"] is False


def test_source_mismatch_and_digest_mismatch_fail_closed() -> None:
    receipt = _render_receipt()
    receipt["revision"] = "b" * 40
    mismatched = review_rendered_output(_discovery(), receipt, SAFE_MANIFEST)

    assert "source-identity-mismatch" in mismatched["findings"]
    assert mismatched["status"] == "blocked"

    receipt = _render_receipt()
    tampered = review_rendered_output(_discovery(), receipt, SAFE_MANIFEST + b"# tampered\n")
    assert "render-output-digest-mismatch" in tampered["findings"]
    assert tampered["status"] == "blocked"


def test_safe_manifest_is_review_ready_but_never_promotion_eligible() -> None:
    report = review_rendered_output(_discovery(), _render_receipt(), SAFE_MANIFEST)

    assert report["status"] == "review-ready"
    assert report["resource_count"] == 1
    assert report["findings"] == []
    assert report["release_eligible"] is False


def test_unsafe_rendered_content_is_blocked_without_echoing_values() -> None:
    leaked = "sk-test-secret-do-not-echo"
    unsafe = (
        "apiVersion: v1\nkind: Secret\nmetadata: {name: credentials}\n"
        f"stringData: {{token: {leaked}}}\n"
    ).encode()
    report = review_rendered_output(_discovery(), _render_receipt(unsafe), unsafe)

    assert report["status"] == "blocked"
    assert "secret-resource" in report["findings"]
    assert leaked not in str(report)


def test_render_review_rejects_mutable_images_and_privileged_resources() -> None:
    unsafe = (
        b"apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: unsafe}\n"
        b"spec:\n  template:\n    spec:\n      hostNetwork: true\n"
        b"      containers:\n        - name: app\n          image: quay.io/example/app:latest\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(unsafe), unsafe)

    assert report["status"] == "blocked"
    assert "host-privilege-required" in report["findings"]
    assert "mutable-or-invalid-image" in report["findings"]


def test_render_review_rejects_unresolved_template_and_cluster_scope() -> None:
    unsafe = (
        b"apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRole\n"
        b"metadata: {name: '{{ .Values.roleName }}'}\nrules: []\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(unsafe), unsafe)

    assert report["status"] == "blocked"
    assert "template-unresolved" in report["findings"]
    assert "cluster-scoped-resource" in report["findings"]


def test_render_review_rejects_external_network_exposure_without_echoing_hosts() -> None:
    hostname = "private-training.example.test"
    unsafe = f"""apiVersion: route.openshift.io/v1
kind: Route
metadata: {{name: fixed-route}}
spec: {{host: {hostname}}}
---
apiVersion: v1
kind: Service
metadata: {{name: public-service}}
spec: {{type: LoadBalancer, ports: [{{port: 443}}]}}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata: {{name: fixed-ingress}}
spec: {{rules: [{{host: {hostname}}}]}}
""".encode()

    report = review_rendered_output(_discovery(), _render_receipt(unsafe), unsafe)

    assert report["status"] == "blocked"
    assert "network-exposure-unresolved" in report["findings"]
    assert hostname not in str(report)
    assert report["release_eligible"] is False


def test_render_review_rejects_malformed_network_spec() -> None:
    unsafe = (
        b"apiVersion: v1\nkind: Service\nmetadata: {name: malformed}\n"
        b"spec: []\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(unsafe), unsafe)

    assert report["status"] == "blocked"
    assert "network-exposure-unresolved" in report["findings"]


@pytest.mark.parametrize(
    "rendered",
    [
        b"apiVersion: v1\nkind: Secret\nkind: ConfigMap\nmetadata: {name: hidden}\n",
        (
            b"apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: hidden}\n"
            b"spec:\n  template:\n    spec:\n      hostNetwork: true\n"
            b"      hostNetwork: false\n"
        ),
    ],
)
def test_render_review_rejects_duplicate_yaml_keys(rendered: bytes) -> None:
    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "blocked"
    assert "render-output-unparseable" in report["findings"]
    assert report["release_eligible"] is False


@pytest.mark.parametrize(
    "kind,spec",
    [
        ("Service", "type: NodePort"),
        ("Service", "type: ExternalName\n  externalName: other.example.test"),
        ("Service", "externalIPs: [192.0.2.4]"),
        ("Route", "subdomain: training"),
        ("Ingress", "tls: [{hosts: [training.example.test]}]"),
    ],
)
def test_render_review_covers_alternate_network_exposure(kind: str, spec: str) -> None:
    rendered = (
        f"apiVersion: v1\nkind: {kind}\nmetadata: {{name: network}}\nspec:\n  {spec}\n"
    ).encode()

    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "blocked"
    assert "network-exposure-unresolved" in report["findings"]
    assert "training.example.test" not in str(report)


def test_render_review_allows_internal_cluster_ip_service() -> None:
    rendered = (
        b"apiVersion: v1\nkind: Service\nmetadata: {name: internal}\n"
        b"spec: {type: ClusterIP, ports: [{port: 8080}]}\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "review-ready"
    assert report["release_eligible"] is False


def test_render_review_rejects_recursive_yaml_alias_without_crashing() -> None:
    recursive = (
        b"apiVersion: apps/v1\nkind: Deployment\n"
        b"metadata: {name: recursive}\n"
        b"spec:\n  loop: &loop\n    self: *loop\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(recursive), recursive)

    assert report["status"] == "blocked"
    assert "render-structure-cycle" in report["findings"]
    assert report["release_eligible"] is False


def test_render_review_rejects_excessive_yaml_depth() -> None:
    nested = "leaf: value\n"
    for _ in range(70):
        nested = "nested:\n" + "".join("  " + line for line in nested.splitlines(True))
    rendered = (
        "apiVersion: apps/v1\nkind: Deployment\n"
        "metadata: {name: deep}\nspec:\n" +
        "".join("  " + line for line in nested.splitlines(True))
    ).encode()

    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "blocked"
    assert "render-structure-limit-exceeded" in report["findings"]


def test_render_review_allows_bounded_nonrecursive_alias() -> None:
    rendered = (
        b"apiVersion: apps/v1\nkind: Deployment\n"
        b"metadata: {name: shared}\n"
        b"spec:\n  first: &common {replicas: 1}\n  second: *common\n"
    )

    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "review-ready"
    assert report["release_eligible"] is False


def test_render_review_rejects_excessive_yaml_breadth() -> None:
    fields = "".join(f"  key{index}: value\n" for index in range(10_001))
    rendered = (
        "apiVersion: apps/v1\nkind: Deployment\n"
        "metadata: {name: wide}\nspec:\n" + fields
    ).encode()

    report = review_rendered_output(_discovery(), _render_receipt(rendered), rendered)

    assert report["status"] == "blocked"
    assert "render-structure-limit-exceeded" in report["findings"]


def test_oversized_output_is_rejected_before_parsing() -> None:
    oversized = SAFE_MANIFEST + b" " * (1024 * 1024)

    report = review_rendered_output(_discovery(), _render_receipt(oversized), oversized)

    assert report["status"] == "blocked"
    assert report["findings"] == ["render-output-size-invalid"]
    assert report["resource_count"] == 0


def test_failed_isolation_and_unknown_receipt_fields_are_not_accepted() -> None:
    receipt = _render_receipt()
    receipt["network_egress_denied"] = False
    receipt["token"] = "do-not-copy"
    report = review_rendered_output(_discovery(), receipt, SAFE_MANIFEST)

    assert report["status"] == "blocked"
    assert "render-isolation-unverified" in report["findings"]
    assert "render-receipt-extra-fields" in report["findings"]
    assert "do-not-copy" not in str(report)


def test_malformed_discovery_draft_fails_closed_without_exception() -> None:
    discovery = _discovery().model_copy(update={"draft_intake": {"catalog": []}})

    report = review_rendered_output(discovery, _render_receipt(), SAFE_MANIFEST)

    assert report["status"] == "blocked"
    assert "discovery-not-proven" in report["findings"]


def test_render_review_contract_does_not_authorize_host_render_or_promotion() -> None:
    contract = yaml.safe_load(
        (ROOT / "contracts/catalog-intake-rendered-output-v1.yaml").read_text()
    )

    assert contract["authority"]["may_render_untrusted_source_on_host"] is False
    assert contract["authority"]["may_publish_catalog"] is False
    assert contract["authority"]["review_ready_is_certified"] is False
    assert any("fixed ingress hosts" in check for check in contract["checks"])
    assert contract["input"]["maximum_yaml_structure_depth"] == 64
    assert contract["input"]["maximum_yaml_structure_nodes_per_document"] == 10000
