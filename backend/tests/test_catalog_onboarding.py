from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.adapters.file.catalog import FileCatalogAdapter
from app.domain.enums import CatalogStatus
from app.services.catalog_onboarding import (
    build_catalog_item,
    discover_quickstart_repo,
    load_intake,
    validate_intake,
)

ROOT = Path(__file__).resolve().parents[2]
INTAKE_PATH = ROOT / "catalog-onboarding/agentops-observability.yaml"
CATALOG_PATH = ROOT / "catalog/agentops-observability/catalog-item.yaml"


def test_agentops_is_registered_as_a_fail_closed_draft():
    intake = load_intake(INTAKE_PATH)
    catalog = yaml.safe_load(CATALOG_PATH.read_text())

    assert catalog == build_catalog_item(intake)
    assert catalog["catalog_item_id"] == "agentops-observability"
    assert catalog["status"] == "draft"
    assert catalog["version"] == "0.1.4"
    assert catalog["metadata"]["certification_stage"] == "twenty-five-seat-certification"
    assert catalog["metadata"]["max_workshop_seats"] == 5
    assert catalog["metadata"]["activation_blockers"]
    assert catalog["metadata"]["showroom_content_repo_url"] == (
        "https://github.com/rhpds/launchpad.git"
    )
    assert catalog["metadata"]["showroom_content_ref"] == (
        "59563b0a77252e8b91077c30c23ab524a8402bce"
    )
    assert catalog["metadata"]["showroom_content_playbook"] == ("site-agentops-observability.yml")
    assert catalog["metadata"]["showroom_content_start_path"] == ("content-agentops-observability")
    assert catalog["metadata"]["workload_repo"] == "https://github.com/rhpds/launchpad.git"
    assert catalog["metadata"]["workload_revision"] == (
        "8596c9e979c76562b5e1239eec2c96e15305568b"
    )
    assert catalog["metadata"]["workload_deploy_path"] == "deploy/workloads/agentops-seat"
    assert catalog["metadata"]["workload_deployment_scope"] == "seat"
    assert catalog["metadata"]["workload_source_kind"] == "launchpad-seat-chart"
    assert catalog["metadata"]["workload_gitops_ready"] is True
    assert catalog["metadata"]["workload_ignore_differences"] == [
        {
            "group": "",
            "kind": "ConfigMap",
            "name": "agentops-pipeline-service-ca",
            "jsonPointers": ["/data"],
        }
    ]
    assert catalog["metadata"]["workload_identity_value_path"] == "identity"
    assert catalog["metadata"]["workload_runtime_secret_name"] == "agentops-runtime"
    assert catalog["metadata"]["workload_readiness"] == [
        {
            "group": "datasciencepipelinesapplications.opendatahub.io",
            "version": "v1",
            "plural": "datasciencepipelinesapplications",
            "name": "dspa",
            "condition_type": "Ready",
            "expected_status": "True",
            "timeout_seconds": 300,
        }
    ]
    assert catalog["metadata"]["source_references"]["automation"]["revision"] == (
        "6ea100531ac869fa66abe69ae223d6b56dbce9a2"
    )
    assert catalog["metadata"]["source_references"]["upstream_showroom"]["revision"] == (
        "f1881c61de55ebf5640c27e76469f4efe458edaf"
    )
    assert catalog["metadata"]["source_references"]["agnosticv"]["path"] == (
        "agd_v2/agentops-intel"
    )


def test_agentops_cannot_be_activated_while_intake_blockers_remain():
    adapter = FileCatalogAdapter(str(ROOT / "catalog"))

    with pytest.raises(ValueError, match="activation blocker"):
        adapter.set_status("agentops-observability", CatalogStatus.ACTIVE)


