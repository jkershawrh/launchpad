from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "inventory_yaml_sources.py"


def load_module():
    spec = importlib.util.spec_from_file_location("inventory_yaml_sources", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_is_complete_and_fail_closed():
    module = load_module()
    inventory = module.build_inventory()
    tracked_yaml = {
        path
        for path in module.tracked_files()
        if path.endswith(module.YAML_SUFFIXES)
    }
    records = inventory["records"]

    assert {record["path"] for record in records} == tracked_yaml
    assert inventory["summary"]["tracked_yaml_files"] == len(tracked_yaml)
    assert inventory["source_state"] == "working-tree"
    assert isinstance(inventory["tracked_changes_present"], bool)
    assert all(record["proposed_disposition"].startswith("preserve-") for record in records)
    assert all(record["deletion_eligible"] is False for record in records)
    assert inventory["summary"]["deletion_eligible"] == 0
    assert inventory["summary"]["unassigned_owners"] == 0
    assert "No record authorizes deletion" in inventory["safety_boundary"]
    assert all(
        not module.GENERATED_REFERENCE_OUTPUTS.intersection(record["referenced_by"])
        for record in records
    )


def test_classification_keeps_evidence_and_source_distinct():
    module = load_module()

    assert module.classify("evidence/public-access/example.yaml") == "evidence"
    assert module.classify("deploy/launchpad/base/service.yaml") == "deployment-source"
    assert module.classify("deploy/workloads/example/templates/pod.yaml") == "deployment-template"
    assert module.classify("fixtures/events/example.yaml") == "fixture"
    assert module.classify("contracts/example.yaml") == "contract"


def test_governance_protects_active_and_legacy_sources():
    module = load_module()

    assert module.governance("catalog/example/catalog-item.yaml", "catalog-source") == {
        "owner": "catalog-release-owner",
        "protection_class": "catalog-release-input",
        "proposed_disposition": "preserve-release-input",
    }
    legacy = module.governance(
        "deploy/agnosticv/example/common.yaml", "deployment-source"
    )
    assert legacy["owner"] == "legacy-integration-owner"
    assert legacy["proposed_disposition"] == (
        "preserve-pending-external-consumer-review"
    )
    repository_configuration = module.governance(
        ".github/dependabot.yml", "repository-configuration"
    )
    assert repository_configuration["owner"] == "repository-maintenance-owner"
    assert (
        repository_configuration["protection_class"]
        == "repository-governance-input"
    )


def test_dependency_flags_distinguish_runtime_sources_from_legacy_automation():
    module = load_module()

    assert module._dependency_flags(
        "deploy/launchpad/overlays/arena/argocd-application.yaml",
        "repoURL: https://github.com/rhpds/launchpad.git\n",
    ) == ["rhpds-git-dependency"]
    assert module._dependency_flags(
        "config/clusters.yaml",
        "image: quay.io/rhpds/git-cloner@sha256:abc\n",
    ) == ["rhpds-image-dependency"]
    assert module._dependency_flags(
        "deploy/agnosticv/example/common.yaml",
        "role: agnosticd.showroom.ocp4_workload_showroom\n",
    ) == ["agnostic-automation-dependency"]
    assert module._dependency_flags(
        "content-agentops-observability/supplemental-ui/partials/head-meta.hbs",
        "https://cdn.jsdelivr.net/gh/rhpds/ocp-zt-tenant-showroom@main/site.css",
    ) == ["rhpds-git-dependency"]


def test_inventory_reports_dependency_counts_without_copying_values():
    module = load_module()
    inventory = module.build_inventory()

    assert inventory["summary"]["dependency_flag_counts"]["rhpds-git-dependency"] > 0
    assert any(record["dependency_flags"] for record in inventory["records"])
    assert "Red Hat-hosted and RHDP dependency review" in module.render_markdown(inventory)
    assert "Protection classes" in module.render_markdown(inventory)


def test_generated_report_contains_no_yaml_values():
    module = load_module()
    inventory = module.build_inventory()
    report = module.render_markdown(inventory)

    assert "does **not** copy YAML values" in report
    assert "absent detected reference does not prove" in report
    assert "Priority review queues" in report
    assert "deploy/launchpad/base/secrets-template.yaml" in report
    assert "preserve-pending-owner-review" not in report


def test_freshness_check_preserves_recorded_generation_provenance():
    module = load_module()
    current = {
        "source_commit": "current-head",
        "source_state": "working-tree",
        "tracked_changes_present": False,
        "records": [{"path": "contracts/example.yaml"}],
    }
    recorded = {
        "source_commit": "generation-base",
        "source_state": "working-tree",
        "tracked_changes_present": True,
    }

    result = module._preserve_recorded_provenance(current, recorded)

    assert result["source_commit"] == "generation-base"
    assert result["tracked_changes_present"] is True
    assert result["records"] == [{"path": "contracts/example.yaml"}]
