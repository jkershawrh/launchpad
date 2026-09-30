#!/usr/bin/env python3
"""Promote one catalog scale gate from verified GREEN-live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _verify_checksum(evidence_path: Path) -> None:
    checksum_path = evidence_path.with_name(evidence_path.name + ".sha256")
    if not checksum_path.is_file():
        raise ValueError("evidence checksum manifest is missing")
    fields = checksum_path.read_text().strip().split()
    if len(fields) != 2 or fields[1] != evidence_path.name:
        raise ValueError("evidence checksum manifest is malformed")
    actual = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    if fields[0] != actual:
        raise ValueError("evidence checksum does not match")


def _next_target(certification: dict[str, Any]) -> int | None:
    current = int(certification.get("certified_seats", 0))
    targets = [int(v) for v in certification["promotion_sequence"] if int(v) > current]
    return targets[0] if targets else None


def validate_promotion(
    *, root: Path, catalog_id: str, evidence_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    _verify_checksum(evidence_path)
    evidence = json.loads(evidence_path.read_text())
    intake_path = root / "catalog-onboarding" / f"{catalog_id}.yaml"
    catalog_path = root / "catalog" / catalog_id / "catalog-item.yaml"
    contract_path = root / "certification" / "catalog" / f"{catalog_id}.yaml"
    intake = _load_yaml(intake_path)
    catalog = _load_yaml(catalog_path)
    contract = _load_yaml(contract_path)
    certification = intake["certification"]
    seats = int((evidence.get("plan") or {}).get("seats", 0))

    expected_contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    checks = {
        "schema": evidence.get("schema")
        == "launchpad.redhat.com/catalog-certification-evidence/v1",
        "catalog": evidence.get("catalog_item_id") == catalog_id,
        "result": evidence.get("result") == "GREEN-live",
        "cluster": (evidence.get("plan") or {}).get("cluster_ref") == "flightpath",
        "version": (evidence.get("contract") or {}).get("catalog_version")
        == intake["catalog"]["version"],
        "contract_path": (evidence.get("contract") or {}).get("path")
        == str(contract_path.relative_to(root)),
        "contract_hash": (evidence.get("contract") or {}).get("sha256")
        == expected_contract_hash,
        "rubric": (evidence.get("rubric") or {}).get("passed") is True
        and (evidence.get("rubric") or {}).get("score") == 100,
        "promotion": (evidence.get("promotion") or {}).get("eligible") is True,
        "cleanup": (evidence.get("cleanup") or {}).get("status") == "completed"
        and all(
            value == 0
            for value in (evidence.get("cleanup") or {})
            .get("resource_counts", {})
            .values()
        ),
        "next_scale": seats == _next_target(certification),
        "catalog_draft": catalog.get("status") == "draft",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("promotion evidence failed: " + ", ".join(failed))
    return intake, catalog, evidence, seats


def promote(*, root: Path, catalog_id: str, evidence_path: Path) -> dict[str, Any]:
    intake, catalog, _, seats = validate_promotion(
        root=root, catalog_id=catalog_id, evidence_path=evidence_path
    )
    certification = intake["certification"]
    stage = f"{seats}-seat-certified"
    scale_label = {1: "one-seat", 5: "five-seat"}.get(seats, f"{seats}-seat")
    certification["certified_seats"] = seats
    certification["stage"] = stage
    certification["activation_blockers"] = [
        blocker
        for blocker in certification.get("activation_blockers", [])
        if scale_label not in str(blocker)
    ]
    catalog["metadata"]["certification_stage"] = stage
    catalog["metadata"]["max_workshop_seats"] = seats
    catalog["metadata"]["activation_blockers"] = list(
        certification["activation_blockers"]
    )
    activated = seats == max(certification["promotion_sequence"]) and not certification[
        "activation_blockers"
    ]
    if activated:
        intake["catalog"]["status"] = "active"
        catalog["status"] = "active"

    intake_path = root / "catalog-onboarding" / f"{catalog_id}.yaml"
    catalog_path = root / "catalog" / catalog_id / "catalog-item.yaml"
    intake_path.write_text(yaml.safe_dump(intake, sort_keys=False))
    catalog_path.write_text(yaml.safe_dump(catalog, sort_keys=False))
    return {
        "catalog_item_id": catalog_id,
        "certified_seats": seats,
        "status": catalog["status"],
        "remaining_blockers": certification["activation_blockers"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_id")
    parser.add_argument("evidence")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    evidence_path = Path(args.evidence).resolve()
    if args.apply:
        result = promote(root=root, catalog_id=args.catalog_id, evidence_path=evidence_path)
    else:
        _, _, _, seats = validate_promotion(
            root=root, catalog_id=args.catalog_id, evidence_path=evidence_path
        )
        result = {"catalog_item_id": args.catalog_id, "certified_seats": seats, "valid": True}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