def test_agentops_intake_captures_the_large_lab_runtime_contract():
    intake = load_intake(INTAKE_PATH)
    runtime = intake["runtime"]
    certification = intake["certification"]

    assert runtime["deployment_type"] == "helm"
    assert runtime["seat_resources"] == {
        "cpu_millicores": 2500,
        "memory_mib": 7168,
        "pods": 12,
        "storage_gib": 30,
    }
    assert runtime["transient_seat_resources"] == {
        "cpu_millicores": 0,
        "memory_mib": 0,
        "pods": 4,
    }
    generated = build_catalog_item(intake)["metadata"]
    assert generated["seat_pods"] == 12
    assert generated["seat_transient_pods"] == 4
    assert runtime["workshop_node_spread"] is True
    assert runtime["workshop_node_min_ready_seconds"] == 900
    assert runtime["workshop_node_headroom_pods"] == 10
    assert runtime["workshop_node_required_labels"] == {
        "launchpad.redhat.com/agentops-certified": "true"
    }
    assert runtime["workshop_provision_concurrency"] == 2
    assert set(runtime["required_capabilities"]) >= {
        "openshift",
        "showroom",
        "model_endpoint",
        "agentops_observability_stack",
        "rhoai",
        "mlflow",
        "user_workload_monitoring",
        "openshift_logging",
        "data_science_pipelines",
    }
    assert "embedding_endpoint" in runtime["required_capabilities"]
    assert runtime["required_models"] == ["granite-3.2-8b-tools"]
    assert [tab["id"] for tab in runtime["tabs"]] == [
        "openshift-console",
        "terminal",
        "mlflow",
        "mortgage-ai",
        "grafana",
        "rhoai",
        "mlflow-docs",
        "rhoai-docs",
    ]
    assert runtime["deployment_scope"] == "seat"
    assert runtime["workload"]["source_kind"] == "launchpad-seat-chart"
    assert runtime["workload"]["identity_value_path"] == "identity"
    assert runtime["workload"]["runtime_secret_value_path"] == "runtime.existingSecret"
    secret_sources = runtime["workload"]["runtime_secret_sources"]
    assert secret_sources["LENDING_DB_PASSWORD"]["source"] == "generated_password"
    assert secret_sources["COMPLIANCE_DB_PASSWORD"]["source"] == "generated_password"
    migration_url = secret_sources["MIGRATION_DATABASE_URL"]["template"]
    assert migration_url.startswith("postgresql+asyncpg://")
    assert "{POSTGRES_PASSWORD}" in migration_url
    assert "{LENDING_DB_PASSWORD}" in secret_sources["DATABASE_URL"]["template"]
    assert "{COMPLIANCE_DB_PASSWORD}" in secret_sources["COMPLIANCE_DATABASE_URL"]["template"]
    assert secret_sources["EMBEDDING_BASE_URL"] == {
        "source": "model_endpoint",
        "model": "nomic-embed-text-v1.5",
    }
    assert certification["promotion_sequence"] == [1, 5, 25]
    blockers = "\n".join(certification["activation_blockers"])
    assert "mutable latest UI bundle" not in blockers
    assert "instead of its original qwen3-14b" not in blockers


