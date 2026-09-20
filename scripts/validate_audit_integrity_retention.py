#!/usr/bin/env python3
"""Fail-closed validation for Launchpad audit integrity and retention policy."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "audit-integrity-retention-v1.yaml"
REQUIRED_EVENT_FIELDS = {
    "schema_version",
    "event_id",
    "event_type",
    "occurred_at",
    "actor",
    "action",
    "target",
    "outcome",
    "correlation",
    "source",
    "sequence",
    "previous_hash",
    "payload_hash",
    "retention_class",
    "payload",
}
REQUIRED_RETENTION_CLASSES = {
    "security-access",
    "lifecycle-mutation",
    "model-inference",
    "evidence-export",
}
REQUIRED_FORBIDDEN_DATA_CLASSES = {
    "credential-secret",
    "direct-email",
    "private-key",
    "raw-model-output",
    "raw-prompt",
    "session-token",
}
REQUIRED_EXPORT_FIELDS = {
    "export_id",
    "requested_by",
    "approved_by",
    "purpose",
    "query_hash",
    "produced_at",
    "event_count",
    "first_sequence",
    "last_sequence",
    "content_hash",
    "retention_class",
}
SEVERITIES = {"critical", "high", "moderate", "low"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _indexed(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    ids = [str(item.get("id", "")).strip() for item in items]
    _require(all(ids), f"Every {kind} requires an id")
    _require(len(ids) == len(set(ids)), f"{kind} ids must be unique")
    return {item["id"]: item for item in items}


def _check_evidence(
    evidence: list[str], *, root: Path, owner: str
) -> tuple[list[str], int]:
    _require(evidence, f"{owner} requires verification evidence")
    checked: list[str] = []
    for raw_path in evidence:
        path = str(raw_path).strip()
        _require(path, f"{owner} contains an empty evidence path")
        _require(
            (root / path).is_file(),
            f"{owner} evidence path does not exist: {path}",
        )
        checked.append(path)
    return checked, len(checked)


def validate(contract: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require(
        contract.get("schema_version")
        == "launchpad.redhat.com/audit-integrity-retention/v1",
        "Unsupported audit contract schema",
    )
    _require(
        contract.get("kind") == "LaunchpadAuditIntegrityRetentionPolicy",
        "Unsupported audit contract kind",
    )
    metadata = contract.get("metadata") or {}
    for field in (
        "id",
        "version",
        "owner",
        "data_governance_owner",
        "review_policy",
    ):
        _require(metadata.get(field), f"Audit metadata requires {field}")

    event_schema = contract.get("event_schema") or {}
    _require(event_schema.get("version"), "Event schema requires version")
    _require(
        "correction" in str(event_schema.get("append_semantics", "")).lower(),
        "Event schema must define append-only correction semantics",
    )
    fields = event_schema.get("fields") or {}
    _require(
        REQUIRED_EVENT_FIELDS <= set(fields),
        "Audit event fields are incomplete",
    )
    for field_name in REQUIRED_EVENT_FIELDS:
        field = fields[field_name] or {}
        _require(field.get("type"), f"Event field {field_name} requires type")
        _require(
            field.get("required") is True,
            f"Event field {field_name} must be required",
        )
        _require(
            field.get("classification"),
            f"Event field {field_name} requires classification",
        )
    actor = event_schema.get("actor_contract") or {}
    _require(
        {"actor_type", "actor_id_hash", "authentication_context"}
        <= set(actor.get("required") or []),
        "Actor contract is incomplete",
    )
    _require(actor.get("raw_email_allowed") is False, "Raw actor email is forbidden")
    _require(actor.get("shared_identity_allowed") is False, "Shared actors are forbidden")
    target = event_schema.get("target_contract") or {}
    _require(
        {"target_type", "target_id"} <= set(target.get("required") or []),
        "Target contract is incomplete",
    )
    correlation = event_schema.get("correlation_contract") or {}
    _require(
        "trace_id" in (correlation.get("required") or []),
        "Correlation contract requires trace_id",
    )
    _require(event_schema.get("outcome_values"), "Outcome values are required")

    redaction = contract.get("redaction") or {}
    _require(redaction.get("owner"), "Redaction requires owner")
    _require(
        redaction.get("default") == "deny-unclassified-fields",
        "Redaction must deny unclassified fields",
    )
    _require(
        REQUIRED_FORBIDDEN_DATA_CLASSES
        <= set(redaction.get("forbidden_data_classes") or []),
        "Redaction forbidden data classes are incomplete",
    )
    _require(redaction.get("recursive_key_patterns"), "Recursive redaction patterns required")
    _require(redaction.get("failure_behavior"), "Redaction failure behavior required")

    retention = _indexed(contract.get("retention_classes") or [], "retention class")
    _require(
        set(retention) == REQUIRED_RETENTION_CLASSES,
        "Required retention classes are incomplete",
    )
    for retention_id, item in retention.items():
        for field in ("owner", "minimum_days", "maximum_days", "disposition"):
            _require(item.get(field), f"Retention class {retention_id} requires {field}")
        _require(
            int(item["minimum_days"]) <= int(item["maximum_days"]),
            f"Retention class {retention_id} has invalid duration",
        )
        _require(
            item.get("legal_hold_eligible") is True,
            f"Retention class {retention_id} requires legal_hold eligibility",
        )

    integrity = contract.get("integrity") or {}
    _require(integrity.get("owner"), "Integrity requires owner")
    _require(integrity.get("append_only") is True, "Audit storage must be append-only")
    _require(
        "forbidden" in str(integrity.get("mutation_policy", "")).lower(),
        "Audit mutation policy must forbid update and delete",
    )
    _require(integrity.get("algorithm") == "sha256", "Integrity algorithm must be sha256")
    for field in (
        "canonicalization",
        "sequence_field",
        "previous_hash_field",
        "payload_hash_field",
        "chain_scope",
        "segment_anchor",
        "correction_policy",
        "verification_frequency",
    ):
        _require(integrity.get(field), f"Integrity requires {field}")
    _require(
        integrity["sequence_field"] in fields,
        "Integrity sequence field is absent from event schema",
    )
    _require(
        integrity["previous_hash_field"] in fields,
        "Integrity previous_hash field is absent from event schema",
    )
    _require(
        integrity["payload_hash_field"] in fields,
        "Integrity payload_hash field is absent from event schema",
    )

    access = contract.get("access") or {}
    _require(access.get("owner"), "Audit access requires owner")
    _require(access.get("default") == "deny", "Audit access must default deny")
    roles = _indexed(access.get("roles") or [], "audit role")
    producer = roles.get("audit-producer") or {}
    _require(
        set(producer.get("permissions") or []) == {"append"},
        "The append-only producer may only append",
    )
    for role_id, role in roles.items():
        _require(role.get("owner"), f"Audit role {role_id} requires owner")
        _require(role.get("permissions"), f"Audit role {role_id} requires permissions")
    separation = access.get("separation_of_duties") or {}
    _require(
        separation
        and all(value is True for value in separation.values()),
        "Audit access separation of duties must be enforced",
    )

    export = contract.get("export") or {}
    _require(export.get("owner"), "Export requires owner")
    _require(export.get("request_owner"), "Export requires request owner")
    _require(export.get("approval_required") is True, "Export requires approval")
    _require(int(export.get("minimum_approvers", 0)) >= 1, "Export requires approver")
    _require(export.get("encryption_required") is True, "Export requires encryption")
    _require(export.get("manifest_required") is True, "Export requires manifest")
    _require(
        REQUIRED_EXPORT_FIELDS <= set(export.get("manifest_fields") or []),
        "Export manifest fields are incomplete",
    )
    _require(export.get("access_logged") is True, "Export access must be logged")
    _require(
        export.get("raw_forbidden_data_rechecked") is True,
        "Export must repeat forbidden-data checks",
    )

    deletion = contract.get("deletion") or {}
    _require(deletion.get("owner"), "Deletion requires owner")
    _require(deletion.get("allow_early_delete") is False, "Audit early deletion is forbidden")
    _require(
        deletion.get("requires_retention_expiry") is True,
        "Deletion requires retention expiry",
    )
    _require(
        deletion.get("requires_no_active_legal_hold") is True,
        "Deletion requires no active legal hold",
    )
    _require(
        deletion.get("disposition_receipt_required") is True,
        "Deletion requires disposition receipt",
    )
    _require(deletion.get("tombstone_fields"), "Deletion requires tombstone fields")
    _require(
        deletion.get("direct_row_delete_allowed") is False,
        "Direct row deletion is forbidden",
    )

    legal_hold = contract.get("legal_hold") or {}
    _require(legal_hold.get("owner"), "Legal hold requires owner")
    _require(legal_hold.get("overrides_deletion") is True, "Legal hold must override deletion")
    for field in (
        "scoped_by",
        "reason_required",
        "approver_required",
        "release_requires_distinct_approver",
        "action_audited",
    ):
        value = legal_hold.get(field)
        _require(value is True or (field == "scoped_by" and value), f"Legal hold requires {field}")

    evidence_count = 0
    evidence_paths: set[str] = set()
    verifications = _indexed(
        contract.get("verification_catalog") or [], "verification"
    )
    pending: list[str] = []
    for verification_id, verification in verifications.items():
        _require(verification.get("owner"), f"Verification {verification_id} requires owner")
        status = verification.get("status")
        _require(
            status in {"implemented", "planned"},
            f"Verification {verification_id} has unsupported status",
        )
        checked, count = _check_evidence(
            verification.get("evidence") or [],
            root=root,
            owner=f"Verification {verification_id}",
        )
        evidence_paths.update(checked)
        evidence_count += count
        if status == "planned":
            pending.append(verification_id)

    risks = _indexed(contract.get("unresolved_risks") or [], "unresolved risk")
    risk_counts: Counter[str] = Counter()
    for risk_id, risk in risks.items():
        for field in ("severity", "owner", "statement", "decision_gate", "verification_plan"):
            _require(risk.get(field), f"Unresolved risk {risk_id} requires {field}")
        _require(
            risk["severity"] in SEVERITIES,
            f"Unresolved risk {risk_id} has unsupported severity",
        )
        risk_counts[risk["severity"]] += 1

    release = contract.get("release_policy") or {}
    blockers = set(release.get("block_on_unresolved_severity") or [])
    _require(
        blockers == {"critical", "high"},
        "Release policy must block critical and high risks",
    )
    required_verifications = set(release.get("required_verifications") or [])
    unknown = required_verifications - set(verifications)
    _require(not unknown, f"Release policy references unknown verification: {sorted(unknown)}")
    _require(
        required_verifications == set(verifications),
        "Release policy must require every verification",
    )
    _require(
        release.get("production_requires_independent_review") is True,
        "Production release requires independent audit review",
    )
    release_eligible = not pending and not any(risk_counts[level] for level in blockers)

    return {
        "schema_version": contract["schema_version"],
        "contract_id": metadata["id"],
        "contract_version": metadata["version"],
        "contract_status": "GREEN-local",
        "release_eligible": release_eligible,
        "append_only": integrity["append_only"],
        "event_fields": sorted(fields),
        "retention_classes": sorted(retention),
        "role_count": len(roles),
        "verification_count": len(verifications),
        "pending_verifications": sorted(pending),
        "unresolved_risks": {
            severity: risk_counts[severity] for severity in sorted(SEVERITIES)
        },
        "evidence_links_checked": evidence_count,
        "unique_evidence_paths": sorted(evidence_paths),
        "release_blockers": sorted(
            pending
            + [
                risk_id
                for risk_id, risk in risks.items()
                if risk["severity"] in blockers
            ]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Launchpad audit integrity and retention policy."
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    contract = yaml.safe_load(args.contract.read_text(encoding="utf-8"))
    report = validate(contract, root=ROOT)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
