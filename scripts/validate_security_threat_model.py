#!/usr/bin/env python3
"""Validate Launchpad's repository-owned security threat model fail closed."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "security-threat-model-v1.yaml"
REQUIRED_SURFACES = {
    "public-access",
    "control-plane",
    "execution-fleet",
    "model-plane",
    "artifact-supply",
    "data-flows",
    "support-access",
}
SEVERITIES = {"critical", "high", "moderate", "low"}
CONTROL_TYPES = {"preventive", "detective", "corrective"}
THREAT_CATEGORIES = {
    "spoofing",
    "tampering",
    "repudiation",
    "information-disclosure",
    "denial-of-service",
    "elevation-of-privilege",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _indexed(items: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    ids = [str(item.get("id", "")).strip() for item in items]
    _require(all(ids), f"Every {kind} requires an id")
    _require(len(ids) == len(set(ids)), f"{kind} ids must be unique")
    return {item["id"]: item for item in items}


def _evidence_paths(
    values: list[str], *, root: Path, owner: str
) -> tuple[list[str], int]:
    _require(values, f"{owner} requires evidence")
    checked: list[str] = []
    for value in values:
        path = str(value).strip()
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
        == "launchpad.redhat.com/security-threat-model/v1",
        "Unsupported threat-model schema",
    )
    _require(contract.get("kind") == "LaunchpadSecurityThreatModel", "Unsupported kind")
    metadata = contract.get("metadata") or {}
    for field in ("id", "version", "owner", "scope", "review_policy"):
        _require(metadata.get(field), f"Threat-model metadata requires {field}")

    boundaries = _indexed(contract.get("trust_boundaries") or [], "trust boundary")
    for boundary_id, boundary in boundaries.items():
        for field in (
            "source",
            "destination",
            "authentication",
            "authorization",
            "transport",
        ):
            _require(boundary.get(field), f"Trust boundary {boundary_id} requires {field}")

    assets = _indexed(contract.get("assets") or [], "asset")
    for asset_id, asset in assets.items():
        for field in ("owner", "classification", "security_properties"):
            _require(asset.get(field), f"Asset {asset_id} requires {field}")

    evidence_count = 0
    evidence_paths: set[str] = set()
    controls = _indexed(contract.get("controls") or [], "control")
    for control_id, control in controls.items():
        _require(control.get("owner"), f"Control {control_id} requires owner")
        _require(
            control.get("type") in CONTROL_TYPES,
            f"Control {control_id} requires a supported type",
        )
        _require(control.get("implementation"), f"Control {control_id} requires implementation")
        checked, count = _evidence_paths(
            control.get("evidence") or [], root=root, owner=f"Control {control_id}"
        )
        evidence_paths.update(checked)
        evidence_count += count

    verifications = _indexed(
        contract.get("verification_catalog") or [], "verification"
    )
    pending_verifications: list[str] = []
    for verification_id, verification in verifications.items():
        status = verification.get("status", "implemented")
        _require(
            status in {"implemented", "planned"},
            f"Verification {verification_id} has unsupported status",
        )
        checked, count = _evidence_paths(
            verification.get("evidence") or [],
            root=root,
            owner=f"Verification {verification_id}",
        )
        evidence_paths.update(checked)
        evidence_count += count
        if status == "planned":
            pending_verifications.append(verification_id)

    surfaces = _indexed(contract.get("surfaces") or [], "surface")
    _require(
        set(surfaces) == REQUIRED_SURFACES,
        "Threat model required surfaces are incomplete or contain unsupported entries",
    )
    threat_ids: set[str] = set()
    threat_count = 0
    for surface_id, surface in surfaces.items():
        _require(surface.get("owner"), f"Surface {surface_id} requires owner")
        surface_boundaries = surface.get("trust_boundaries") or []
        surface_assets = surface.get("assets") or []
        _require(surface_boundaries, f"Surface {surface_id} requires trust boundaries")
        _require(surface_assets, f"Surface {surface_id} requires assets")
        for boundary_id in surface_boundaries:
            _require(
                boundary_id in boundaries,
                f"Surface {surface_id} references unknown trust boundary {boundary_id}",
            )
        for asset_id in surface_assets:
            _require(
                asset_id in assets,
                f"Surface {surface_id} references unknown asset {asset_id}",
            )
        threats = surface.get("threats") or []
        _require(threats, f"Surface {surface_id} requires threats")
        for threat in threats:
            threat_id = str(threat.get("id", "")).strip()
            _require(threat_id, f"Surface {surface_id} has threat without id")
            _require(threat_id not in threat_ids, f"Threat id {threat_id} is duplicated")
            threat_ids.add(threat_id)
            threat_count += 1
            _require(threat.get("statement"), f"Threat {threat_id} requires statement")
            _require(
                threat.get("category") in THREAT_CATEGORIES,
                f"Threat {threat_id} requires a supported category",
            )
            _require(
                threat.get("severity") in SEVERITIES,
                f"Threat {threat_id} requires a supported severity",
            )
            mitigations = threat.get("mitigations") or []
            verification_ids = threat.get("verification") or []
            _require(mitigations, f"Threat {threat_id} requires mitigations")
            _require(verification_ids, f"Threat {threat_id} requires verification")
            for control_id in mitigations:
                _require(
                    control_id in controls,
                    f"Threat {threat_id} references unknown control {control_id}",
                )
            for verification_id in verification_ids:
                _require(
                    verification_id in verifications,
                    f"Threat {threat_id} references unknown verification {verification_id}",
                )

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

    release_policy = contract.get("release_policy") or {}
    blocker_severities = set(release_policy.get("block_on_unresolved_severity") or [])
    _require(
        blocker_severities == {"critical", "high"},
        "Release policy must block unresolved critical and high risks",
    )
    _require(
        release_policy.get("production_requires_independent_review") is True,
        "Production release must require independent security review",
    )
    release_eligible = not pending_verifications and not any(
        risk_counts[severity] for severity in blocker_severities
    )

    return {
        "schema_version": contract["schema_version"],
        "contract_id": metadata["id"],
        "contract_version": metadata["version"],
        "contract_status": "GREEN-local",
        "release_eligible": release_eligible,
        "surfaces": sorted(surfaces),
        "trust_boundary_count": len(boundaries),
        "asset_count": len(assets),
        "control_count": len(controls),
        "threat_count": threat_count,
        "verification_count": len(verifications),
        "pending_verifications": sorted(pending_verifications),
        "unresolved_risks": {
            severity: risk_counts[severity] for severity in sorted(SEVERITIES)
        },
        "evidence_links_checked": evidence_count,
        "unique_evidence_paths": sorted(evidence_paths),
        "release_blockers": sorted(
            [
                risk_id
                for risk_id, risk in risks.items()
                if risk["severity"] in blocker_severities
            ]
            + pending_verifications
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the repository-owned Launchpad security threat model."
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