def test_validator_accepts_complete_local_source_contract(tmp_path: Path):
    showroom = tmp_path / "showroom"
    content = showroom / "content"
    pages = content / "modules/ROOT/pages"
    pages.mkdir(parents=True)
    (showroom / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: content\n"
    )
    (content / "antora.yml").write_text(
        "name: modules\ntitle: Example\nversion: ~\nnav:\n  - modules/ROOT/nav.adoc\n"
    )
    (content / "modules/ROOT/nav.adoc").write_text("* xref:index.adoc[Start]\n")
    (pages / "index.adoc").write_text("= Start\nimage::diagram.svg[]\n")
    images = content / "modules/ROOT/images"
    images.mkdir(parents=True)
    (images / "diagram.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>\n")

    workload = tmp_path / "workload"
    chart = workload / "deploy/helm/example"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 1.0.0\n")
    (chart / "values.yaml").write_text("replicaCount: 1\n")

    intake = {
        "api_version": "launchpad.redhat.com/v1alpha1",
        "catalog": {
            "catalog_item_id": "example",
            "display_name": "Example",
            "description": "Example catalog intake",
            "category": "guided_build",
            "version": "0.1.0",
        },
        "sources": {
            "showroom": {
                "repo_url": "https://github.com/example/showroom.git",
                "revision": "a" * 40,
                "playbook": "site.yml",
                "start_path": "content",
            },
            "workload": {
                "repo_url": "https://github.com/example/workload.git",
                "revision": "b" * 40,
                "deploy_path": "deploy/helm/example",
            },
        },
        "runtime": {
            "deployment_type": "helm",
            "required_capabilities": ["openshift", "showroom"],
            "required_models": [],
            "seat_resources": {
                "cpu_millicores": 100,
                "memory_mib": 256,
                "pods": 1,
                "storage_gib": 0,
            },
            "tabs": [{"id": "terminal", "title": "Terminal"}],
        },
        "certification": {
            "stage": "intake",
            "max_workshop_seats": 1,
            "promotion_sequence": [1, 5, 25],
            "activation_blockers": ["One-seat live certification is incomplete."],
        },
    }

    report = validate_intake(
        intake,
        showroom_dir=showroom,
        workload_dir=workload,
        catalog=build_catalog_item(intake),
    )

    assert report["validation_status"] == "pass"
    assert report["activation_status"] == "blocked"
    assert report["errors"] == []
    assert report["checks"]["showroom_structure"] == "pass"
    assert report["checks"]["workload_structure"] == "pass"
    assert report["checks"]["catalog_drift"] == "pass"


