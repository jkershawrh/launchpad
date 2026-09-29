#!/usr/bin/env python3
"""Plan and validate a one-seat public exposure certification.

This gate is deliberately separate from catalog scale promotion.  It consumes
an already successful internal certification bundle and never asks Launchpad
for a certification override.  A successful result proves the public identity,
edge, participant journey, authorization, and cleanup path for one seat; it
does not increase ``certified_seats``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


INTERNAL_SCHEMA = "launchpad.redhat.com/catalog-certification-evidence/v1"
PUBLIC_SCHEMA = "launchpad.redhat.com/public-exposure-certification-evidence/v1"
PUBLIC_RESULT = "GREEN-live-public-exposure"


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    if path.suffix in {".yaml", ".yml"}:
        value = yaml.safe_load(path.read_text())
    else:
        value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_checksum(path: Path) -> str:
    checksum = path.with_name(path.name + ".sha256")
    if not checksum.is_file():
        raise ValueError(f"checksum manifest is missing for {path.name}")
    fields = checksum.read_text().strip().split()
    if len(fields) != 2 or fields[1] != path.name:
        raise ValueError(f"checksum manifest is malformed for {path.name}")
    actual = _sha256(path)
    if fields[0] != actual:
        raise ValueError(f"checksum does not match for {path.name}")
    return actual


def _zero_residue(cleanup: Any) -> bool:
    if not isinstance(cleanup, dict) or cleanup.get("status") != "completed":
        return False
    counts = cleanup.get("resource_counts")
    return isinstance(counts, dict) and bool(counts) and all(
        isinstance(value, int) and not isinstance(value, bool) and value == 0
        for value in counts.values()
    )


def _load_internal_green(path: Path, catalog_id: str) -> tuple[dict[str, Any], str]:
    digest = _verify_checksum(path)
    evidence = _load_mapping(path)
    plan = evidence.get("plan") or {}
    rubric = evidence.get("rubric") or {}
    checks = {
        "schema": evidence.get("schema") == INTERNAL_SCHEMA,
        "catalog_item_id": evidence.get("catalog_item_id") == catalog_id,
        "result": evidence.get("result") == "GREEN-live",
        "seats": isinstance(plan.get("seats"), int) and plan["seats"] >= 1,
        "cluster_ref": bool(plan.get("cluster_ref")),
        "rubric": rubric.get("passed") is True and rubric.get("score") == 100,
        "cleanup": _zero_residue(evidence.get("cleanup")),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(
            "internal certification evidence failed: " + ", ".join(failed)
        )
    return evidence, digest


def _validate_intake(intake: dict[str, Any], catalog_id: str) -> int:
    catalog = intake.get("catalog") or {}
    runtime = intake.get("runtime") or {}
    certification = intake.get("certification") or {}
    if catalog.get("catalog_item_id") != catalog_id:
        raise ValueError("intake catalog id does not match")
    policies = runtime.get("allowed_exposure_policies") or []
    if "public_code" not in policies:
        raise ValueError("intake does not allow public_code exposure")
    certified_seats = certification.get("certified_seats", 0)
    if not isinstance(certified_seats, int) or certified_seats < 1:
        raise ValueError("intake has no prior internal seat certification")
    return certified_seats


def build_public_certification_plan(
    *, catalog_id: str, intake_path: Path, internal_evidence_path: Path
) -> dict[str, Any]:
    intake = _load_mapping(intake_path)
    internal, internal_digest = _load_internal_green(
        internal_evidence_path, catalog_id
    )
    certified_seats = _validate_intake(intake, catalog_id)
    cluster_ref = internal["plan"]["cluster_ref"]
    return {
        "schema": "launchpad.redhat.com/public-exposure-certification-plan/v1",
        "catalog_item_id": catalog_id,
        "catalog_version": (intake.get("catalog") or {}).get("version"),
        "cluster_ref": cluster_ref,
        "seats": 1,
        "exposure_policy": "public_code",
        "certification_override": False,
        "internal_certified_seats": certified_seats,
        "internal_evidence": {
            "path": str(internal_evidence_path),
            "sha256": internal_digest,
        },
        "order_request": {
            "catalog_item_id": catalog_id,
            "num_users": 1,
            "target_cluster": cluster_ref,
            "exposure_policy": "public_code",
            "certification_override": False,
        },
        "required_gates": [
            "identity_and_claim",
            "participant_journey",
            "authorization",
            "edge",
            "abuse_controls",
            "cleanup",
        ],
        "scale_promotion": "not-applicable",
    }


def _check_true(
    evidence: dict[str, Any], section: str, fields: tuple[str, ...], failed: list[str]
) -> None:
    value = evidence.get(section)
    if not isinstance(value, dict):
        failed.append(section)
        return
    failed.extend(
        f"{section}.{field}" for field in fields if value.get(field) is not True
    )


def validate_public_evidence(
    *,
    catalog_id: str,
    intake_path: Path,
    internal_evidence_path: Path,
    public_evidence_path: Path,
) -> dict[str, Any]:
    plan = build_public_certification_plan(
        catalog_id=catalog_id,
        intake_path=intake_path,
        internal_evidence_path=internal_evidence_path,
    )
    public_digest = _verify_checksum(public_evidence_path)
    evidence = _load_mapping(public_evidence_path)
    failed: list[str] = []

    expected = {
        "schema": evidence.get("schema") == PUBLIC_SCHEMA,
        "catalog_item_id": evidence.get("catalog_item_id") == catalog_id,
        "result": evidence.get("result") == PUBLIC_RESULT,
        "internal_evidence.sha256": (evidence.get("internal_evidence") or {}).get(
            "sha256"
        )
        == plan["internal_evidence"]["sha256"],
        "plan.seats": (evidence.get("plan") or {}).get("seats") == 1,
        "plan.cluster_ref": (evidence.get("plan") or {}).get("cluster_ref")
        == plan["cluster_ref"],
        "plan.exposure_policy": (evidence.get("plan") or {}).get(
            "exposure_policy"
        )
        == "public_code",
        "plan.certification_override": (evidence.get("plan") or {}).get(
            "certification_override"
        )
        is False,
        "rubric": (evidence.get("rubric") or {}).get("passed") is True
        and (evidence.get("rubric") or {}).get("score") == 100,
        "cleanup.resource_counts": _zero_residue(evidence.get("cleanup")),
        "security.contains_plaintext_credentials": (
            evidence.get("security") or {}
        ).get("contains_plaintext_credentials")
        is False,
        "security.participant_email_exported": (evidence.get("security") or {}).get(
            "participant_email_exported"
        )
        is False,
        "identity_and_claim.plaintext_code_persisted": (
            evidence.get("identity_and_claim") or {}
        ).get("plaintext_code_persisted")
        is False,
    }
    failed.extend(name for name, passed in expected.items() if not passed)
    _check_true(
        evidence,
        "identity_and_claim",
        (
            "one_time_code_disclosed_once",
            "claim_succeeded",
            "same_identity_recovered_same_seat",
        ),
        failed,
    )
    _check_true(
        evidence,
        "participant_journey",
        ("landing", "showroom", "declared_tools", "logout_and_resume"),
        failed,
    )
    _check_true(
        evidence,
        "authorization",
        ("assigned_namespace_edit", "cross_namespace_denied", "unauthenticated_denied"),
        failed,
    )
    _check_true(evidence, "edge", ("trusted_tls", "external_browser"), failed)
    _check_true(
        evidence,
        "abuse_controls",
        ("uniform_denial", "rate_limit_enforced"),
        failed,
    )
    _check_true(
        evidence,
        "cleanup",
        ("identity_disabled_after_final_entitlement", "model_keys_revoked"),
        failed,
    )
    if failed:
        raise ValueError("public exposure evidence failed: " + ", ".join(sorted(set(failed))))
    return {
        "catalog_item_id": catalog_id,
        "result": PUBLIC_RESULT,
        "valid": True,
        "evidence_sha256": public_digest,
        "internal_evidence_sha256": plan["internal_evidence"]["sha256"],
        "scale_certification_unchanged": True,
        "public_certified_seats": 1,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("catalog_id")
        command.add_argument("--intake", required=True, type=Path)
        command.add_argument("--internal-evidence", required=True, type=Path)
        if name == "validate":
            command.add_argument("--public-evidence", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "plan":
            result = build_public_certification_plan(
                catalog_id=args.catalog_id,
                intake_path=args.intake,
                internal_evidence_path=args.internal_evidence,
            )
        else:
            result = validate_public_evidence(
                catalog_id=args.catalog_id,
                intake_path=args.intake,
                internal_evidence_path=args.internal_evidence,
                public_evidence_path=args.public_evidence,
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"public exposure certification failed: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
