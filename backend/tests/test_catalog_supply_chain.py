from __future__ import annotations

from pathlib import Path

from app.services.catalog_supply_chain import (
    build_supply_chain_report,
    validate_image_reference,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "config/catalog-artifact-policy.yaml"


def test_image_policy_rejects_mutable_and_execution_cluster_references():
    approved = ["quay.io", "ghcr.io", "registry.redhat.io"]

    assert (
        validate_image_reference(
            "quay.io/example/workload@sha256:" + "a" * 64,
            approved,
        )
        == []
    )
    assert "immutable" in " ".join(
        validate_image_reference("quay.io/example/workload:latest", approved)
    )
    assert "execution-cluster" in " ".join(
        validate_image_reference(
            "image-registry.openshift-image-registry.svc:5000/ns/app@sha256:" + "b" * 64,
            approved,
        )
    )


def test_pilot_catalog_release_policy_is_green_and_complete():
    report = build_supply_chain_report(POLICY, ROOT)

    assert report["status"] == "GREEN-local"
    assert report["catalog_count"] == 3
    assert set(report["catalogs"]) == {
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
        "multi-agent-quickstart",
    }
    assert report["image_count"] >= 5
    assert report["violations"] == []
    for catalog in report["catalogs"].values():
        assert catalog["showroom_content_ref_is_immutable"] is True
        assert catalog["images"]
        assert catalog["violations"] == []


def test_policy_fails_closed_when_a_scanned_artifact_becomes_mutable(tmp_path):
    artifact = tmp_path / "deployment.yaml"
    artifact.write_text("image: quay.io/example/workload:latest\n")
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        """
api_version: launchpad.redhat.com/v1alpha1
approved_registries: [quay.io]
catalogs:
  intel-llm-cpu-serving:
    catalog_path: catalog/intel-llm-cpu-serving/catalog-item.yaml
    artifact_paths:
      - deployment.yaml
""".strip()
        + "\n"
    )

    report = build_supply_chain_report(policy, ROOT, artifact_root=tmp_path)

    assert report["status"] == "RED"
    assert any("immutable" in item for item in report["violations"])


def test_ci_and_local_make_gate_enforce_the_artifact_policy():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    makefile = (ROOT / "Makefile").read_text()

    assert "python scripts/validate_catalog_artifacts.py" in workflow
    assert "catalog-artifact-policy.json" in workflow
    assert "catalog-artifacts:" in makefile
    assert "python3 scripts/validate_catalog_artifacts.py" in makefile
