from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_audit_integrity_retention.py"
CONTRACT = ROOT / "contracts" / "audit-integrity-retention-v1.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_integrity_retention", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_repository_audit_contract_is_complete_and_release_blocking() -> None:
    module = load_module()

    report = module.validate(load_contract(), root=ROOT)

    assert report["contract_status"] == "GREEN-local"
    assert report["release_eligible"] is False
    assert set(report["retention_classes"]) == module.REQUIRED_RETENTION_CLASSES
    assert set(report["event_fields"]) >= module.REQUIRED_EVENT_FIELDS
    assert report["append_only"] is True
    assert report["pending_verifications"]


def test_missing_accountability_field_fails_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["event_schema"]["fields"].pop("actor")

    with pytest.raises(ValueError, match="event fields"):
        module.validate(contract, root=ROOT)


def test_integrity_requires_append_only_hash_chain_and_canonicalization() -> None:
    module = load_module()
    contract = load_contract()
    contract["integrity"]["append_only"] = False
    contract["integrity"].pop("canonicalization")
    contract["integrity"].pop("previous_hash_field")

    with pytest.raises(ValueError, match="append-only|canonicalization|previous_hash"):
        module.validate(contract, root=ROOT)


def test_redaction_must_cover_secrets_pii_and_raw_model_content() -> None:
    module = load_module()
    contract = load_contract()
    contract["redaction"]["forbidden_data_classes"].remove("credential-secret")

    with pytest.raises(ValueError, match="forbidden data classes"):
        module.validate(contract, root=ROOT)


def test_retention_classes_require_owner_duration_disposition_and_hold() -> None:
    module = load_module()
    contract = load_contract()
    retention = contract["retention_classes"][0]
    retention.pop("owner")
    retention.pop("minimum_days")
    retention.pop("disposition")
    retention.pop("legal_hold_eligible")

    with pytest.raises(ValueError, match="owner|minimum_days|disposition|legal_hold"):
        module.validate(contract, root=ROOT)


def test_export_and_access_require_named_ownership_and_separation() -> None:
    module = load_module()
    contract = load_contract()
    contract["access"]["roles"][0]["permissions"].append("delete")
    contract["export"].pop("owner")

    with pytest.raises(ValueError, match="append-only producer|Export requires owner"):
        module.validate(contract, root=ROOT)


def test_deletion_and_legal_hold_are_explicit_and_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["deletion"]["allow_early_delete"] = True
    contract["legal_hold"]["overrides_deletion"] = False

    with pytest.raises(ValueError, match="early deletion|Legal hold"):
        module.validate(contract, root=ROOT)


def test_missing_evidence_and_dangling_verification_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["verification_catalog"][0]["evidence"].append(
        "evidence/does-not-exist/audit-proof.json"
    )

    with pytest.raises(ValueError, match="evidence path does not exist"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["release_policy"]["required_verifications"].append("AUDIT-UNKNOWN")
    with pytest.raises(ValueError, match="unknown verification"):
        module.validate(contract, root=ROOT)


def test_duplicate_ids_and_unsupported_schema_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["retention_classes"].append(deepcopy(contract["retention_classes"][0]))

    with pytest.raises(ValueError, match="retention class ids must be unique"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["schema_version"] = "unsupported"
    with pytest.raises(ValueError, match="Unsupported audit contract schema"):
        module.validate(contract, root=ROOT)
