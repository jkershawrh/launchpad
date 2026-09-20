#!/usr/bin/env python3
"""Fail-closed validation for the isolated catalog-intake worker policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "catalog-intake-worker-safety-v1.yaml"
REQUIRED_CREDENTIAL_PATTERNS = {
    "*password*", "*token*", "*secret*", "*api_key*", "*private_key*", "*kubeconfig*"
}
REQUIRED_BLOCKED_DESTINATIONS = {
    "kubernetes-api", "cloud-instance-metadata", "internal-service-network",
    "cluster-ingress-domain", "database", "artifact-registry-publisher",
}
REQUIRED_FORBIDDEN_CREDENTIALS = {
    "cluster-admin", "kubeconfig", "catalog-database", "catalog-publisher",
    "argocd", "registry-publisher", "keycloak-admin", "tunnel", "model-api",
}
REQUIRED_CLEANUP_EVENTS = {
    "success", "validation-failure", "timeout", "cancellation", "worker-failure"
}
REQUIRED_EVIDENCE_FIELDS = {
    "intake_request_id", "idempotency_key", "repository", "commit_sha",
    "policy_version", "worker_image_digest", "started_at", "finished_at",
    "outcome", "scan_summary", "output_hash", "cleanup_receipt_id",
}
REQUIRED_RECEIPT_FIELDS = {
    "receipt_id", "attempt_id", "completed_at", "workspace_removed",
    "process_count", "bytes_removed", "result",
}
REQUIRED_IDEMPOTENCY_FIELDS = {
    "repository", "commit_sha", "policy_version", "normalized_payload_hash"
}
REQUIRED_FORBIDDEN_MUTATIONS = {
    "live-catalog", "catalog-database", "openshift-cluster", "argocd",
    "artifact-registry", "workshop", "session",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _index(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    ids = [str(item.get("id", "")).strip() for item in items]
    _require(all(ids), f"Every {kind} requires an id")
    _require(len(ids) == len(set(ids)), f"{kind} ids must be unique")
    return {item["id"]: item for item in items}


def _check_evidence(evidence: list[str], *, root: Path, owner: str) -> list[str]:
    _require(evidence, f"{owner} requires evidence")
    checked: list[str] = []
    for item in evidence:
        path = str(item).strip()
        _require(path, f"{owner} contains an empty evidence path")
        _require((root / path).is_file(), f"{owner} evidence path does not exist: {path}")
        checked.append(path)
    return checked


def validate(contract: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require(
        contract.get("schema_version") == "launchpad.redhat.com/catalog-intake-worker-safety/v1",
        "Unsupported worker safety schema",
    )
    _require(
        contract.get("kind") == "LaunchpadCatalogIntakeWorkerSafetyPolicy",
        "Unsupported worker safety kind",
    )
    metadata = contract.get("metadata") or {}
    for field in ("id", "version", "owner", "service_owner", "review_policy"):
        _require(metadata.get(field), f"Worker safety metadata requires {field}")

    source = contract.get("source_policy") or {}
    _require(source.get("default") == "deny", "Source policy must default deny")
    _require(source.get("allowed_schemes") == ["https"], "Only HTTPS source fetch is allowed")
    _require(source.get("allowed_hosts"), "Source host allowlist is required")
    immutable = source.get("immutable_revision") or {}
    _require(immutable.get("required") is True, "Source revision must be immutable")
    _require("40-character" in str(immutable.get("format", "")), "Immutable source requires a full commit SHA")
    _require(immutable.get("branch_tag_or_symbolic_ref_allowed") is False, "Mutable refs are forbidden")
    authorization = source.get("repository_authorization") or {}
    _require(authorization.get("unlisted_repository_policy") == "require-recorded-approval", "Unlisted repositories require approval")
    _require(authorization.get("approval_must_precede_fetch") is True, "Repository approval must precede fetch")
    approval_fields = set(authorization.get("approval_record_fields") or [])
    _require({"repository", "commit_sha", "requested_by", "approved_by", "approved_at", "expires_at", "purpose"} <= approval_fields, "Repository approval record is incomplete")
    _require(source.get("redirects", {}).get("allowed") is False, "Source redirects are forbidden")
    _require(source.get("submodules", {}).get("allowed") is False, "Submodules are forbidden by default")

    payload = contract.get("payload_policy") or {}
    _require(int(payload.get("maximum_bytes", 0)) > 0, "Payload size limit is required")
    _require(payload.get("allow_only_schema_fields") is True, "Payload must allow only schema fields")
    _require(payload.get("user_credentials_allowed") is False, "User credentials are forbidden in payloads")
    _require(REQUIRED_CREDENTIAL_PATTERNS <= set(payload.get("forbidden_key_patterns") or []), "Payload credential patterns are incomplete")
    _require(payload.get("forbidden_value_classes"), "Payload forbidden value classes are required")

    runtime = contract.get("runtime_policy") or {}
    security = runtime.get("security_context") or {}
    _require(security.get("run_as_non_root") is True, "Worker must run as non-root")
    _require(security.get("privileged") is False, "Privileged worker is forbidden")
    _require(security.get("allow_privilege_escalation") is False, "Privilege escalation is forbidden")
    _require(security.get("read_only_root_filesystem") is True, "Root filesystem must be read-only")
    _require(security.get("seccomp_profile") == "RuntimeDefault", "RuntimeDefault seccomp is required")
    _require("ALL" in (security.get("drop_capabilities") or []), "All Linux capabilities must be dropped")
    _require(security.get("automount_service_account_token") is False, "Service-account token automount is forbidden")
    for field in ("host_network", "host_pid", "host_ipc", "host_path_allowed"):
        _require(security.get(field) is False, f"Runtime security requires {field}=false")
    workspace = runtime.get("workspace") or {}
    _require(workspace.get("ephemeral") is True, "Worker workspace must be ephemeral")
    _require(workspace.get("persistent_volume_allowed") is False, "Persistent worker storage is forbidden")
    _require(workspace.get("unique_per_attempt") is True, "Workspace must be unique per attempt")
    _require(workspace.get("cleanup_always") is True, "Workspace cleanup must always run")
    _require(int(workspace.get("maximum_size_mib", 0)) > 0, "Workspace size limit is required")
    limits = runtime.get("limits") or {}
    for field in ("cpu", "memory_mib", "ephemeral_storage_mib", "wall_clock_seconds", "maximum_processes", "maximum_output_bytes"):
        _require(limits.get(field), f"Runtime limit requires {field}")

    egress = contract.get("egress_policy") or {}
    _require(egress.get("default") == "deny", "Egress must default deny")
    _require(egress.get("allowed_destinations"), "Egress destination allowlist is required")
    for destination in egress["allowed_destinations"]:
        _require(destination.get("host") in source["allowed_hosts"] or destination.get("host") == "api.github.com", "Egress destination is not source-approved")
        _require(set(destination.get("ports") or []) == {443}, "Egress is restricted to HTTPS")
    _require(REQUIRED_BLOCKED_DESTINATIONS <= set(egress.get("blocked_destination_classes") or []), "Egress blocked destinations are incomplete")
    _require(egress.get("redirects_revalidated_against_allowlist") is True, "Redirect targets must be revalidated")
    _require(egress.get("ip_literals_allowed") is False, "IP literal egress is forbidden")

    credentials = contract.get("credential_policy") or {}
    _require(credentials.get("live_credentials_allowed") is False, "Live credentials are forbidden")
    _require(credentials.get("worker_service_account_allowed") is False, "Worker service-account credentials are forbidden")
    _require(credentials.get("source_fetch_mode") == "anonymous-public-read", "Source fetch must be anonymous public read")
    _require(REQUIRED_FORBIDDEN_CREDENTIALS <= set(credentials.get("forbidden_credentials") or []), "Forbidden live credentials are incomplete")
    _require(credentials.get("environment_secret_import_allowed") is False, "Environment secret import is forbidden")
    _require(credentials.get("secret_volume_mount_allowed") is False, "Secret mounts are forbidden")

    scanning = contract.get("scanning_policy") or {}
    _require(scanning.get("owner"), "Scanning requires owner")
    _require(set(scanning.get("secret_scan_stages") or []) == {"payload-before-dispatch", "source-after-fetch", "output-before-evidence"}, "Secret scan stages are incomplete")
    _require(scanning.get("scanner_configuration_versioned") is True, "Scanner configuration must be versioned")
    _require(scanning.get("scan_entire_workspace") is True, "Scanner must inspect the full workspace")
    _require(str(scanning.get("on_detection", "")).startswith("reject"), "Secret detection must fail closed")
    _require(scanning.get("on_scanner_failure") == "reject", "Scanner failure must fail closed")

    logging = contract.get("logging_and_evidence") or {}
    _require(logging.get("owner"), "Logging and evidence require owner")
    _require(logging.get("sanitized_only") is True, "Logs and evidence must be sanitized")
    for field in ("raw_source_content_allowed", "environment_dump_allowed", "credential_values_allowed"):
        _require(logging.get(field) is False, f"Logging requires {field}=false")
    _require(logging.get("bounded_output_required") is True, "Output must be bounded")
    _require(REQUIRED_EVIDENCE_FIELDS <= set(logging.get("required_fields") or []), "Required evidence fields are incomplete")

    cleanup = contract.get("cleanup_policy") or {}
    _require(cleanup.get("owner"), "Cleanup requires owner")
    _require(REQUIRED_CLEANUP_EVENTS <= set(cleanup.get("runs_on") or []), "Cleanup trigger coverage is incomplete")
    _require(cleanup.get("workspace_deleted") is True, "Cleanup must delete workspace")
    _require(cleanup.get("child_processes_terminated") is True, "Cleanup must terminate processes")
    _require(cleanup.get("receipt_required") is True, "A cleanup receipt is required")
    _require(REQUIRED_RECEIPT_FIELDS <= set(cleanup.get("receipt_fields") or []), "Cleanup receipt fields are incomplete")
    _require("credential-values" in (cleanup.get("receipt_forbids") or []), "Cleanup receipt must forbid credentials")

    retry = contract.get("retry_policy") or {}
    _require(1 <= int(retry.get("max_attempts", 0)) <= 3, "Retry attempts must be bounded from one to three")
    _require(retry.get("retryable_outcomes"), "Retryable outcomes are required")
    _require("secret-detection" in (retry.get("non_retryable_outcomes") or []), "Secret findings must not retry")
    _require(REQUIRED_IDEMPOTENCY_FIELDS <= set(retry.get("idempotency_key_fields") or []), "Idempotency fields are incomplete")
    _require(retry.get("same_key_reuses_terminal_result") is True, "Terminal result reuse is required")
    _require(retry.get("live_side_effects_allowed") is False, "Retry side effects are forbidden")
    _require(retry.get("cleanup_receipt_required_before_retry") is True, "Cleanup receipt is required before retry")

    authority = contract.get("authority_boundary") or {}
    _require(authority.get("mode") == "analysis-only", "Worker authority must be analysis-only")
    _require(REQUIRED_FORBIDDEN_MUTATIONS <= set(authority.get("forbidden_mutations") or []), "Forbidden live mutations are incomplete")
    _require(authority.get("promotion_requires_separate_authenticated-approved-stage") is True, "Promotion must be a separate approved stage")

    verifications = _index(contract.get("verification_catalog") or [], "verification")
    evidence: list[str] = []
    for verification_id, verification in verifications.items():
        _require(verification.get("status") in {"implemented", "planned"}, f"Verification {verification_id} has invalid status")
        _require(verification.get("owner"), f"Verification {verification_id} requires owner")
        evidence.extend(_check_evidence(verification.get("evidence") or [], root=root, owner=verification_id))

    risks = _index(contract.get("unresolved_risks") or [], "risk")
    for risk_id, risk in risks.items():
        _require(risk.get("severity") in {"critical", "high", "moderate", "low"}, f"Risk {risk_id} has invalid severity")
        _require(risk.get("owner") and risk.get("statement"), f"Risk {risk_id} requires owner and statement")
        _require(risk.get("required_verification") in verifications, f"Risk {risk_id} references unknown verification")

    release = contract.get("release_policy") or {}
    _require(release.get("release_eligible") is False, "Non-live worker must remain release ineligible")
    _require(release.get("fail_closed") is True, "Release policy must fail closed")
    required = set(release.get("required_verifications") or [])
    _require(required, "Release policy requires verifications")
    _require(required <= set(verifications), "Release policy references unknown verification")
    pending = sorted(item_id for item_id in required if verifications[item_id]["status"] != "implemented")
    _require(pending, "Live isolation proof must remain pending")
    _require(all(risk.get("blocks_release") is True for risk in risks.values()), "Every unresolved worker risk must block release")

    return {
        "contract_id": metadata["id"],
        "contract_version": metadata["version"],
        "contract_status": "GREEN-local",
        "release_eligible": False,
        "source_default": source["default"],
        "egress_default": egress["default"],
        "live_credentials_allowed": credentials["live_credentials_allowed"],
        "verification_count": len(verifications),
        "pending_verifications": pending,
        "unresolved_risks": sorted(risks),
        "evidence_paths": sorted(set(evidence)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(yaml.safe_load(args.contract.read_text(encoding="utf-8")), root=ROOT)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
