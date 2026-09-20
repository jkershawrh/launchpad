from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_catalog_intake_worker_safety.py"
CONTRACT = ROOT / "contracts" / "catalog-intake-worker-safety-v1.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("catalog_intake_worker_safety", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def test_repository_contract_is_complete_and_release_blocking() -> None:
    module = load_module()

    report = module.validate(load_contract(), root=ROOT)

    assert report["contract_status"] == "GREEN-local"
    assert report["release_eligible"] is False
    assert report["source_default"] == "deny"
    assert report["egress_default"] == "deny"
    assert report["live_credentials_allowed"] is False
    assert report["pending_verifications"]


def test_source_requires_immutable_sha_and_explicit_authorization() -> None:
    module = load_module()
    contract = load_contract()
    contract["source_policy"]["immutable_revision"]["required"] = False

    with pytest.raises(ValueError, match="immutable"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["source_policy"]["repository_authorization"].pop("approval_record_fields")
    with pytest.raises(ValueError, match="approval record"):
        module.validate(contract, root=ROOT)


def test_payload_rejects_user_credentials_and_sensitive_fields() -> None:
    module = load_module()
    contract = load_contract()
    contract["payload_policy"]["forbidden_key_patterns"].remove("*password*")

    with pytest.raises(ValueError, match="credential patterns"):
        module.validate(contract, root=ROOT)


def test_runtime_requires_unprivileged_read_only_ephemeral_limits() -> None:
    module = load_module()
    contract = load_contract()
    contract["runtime_policy"]["security_context"]["run_as_non_root"] = False

    with pytest.raises(ValueError, match="run as non-root"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["runtime_policy"]["workspace"]["ephemeral"] = False
    with pytest.raises(ValueError, match="ephemeral"):
        module.validate(contract, root=ROOT)


def test_egress_defaults_deny_and_blocks_control_plane_destinations() -> None:
    module = load_module()
    contract = load_contract()
    contract["egress_policy"]["default"] = "allow"

    with pytest.raises(ValueError, match="default deny"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["egress_policy"]["blocked_destination_classes"].remove("kubernetes-api")
    with pytest.raises(ValueError, match="blocked destinations"):
        module.validate(contract, root=ROOT)


def test_worker_has_no_live_catalog_or_cluster_credentials() -> None:
    module = load_module()
    contract = load_contract()
    contract["credential_policy"]["live_credentials_allowed"] = True

    with pytest.raises(ValueError, match="Live credentials"):
        module.validate(contract, root=ROOT)


def test_scanning_logs_evidence_and_cleanup_are_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["scanning_policy"]["on_detection"] = "warn"

    with pytest.raises(ValueError, match="fail closed"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["cleanup_policy"]["receipt_required"] = False
    with pytest.raises(ValueError, match="cleanup receipt"):
        module.validate(contract, root=ROOT)


def test_retry_is_bounded_and_idempotent_without_side_effects() -> None:
    module = load_module()
    contract = load_contract()
    contract["retry_policy"]["max_attempts"] = 0

    with pytest.raises(ValueError, match="attempts"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["retry_policy"]["live_side_effects_allowed"] = True
    with pytest.raises(ValueError, match="side effects"):
        module.validate(contract, root=ROOT)


def test_missing_evidence_and_unknown_verification_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["verification_catalog"][0]["evidence"].append(
        "evidence/does-not-exist/intake-worker.json"
    )

    with pytest.raises(ValueError, match="evidence path does not exist"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["release_policy"]["required_verifications"].append("INTAKE-UNKNOWN")
    with pytest.raises(ValueError, match="unknown verification"):
        module.validate(contract, root=ROOT)


def test_duplicate_ids_and_unsupported_schema_fail_closed() -> None:
    module = load_module()
    contract = load_contract()
    contract["verification_catalog"].append(
        deepcopy(contract["verification_catalog"][0])
    )

    with pytest.raises(ValueError, match="verification ids must be unique"):
        module.validate(contract, root=ROOT)

    contract = load_contract()
    contract["schema_version"] = "unsupported"
    with pytest.raises(ValueError, match="Unsupported worker safety schema"):
        module.validate(contract, root=ROOT)
