from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "repository-sanitization-v1.yaml"
SCRIPT = ROOT / "scripts" / "audit_repository_sanitization.py"
spec = importlib.util.spec_from_file_location("repository_sanitization", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_contract_preserves_joint_product_and_is_not_oss_extraction() -> None:
    contract = yaml.safe_load(CONTRACT.read_text())
    assert contract["intent"]["oss_extraction"] is False
    assert contract["intent"]["distribution_target"] == "red-hat-intel-joint-product"
    retained = set(contract["retained_boundaries"])
    assert {"red-hat-intel-branding", "showroom-antora-content", "flightpath-control-and-execution-path"} <= retained


def test_contract_forbids_live_and_active_lab_mutation() -> None:
    safety = yaml.safe_load(CONTRACT.read_text())["safety"]
    assert safety["live_cluster_mutation_during_source_cleanup"] == "forbidden"
    assert safety["active_lab_mutation"] == "forbidden"
    assert safety["delete_without_consumer_inventory"] == "forbidden"


def test_inventory_contains_paths_and_counts_but_never_matched_values() -> None:
    report = module.audit()
    assert report["metadata"]["privacy"] == "paths-and-counts-only-no-matched-values"
    assert report["records"]
    for record in report["records"]:
        assert set(record) == {"path", "categories", "disposition", "counts"}
        assert all(isinstance(value, int) for value in record["counts"].values())
        assert record["path"] not in module.GOVERNANCE_PATHS
        assert not record["path"].startswith("evidence/repository-sanitization/")


def test_current_baseline_identifies_legacy_delivery_candidates() -> None:
    records = module.audit()["records"]
    assert not any(record["path"].startswith("backend/app/adapters/rhdp/") for record in records)
    assert not any(record["path"].startswith("deploy/agnosticv/") for record in records)


def test_stargate_capacity_adapter_is_provider_neutral() -> None:
    placement = (ROOT / "backend" / "app" / "services" / "placement.py").read_text()
    assert "app.adapters.stargate.capacity" in placement
    assert "app.adapters.rhdp.stargate_capacity" not in placement
    assert (ROOT / "backend" / "app" / "adapters" / "stargate" / "capacity.py").is_file()