def test_validator_rejects_mutable_refs_and_missing_showroom_assets(tmp_path: Path):
    showroom = tmp_path / "showroom"
    pages = showroom / "content/modules/ROOT/pages"
    pages.mkdir(parents=True)
    (showroom / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: content\n"
    )
    (showroom / "content/antora.yml").write_text(
        "name: modules\ntitle: Example\nversion: ~\nnav:\n  - modules/ROOT/nav.adoc\n"
    )
    (showroom / "content/modules/ROOT/nav.adoc").write_text("* xref:index.adoc[Start]\n")
    (pages / "index.adoc").write_text("= Start\nimage::missing.png[]\n")

    workload = tmp_path / "workload/deploy/helm/example"
    workload.mkdir(parents=True)
    (workload / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 1\n")
    (workload / "values.yaml").write_text("{}\n")

    intake = load_intake(INTAKE_PATH)
    intake["sources"]["showroom"]["revision"] = "main"
    intake["sources"]["showroom"]["start_path"] = "content"
    intake["sources"]["showroom"]["playbook"] = "site.yml"
    intake["sources"]["workload"]["deploy_path"] = "deploy/helm/example"

    report = validate_intake(
        intake,
        showroom_dir=showroom,
        workload_dir=tmp_path / "workload",
    )

    assert report["validation_status"] == "fail"
    assert any("immutable 40-character Git SHA" in error for error in report["errors"])
    assert any("missing.png" in error for error in report["errors"])


def test_validator_rejects_mutable_reference_and_literal_runtime_secret():
    intake = load_intake(INTAKE_PATH)
    intake["references"]["automation"]["revision"] = "main"
    intake["runtime"]["workload"]["runtime_secret_sources"]["LLM_API_KEY"] = {
        "value": "embedded-secret"
    }

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any("references.automation.revision" in error for error in report["errors"])
    assert any("Sensitive runtime field 'LLM_API_KEY'" in error for error in report["errors"])


def test_validator_rejects_incomplete_runtime_secret_and_identity_contract():
    intake = load_intake(INTAKE_PATH)
    workload = intake["runtime"]["workload"]
    workload["identity_value_path"] = "bad..path"
    workload["runtime_secret_value_path"] = ""

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any("identity_value_path" in error for error in report["errors"])
    assert any("runtime Secret name and value path" in error for error in report["errors"])


def test_validator_rejects_invalid_workshop_provision_concurrency():
    intake = load_intake(INTAKE_PATH)
    intake["runtime"]["workshop_provision_concurrency"] = 0

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any(
        "workshop_provision_concurrency" in error
        for error in report["errors"]
    )


def test_validator_rejects_proof_contract_outside_certification_catalog():
    intake = load_intake(INTAKE_PATH)
    intake["certification"]["proof_contract"] = "../../unsafe.yaml"

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any("certification.proof_contract" in error for error in report["errors"])


def test_validator_rejects_invalid_transient_resource_contract():
    intake = load_intake(INTAKE_PATH)
    intake["runtime"]["transient_seat_resources"] = {
        "cpu_millicores": 0,
        "memory_mib": 0,
        "pods": -1,
    }

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any(
        "runtime.transient_seat_resources.pods" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    "required_labels",
    [
        ["launchpad.redhat.com/agentops-certified=true"],
        {"": "true"},
        {"launchpad.redhat.com/agentops-certified": ""},
        {"launchpad.redhat.com/agentops-certified": True},
    ],
)
def test_validator_rejects_invalid_workshop_node_required_labels(
    required_labels,
):
    intake = load_intake(INTAKE_PATH)
    intake["runtime"]["workshop_node_required_labels"] = required_labels

    report = validate_intake(intake)

    assert report["validation_status"] == "fail"
    assert any(
        "workshop_node_required_labels" in error
        for error in report["errors"]
    )


def test_quickstart_discovery_scaffolds_fail_closed_intake(tmp_path: Path):
    content = tmp_path / "showroom"
    pages = content / "modules/ROOT/pages"
    pages.mkdir(parents=True)
    (tmp_path / "site.yml").write_text(
        "content:\n  sources:\n    - url: .\n      start_path: showroom\n"
    )
    (content / "antora.yml").write_text(
        "name: example\ntitle: Example\nversion: ~\nnav:\n  - modules/ROOT/nav.adoc\n"
    )
    (content / "modules/ROOT/nav.adoc").write_text("* xref:index.adoc[Start]\n")
    (pages / "index.adoc").write_text("= Start\n")

    chart = tmp_path / "deploy/chart"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: example\nversion: 0.1.0\n"
    )
    (chart / "values.yaml").write_text("{}\n")

    intake, report = discover_quickstart_repo(
        tmp_path,
        repo_url="https://github.com/example/quickstart.git",
        revision="a" * 40,
        catalog_id="example-quickstart",
        display_name="Example Quickstart",
    )

    assert report["discovery_status"] == "pass"
    assert report["showroom"]["playbook"] == "site.yml"
    assert report["showroom"]["start_path"] == "showroom"
    assert report["workload"] == {
        "deployment_type": "helm",
        "deploy_path": "deploy/chart",
    }
    assert intake["catalog"]["status"] == "draft"
    assert intake["sources"]["showroom"]["revision"] == "a" * 40
    assert intake["sources"]["workload"]["repo_url"].endswith("quickstart.git")
    assert intake["runtime"]["seat_resources"] == {
        "cpu_millicores": 0,
        "memory_mib": 0,
        "pods": 0,
        "storage_gib": 0,
    }
    blockers = "\n".join(intake["certification"]["activation_blockers"])
    assert "resource measurements" in blockers
    assert "participant tabs" in blockers
    assert validate_intake(intake)["validation_status"] == "pass"
    assert validate_intake(intake)["activation_status"] == "blocked"


def test_quickstart_discovery_fails_closed_without_showroom_or_workload(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Empty quickstart\n")

    intake, report = discover_quickstart_repo(
        tmp_path,
        repo_url="https://github.com/example/empty.git",
        revision="b" * 40,
        catalog_id="empty-quickstart",
        display_name="Empty Quickstart",
    )

    assert report["discovery_status"] == "fail"
    assert any("Antora playbook" in error for error in report["errors"])
    assert any("deployable workload" in error for error in report["errors"])
    assert intake["certification"]["max_workshop_seats"] == 1
