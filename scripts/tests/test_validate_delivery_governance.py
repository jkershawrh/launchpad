from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_delivery_governance.py"


def load_module():
    spec = importlib.util.spec_from_file_location("delivery_governance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contracts() -> tuple[dict, dict]:
    streams = yaml.safe_load(
        (ROOT / "contracts" / "delivery-streams-v1.yaml").read_text(encoding="utf-8")
    )
    matrix = yaml.safe_load(
        (ROOT / "certification" / "convergence-matrix-v1.yaml").read_text(encoding="utf-8")
    )
    return streams, matrix


def test_repository_delivery_governance_is_valid():
    module = load_module()
    streams, matrix = load_contracts()

    report = module.validate(streams, matrix, root=ROOT)

    assert report["valid"] is True
    assert report["stream_count"] == 13
    assert report["initial_active_count"] == 4
    assert report["convergence_stream"] == "convergence-release"
    assert report["contract_count"] == 12
    assert report["scenario_count"] >= 19


def test_unknown_dependency_and_overlapping_ownership_fail_closed():
    module = load_module()
    streams, matrix = load_contracts()
    streams["streams"][0]["depends_on"] = ["not-a-stream"]
    streams["streams"][1]["owned_paths"] = streams["streams"][0]["owned_paths"][:1]

    with pytest.raises(ValueError, match="unknown stream|owned by multiple"):
        module.validate(streams, matrix, root=ROOT)


def test_feature_stream_cannot_authorize_live_mutation():
    module = load_module()
    streams, matrix = load_contracts()
    streams["streams"][0]["live_mutation_policy"] = "approval-gated"

    with pytest.raises(ValueError, match="Only the convergence stream"):
        module.validate(streams, matrix, root=ROOT)


def test_every_scenario_requires_usability_proof():
    module = load_module()
    streams, matrix = load_contracts()
    matrix["scenarios"][0]["proof_dimensions"].remove("usability")

    with pytest.raises(ValueError, match="required proof dimensions"):
        module.validate(streams, matrix, root=ROOT)


def test_product_release_dimensions_are_required():
    module = load_module()
    streams, matrix = load_contracts()
    matrix["release_required_dimensions"].remove("commercial_readiness")

    with pytest.raises(ValueError, match="product release dimensions"):
        module.validate(streams, matrix, root=ROOT)


def test_production_contracts_are_required():
    module = load_module()
    streams, matrix = load_contracts()
    streams["contracts"] = [
        item for item in streams["contracts"] if item["id"] != "gtm-value-attribution-v1"
    ]

    with pytest.raises(ValueError, match="Production delivery contracts"):
        module.validate(streams, matrix, root=ROOT)


def test_production_release_policy_requires_all_contracts():
    module = load_module()
    streams, matrix = load_contracts()
    streams["delivery_policy"]["production_release_requires"].remove("sre-operating-model-v1")

    with pytest.raises(ValueError, match="Production release policy"):
        module.validate(streams, matrix, root=ROOT)


def test_green_scenario_requires_complete_method_evidence():
    module = load_module()
    streams, matrix = load_contracts()
    scenario = matrix["scenarios"][0]
    scenario["state"] = "green-integration"
    scenario["methods"]["tdd"] = "green-integration"
    scenario["evidence"] = []

    with pytest.raises(ValueError, match="evidence|method"):
        module.validate(streams, matrix, root=ROOT)
