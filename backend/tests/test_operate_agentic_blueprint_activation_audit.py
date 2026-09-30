import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = (
    ROOT
    / "evidence/runs/catalog/operate-agentic-blueprint-activation-gate-audit-20260928.json"
)
AUDIT_SHA256_PATH = AUDIT_PATH.with_suffix(".json.sha256")
CATALOG_PATH = ROOT / "catalog/operate-agentic-blueprint/catalog-item.yaml"
TELEMETRY_PATH = ROOT / "contracts/agentic-journey-telemetry-v1.yaml"


def _audit():
    return json.loads(AUDIT_PATH.read_text())


def test_activation_audit_has_matching_hash_manifest():
    expected_hash, expected_name = AUDIT_SHA256_PATH.read_text().split()

    assert expected_name == AUDIT_PATH.name
    assert hashlib.sha256(AUDIT_PATH.read_bytes()).hexdigest() == expected_hash


def test_activation_audit_preserves_scale_and_activation_boundary():
    audit = _audit()
    catalog = yaml.safe_load(CATALOG_PATH.read_text())

    assert audit["decision"] == "SCALE_GREEN_ACTIVATION_GATED"
    assert audit["certified_scale"]["internal_workshop_seats"] == 25
    assert audit["certified_scale"]["public_workshop_seats"] == 1
    assert audit["certified_scale"]["consecutive_green_runs"] == 3
    assert audit["certified_scale"]["zero_residue"] is True
    assert catalog["status"] == "draft"
    # The audit belongs to a prior immutable digest. It remains historical
    # scale evidence and does not raise the current draft candidate's ceiling.
    assert catalog["metadata"]["max_workshop_seats"] == 5
    assert catalog["metadata"]["public_max_workshop_seats"] == 1
    # Two gates were subsequently closed by the correlation/live-policy
    # one-seat release; this historical audit remains immutable.
    assert len(catalog["metadata"]["activation_blockers"]) == 4


def test_activation_audit_references_immutable_green_evidence():
    for reference in _audit()["certified_scale"]["evidence"]:
        evidence_path = ROOT / reference["path"]
        assert evidence_path.is_file()
        assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == reference["sha256"]
        evidence = json.loads(evidence_path.read_text())
        assert evidence["result"] == "GREEN-live"
        assert evidence["cleanup"]["status"] == "completed"
        assert not any(evidence["cleanup"]["resource_counts"].values())


def test_no_unproved_activation_gate_is_green():
    gates = {gate["id"]: gate for gate in _audit()["activation_gates"]}

    assert set(gates) == {
        "same-origin-live-policy",
        "journey-correlation-v1",
        "independent-outage-recovery",
        "opentelemetry-correlated-trace",
        "gitops-drift-and-pipeline-evaluation",
        "approved-intel-xeon-telemetry",
    }
    assert all(gate["status"] in {"RED", "AMBER"} for gate in gates.values())
    assert gates["same-origin-live-policy"]["status"] == "AMBER"
    assert gates["journey-correlation-v1"]["status"] == "RED"
    assert gates["opentelemetry-correlated-trace"]["status"] == "RED"


def test_correlation_audit_names_every_required_contract_field():
    telemetry = yaml.safe_load(TELEMETRY_PATH.read_text())
    correlation_gate = next(
        gate
        for gate in _audit()["activation_gates"]
        if gate["id"] == "journey-correlation-v1"
    )

    assert set(correlation_gate["missing"]) == set(
        telemetry["correlation"]["required_fields"]
    )


def test_personal_registry_images_remain_explicit_production_gates():
    production = _audit()["production_gates"]

    assert len(production) == 2
    assert all(gate["status"] == "RED" for gate in production)
    assert all("quay.io/rh-ee-jkershaw/" in gate["current"] for gate in production)
