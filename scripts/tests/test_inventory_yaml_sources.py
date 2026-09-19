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
    assert all(record["owner"] == "unassigned" for record in records)
    assert all(
        record["proposed_disposition"] == "preserve-pending-owner-review"
        for record in records
    )
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


def test_generated_report_contains_no_yaml_values():
    module = load_module()
    inventory = module.build_inventory()
    report = module.render_markdown(inventory)

    assert "does **not** copy YAML values" in report
    assert "absent detected reference does not prove" in report
    assert "Priority review queues" in report
    assert "deploy/launchpad/base/secrets-template.yaml" in report
    assert "preserve-pending-owner-review" not in report
