from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_security_threat_model.py"
CONTRACT = ROOT / "contracts" / "security-threat-model-v1.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("security_threat_model", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_repository_threat_model_is_complete_and_release_blocking() -> None:
    module = load_module()

    report = module.validate(load_contract(), root=ROOT)

    assert report["contract_status"] == "GREEN-local"
    assert report["release_eligible"] is False
    assert set(report["surfaces"]) == module.REQUIRED_SURFACES
    assert report["unresolved_risks"]["high"] >= 1
    assert report["evidence_links_checked"] >= 10


def test_missing_required_surface_fails_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["surfaces"] = [
        item for item in contract["surfaces"] if item["id"] != "support-access"
    ]

    with pytest.raises(ValueError, match="required surfaces"):
        module.validate(contract, root=ROOT)


def test_dangling_boundary_asset_and_control_references_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    surface = contract["surfaces"][0]
    surface["trust_boundaries"].append("boundary-that-does-not-exist")
    surface["assets"].append("asset-that-does-not-exist")
    surface["threats"][0]["mitigations"].append("control-that-does-not-exist")

    with pytest.raises(ValueError, match="unknown trust boundary|unknown asset|unknown control"):
        module.validate(contract, root=ROOT)


@pytest.mark.parametrize("field", ["mitigations", "verification"])
def test_every_threat_requires_mitigation_and_verification(field: str) -> None:
    module = load_module()
    contract = load_contract()
    contract["surfaces"][0]["threats"][0][field] = []

    with pytest.raises(ValueError, match=field):
        module.validate(contract, root=ROOT)


def test_missing_evidence_path_fails_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["controls"][0]["evidence"].append(
        "evidence/does-not-exist/security-proof.json"
    )

    with pytest.raises(ValueError, match="evidence path does not exist"):
        module.validate(contract, root=ROOT)


def test_unresolved_risk_requires_owner_gate_and_verification_plan() -> None:
    module = load_module()
    contract = load_contract()
    risk = contract["unresolved_risks"][0]
    risk.pop("decision_gate")
    risk.pop("verification_plan")

    with pytest.raises(ValueError, match="decision_gate|verification_plan"):
        module.validate(contract, root=ROOT)


def test_duplicate_ids_and_unsupported_schema_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["assets"].append(deepcopy(contract["assets"][0]))

    with pytest.raises(ValueError, match="asset ids must be unique"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["schema_version"] = "unsupported"
    with pytest.raises(ValueError, match="Unsupported threat-model schema"):
        module.validate(contract, root=ROOT)
