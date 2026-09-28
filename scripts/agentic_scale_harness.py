#!/usr/bin/env python3
"""Build deterministic 501 run plans; live execution stays fail-closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts/agentic-workload-scale-v1.yaml"
DEFAULT_EVALUATION_SET = ROOT / "evaluation/agentic-scale-v1.yaml"
DEFAULT_EXECUTION_CHARTER = ROOT / "certification/workload/scale-agentic-blueprint.yaml"


class HarnessError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HarnessError(f"{path} must contain a YAML mapping")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evaluation_set(document: dict[str, Any], contract: dict[str, Any]) -> None:
    cases = document.get("cases")
    if not isinstance(cases, list):
        raise HarnessError("evaluation set cases must be a list")
    minimum = contract["quality_gate"]["evaluation_set"]["minimum_cases"]
    if len(cases) < minimum:
        raise HarnessError(f"evaluation set requires at least {minimum} cases")
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise HarnessError("evaluation case IDs must be unique")
    complexities = {name: 0 for name in ("simple", "medium", "complex")}
    domains: set[str] = set()
    for case in cases:
        complexity = case.get("complexity")
        if complexity not in complexities:
            raise HarnessError(f"case {case.get('id')} has unsupported complexity")
        complexities[complexity] += 1
        domains.add(str(case.get("domain")))
        if not case.get("prompt") or not case.get("required_evidence"):
            raise HarnessError(f"case {case.get('id')} lacks prompt or evidence")
    if len(set(complexities.values())) != 1:
        raise HarnessError("evaluation complexity groups must be equal")
    if len(domains) < 5:
        raise HarnessError("evaluation set must contain at least five domains")


def build_plan(
    profile_id: str,
    run_id: str,
    contract_path: Path = DEFAULT_CONTRACT,
    evaluation_path: Path = DEFAULT_EVALUATION_SET,
    execution_charter_path: Path = DEFAULT_EXECUTION_CHARTER,
) -> dict[str, Any]:
    contract = load_yaml(contract_path)
    evaluation = load_yaml(evaluation_path)
    execution_charter = load_yaml(execution_charter_path)
    validate_evaluation_set(evaluation, contract)
    profiles = {profile["id"]: profile for profile in contract["workload_profiles"]}
    if profile_id not in profiles:
        raise HarnessError(f"unknown profile: {profile_id}")
    profile = profiles[profile_id]
    cases = evaluation["cases"]
    journey_count = max(profile["minimum_completed_journeys"], len(cases))
    journeys = []
    for index in range(journey_count):
        case = cases[index % len(cases)]
        journeys.append(
            {
                "sequence": index + 1,
                "journey_id": f"{run_id}-{index + 1:04d}",
                "case_id": case["id"],
                "complexity": case["complexity"],
                "expected_workflow": case["expected_workflow"],
            }
        )
    return {
        "schema": "launchpad.agentic-scale-run-plan/v1",
        "run_id": run_id,
        "mode": "plan",
        "execution_enabled": execution_charter["spec"]["execution_enabled"],
        "profile": profile,
        "evaluation_set": {
            "id": evaluation["evaluation_set_id"],
            "revision": evaluation["revision"],
            "sha256": sha256(evaluation_path),
            "case_count": len(cases),
        },
        "journeys": journeys,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=("plan", "execute"), default="plan")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    execution_charter = load_yaml(DEFAULT_EXECUTION_CHARTER)
    if args.mode == "execute":
        if not execution_charter["spec"]["execution_enabled"]:
            parser.error("live execution is disabled by the 501 workload charter")
        parser.error("live execution adapter is not implemented")
    plan = build_plan(args.profile, args.run_id)
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
