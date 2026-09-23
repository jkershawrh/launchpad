#!/usr/bin/env python3
"""Validate an immutable Launchpad convergence candidate without live mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")
STAGES = ["green-local", "green-integration", "green-canary", "green-staging"]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _catalog_identity(path: Path) -> dict[str, str]:
    source = yaml.safe_load(path.read_text(encoding="utf-8"))
    metadata = source["catalog"]
    content = source["sources"]
    return {
        "catalog_id": metadata["catalog_item_id"],
        "version": str(metadata["version"]),
        "showroom_revision": content["showroom"]["revision"],
        "workload_revision": content["workload"]["revision"],
    }


def validate(candidate: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require(
        candidate.get("schema_version")
        == "launchpad.redhat.com/convergence-candidate/v1",
        "unsupported candidate schema",
    )
    stage = candidate.get("current_stage")
    _require(stage in STAGES, "unsupported candidate stage")
    revision = candidate.get("platform", {}).get("revision", "")
    _require(bool(SHA.fullmatch(revision)), "platform revision must be an immutable Git SHA")
    resolved = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    _require(resolved.returncode == 0, "platform revision does not resolve locally")

    declared = {item["catalog_id"]: item for item in candidate.get("catalog_releases", [])}
    required = {
        "intel-llm-cpu-serving",
        "intel-xeon6-agent-201",
        "multi-agent-quickstart",
    }
    _require(set(declared) == required, "candidate must bind exactly the three pilot catalogs")
    for catalog_id in sorted(required):
        actual = _catalog_identity(root / "catalog-onboarding" / f"{catalog_id}.yaml")
        _require(declared[catalog_id] == actual, f"catalog identity drift: {catalog_id}")

    evidence = candidate.get("evidence") or []
    _require(evidence, "candidate requires evidence")
    for item in evidence:
        path = root / item["path"]
        _require(path.is_file(), f"candidate evidence is missing: {item['path']}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _require(digest == item.get("sha256"), f"candidate evidence hash drift: {item['path']}")

    approval = candidate.get("approval") or {}
    _require(approval.get("required") is True, "candidate promotion must require approval")
    if stage != "green-local":
        _require(approval.get("approved_by"), "promoted candidate requires named approval")
        _require(approval.get("approved_at"), "promoted candidate requires approval time")

    next_index = STAGES.index(stage) + 1
    next_stage = STAGES[next_index] if next_index < len(STAGES) else None
    if next_stage:
        blocker_key = f"blockers_to_{next_stage.replace('-', '_')}"
        _require(candidate.get(blocker_key), f"candidate must name blockers to {next_stage}")

    return {
        "valid": True,
        "candidate_id": candidate["candidate_id"],
        "stage": stage,
        "platform_revision": revision,
        "catalog_count": len(declared),
        "evidence_count": len(evidence),
        "next_stage": next_stage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate = yaml.safe_load(args.candidate.read_text(encoding="utf-8"))
    result = validate(candidate)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
