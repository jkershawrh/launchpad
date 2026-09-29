from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.public_exposure_certification import (
    PUBLIC_RESULT,
    PUBLIC_SCHEMA,
    build_public_certification_plan,
    validate_public_evidence,
)


ROOT = Path(__file__).resolve().parents[2]


def _write_json_with_checksum(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")


def _internal_evidence(catalog_id: str = "example-lab") -> dict:
    return {
        "schema": "launchpad.redhat.com/catalog-certification-evidence/v1",
        "catalog_item_id": catalog_id,
        "result": "GREEN-live",
        "plan": {"seats": 5, "cluster_ref": "flightpath"},
        "rubric": {"passed": True, "score": 100},
        "cleanup": {"status": "completed", "resource_counts": {"namespaces": 0}},
    }


def _intake(catalog_id: str = "example-lab") -> dict:
    return {
        "catalog": {"catalog_item_id": catalog_id, "version": "1.2.3"},
        "runtime": {"allowed_exposure_policies": ["internal", "public_code"]},
        "certification": {"certified_seats": 5, "public_certified_seats": 0},
    }


def _public_evidence(*, internal_sha: str, catalog_id: str = "example-lab") -> dict:
    return {
        "schema": "launchpad.redhat.com/public-exposure-certification-evidence/v1",
        "catalog_item_id": catalog_id,
        "result": "GREEN-live-public-exposure",
        "internal_evidence": {"sha256": internal_sha},
        "plan": {
            "seats": 1,
            "cluster_ref": "flightpath",
            "exposure_policy": "public_code",
            "certification_override": False,
        },
        "identity_and_claim": {
            "plaintext_code_persisted": False,
            "one_time_code_disclosed_once": True,
            "claim_succeeded": True,
            "same_identity_recovered_same_seat": True,
        },
        "participant_journey": {
            "landing": True,
            "showroom": True,
            "declared_tools": True,
            "logout_and_resume": True,
        },
        "authorization": {
            "assigned_namespace_edit": True,
            "cross_namespace_denied": True,
            "unauthenticated_denied": True,
        },
        "edge": {"trusted_tls": True, "external_browser": True},
        "abuse_controls": {"uniform_denial": True, "rate_limit_enforced": True},
        "cleanup": {
            "status": "completed",
            "resource_counts": {
                "namespaces": 0,
                "routes": 0,
                "role_bindings": 0,
                "entitlements": 0,
                "access_policies": 0,
                "argo_applications": 0,
            },
            "identity_disabled_after_final_entitlement": True,
            "model_keys_revoked": True,
        },
        "rubric": {"passed": True, "score": 100},
        "security": {
            "contains_plaintext_credentials": False,
            "participant_email_exported": False,
        },
    }


def test_public_plan_is_one_seat_and_never_uses_scale_override(tmp_path: Path) -> None:
    internal = tmp_path / "internal.json"
    intake = tmp_path / "intake.yaml"
    _write_json_with_checksum(internal, _internal_evidence())
    intake.write_text(yaml.safe_dump(_intake()))

    plan = build_public_certification_plan(
        catalog_id="example-lab", intake_path=intake, internal_evidence_path=internal
    )

    assert plan["seats"] == 1
    assert plan["exposure_policy"] == "public_code"
    assert plan["certification_override"] is False
    assert plan["internal_certified_seats"] == 5
    assert "next_promotion_target" not in plan


def test_versioned_contract_matches_implementation() -> None:
    contract = yaml.safe_load(
        (ROOT / "contracts/public-exposure-certification-v1.yaml").read_text()
    )

    assert contract["spec"]["schema"] == PUBLIC_SCHEMA
    assert contract["spec"]["result"] == PUBLIC_RESULT
    assert contract["spec"]["order"] == {
        "seats": 1,
        "exposurePolicy": "public_code",
        "certificationOverride": False,
    }
    assert contract["spec"]["promotion"]["scaleCertificationChanged"] is False


def test_public_plan_requires_prior_internal_green_and_public_policy(tmp_path: Path) -> None:
    internal = tmp_path / "internal.json"
    intake = tmp_path / "intake.yaml"
    bad = _internal_evidence()
    bad["result"] = "RED-live"
    _write_json_with_checksum(internal, bad)
    intake.write_text(yaml.safe_dump(_intake()))

    with pytest.raises(ValueError, match="internal certification evidence"):
        build_public_certification_plan(
            catalog_id="example-lab", intake_path=intake, internal_evidence_path=internal
        )

    _write_json_with_checksum(internal, _internal_evidence())
    value = _intake()
    value["runtime"]["allowed_exposure_policies"] = ["internal"]
    intake.write_text(yaml.safe_dump(value))
    with pytest.raises(ValueError, match="public_code"):
        build_public_certification_plan(
            catalog_id="example-lab", intake_path=intake, internal_evidence_path=internal
        )


def test_public_evidence_gate_is_separate_and_green(tmp_path: Path) -> None:
    internal = tmp_path / "internal.json"
    public = tmp_path / "public.json"
    intake = tmp_path / "intake.yaml"
    _write_json_with_checksum(internal, _internal_evidence())
    intake.write_text(yaml.safe_dump(_intake()))
    internal_sha = hashlib.sha256(internal.read_bytes()).hexdigest()
    _write_json_with_checksum(public, _public_evidence(internal_sha=internal_sha))

    report = validate_public_evidence(
        catalog_id="example-lab",
        intake_path=intake,
        internal_evidence_path=internal,
        public_evidence_path=public,
    )

    assert report["valid"] is True
    assert report["result"] == "GREEN-live-public-exposure"
    assert report["scale_certification_unchanged"] is True


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("authorization", "cross_namespace_denied"),
        ("edge", "trusted_tls"),
        ("abuse_controls", "rate_limit_enforced"),
        ("cleanup", "identity_disabled_after_final_entitlement"),
    ],
)
def test_public_evidence_fails_closed_on_critical_gate(
    tmp_path: Path, section: str, field: str
) -> None:
    internal = tmp_path / "internal.json"
    public = tmp_path / "public.json"
    intake = tmp_path / "intake.yaml"
    _write_json_with_checksum(internal, _internal_evidence())
    intake.write_text(yaml.safe_dump(_intake()))
    internal_sha = hashlib.sha256(internal.read_bytes()).hexdigest()
    evidence = _public_evidence(internal_sha=internal_sha)
    evidence[section][field] = False
    _write_json_with_checksum(public, evidence)

    with pytest.raises(ValueError, match=f"{section}.{field}"):
        validate_public_evidence(
            catalog_id="example-lab",
            intake_path=intake,
            internal_evidence_path=internal,
            public_evidence_path=public,
        )


def test_public_evidence_rejects_scale_override_and_residue(tmp_path: Path) -> None:
    internal = tmp_path / "internal.json"
    public = tmp_path / "public.json"
    intake = tmp_path / "intake.yaml"
    _write_json_with_checksum(internal, _internal_evidence())
    intake.write_text(yaml.safe_dump(_intake()))
    internal_sha = hashlib.sha256(internal.read_bytes()).hexdigest()
    evidence = _public_evidence(internal_sha=internal_sha)
    evidence["plan"]["certification_override"] = True
    evidence["cleanup"]["resource_counts"]["routes"] = 1
    _write_json_with_checksum(public, evidence)

    with pytest.raises(ValueError) as exc:
        validate_public_evidence(
            catalog_id="example-lab",
            intake_path=intake,
            internal_evidence_path=internal,
            public_evidence_path=public,
        )
    assert "plan.certification_override" in str(exc.value)
    assert "cleanup.resource_counts" in str(exc.value)
