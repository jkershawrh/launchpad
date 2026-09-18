#!/usr/bin/env python3
"""Fail-closed validation for parallel delivery and convergence contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"tdd", "edd", "cdd", "bdd", "cbt"}
STAGES = ("red", "green-local", "green-integration", "green-live")
STAGE_RANK = {stage: index for index, stage in enumerate(STAGES)}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _assert_acyclic(streams: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stream_id: str) -> None:
        if stream_id in visiting:
            raise ValueError(f"Delivery stream dependency cycle includes {stream_id}")
        if stream_id in visited:
            return
        visiting.add(stream_id)
        for dependency in streams[stream_id].get("depends_on", []):
            visit(dependency)
        visiting.remove(stream_id)
        visited.add(stream_id)

    for stream_id in streams:
        visit(stream_id)


def validate(
    delivery: dict[str, Any], matrix: dict[str, Any], *, root: Path = ROOT
) -> dict[str, Any]:
    _require(
        delivery.get("schema_version") == "launchpad.redhat.com/v1alpha1",
        "Unsupported delivery schema",
    )
    _require(
        matrix.get("schema_version") == "launchpad.redhat.com/v1alpha1", "Unsupported matrix schema"
    )

    stream_items = delivery.get("streams") or []
    stream_ids = [item.get("id") for item in stream_items]
    _require(all(stream_ids), "Every delivery stream requires an id")
    _require(len(stream_ids) == len(set(stream_ids)), "Delivery stream ids must be unique")
    streams = {item["id"]: item for item in stream_items}

    convergence = [item for item in stream_items if item.get("kind") == "convergence"]
    _require(len(convergence) == 1, "Exactly one convergence stream is required")
    convergence_id = convergence[0]["id"]
    _require(
        "product-gtm-customer-success" in streams,
        "Product production requires a GTM and customer-success stream",
    )

    max_active = int(
        delivery.get("delivery_policy", {}).get("max_parallel_implementation_streams", 0)
    )
    active = [item for item in stream_items if item.get("initially_active")]
    _require(max_active > 0, "A positive work-in-progress limit is required")
    _require(
        len(active) <= max_active, "Initially active streams exceed the work-in-progress limit"
    )

    path_owners: dict[str, str] = {}
    for item in stream_items:
        stream_id = item["id"]
        policy = item.get("live_mutation_policy")
        if stream_id == convergence_id:
            _require(policy == "approval-gated", "The convergence stream must be approval-gated")
        else:
            _require(
                policy == "forbidden",
                "Only the convergence stream may use an approval-gated live mutation policy",
            )
        for dependency in item.get("depends_on", []):
            _require(dependency in streams, f"{stream_id} depends on unknown stream {dependency}")
            _require(dependency != stream_id, f"{stream_id} cannot depend on itself")
        _require(item.get("entry_gate"), f"{stream_id} requires an entry gate")
        _require(item.get("exit_gate"), f"{stream_id} requires an exit gate")
        for path in item.get("owned_paths", []):
            previous = path_owners.get(path)
            _require(
                previous is None,
                f"{path} is owned by multiple streams: {previous}, {stream_id}",
            )
            path_owners[path] = stream_id
    _assert_acyclic(streams)

    contract_items = delivery.get("contracts") or []
    contract_ids = [item.get("id") for item in contract_items]
    _require(all(contract_ids), "Every shared contract requires an id")
    _require(len(contract_ids) == len(set(contract_ids)), "Shared contract ids must be unique")
    contracts = {item["id"]: item for item in contract_items}
    production_contracts = {
        "production-readiness-v1",
        "sre-operating-model-v1",
        "data-ai-governance-v1",
        "gtm-value-attribution-v1",
    }
    _require(
        production_contracts <= set(contracts),
        "Production delivery contracts are incomplete",
    )
    _require(
        set(delivery.get("delivery_policy", {}).get("production_release_requires", []))
        == production_contracts,
        "Production release policy must require every production contract",
    )
    for item in contract_items:
        _require(item.get("owner") in streams, f"Contract {item['id']} has an unknown owner")
        for consumer in item.get("consumers", []):
            _require(consumer in streams, f"Contract {item['id']} has unknown consumer {consumer}")
        path = item.get("path")
        _require(
            path and (root / path).exists(), f"Contract {item['id']} path does not exist: {path}"
        )
        _require(item.get("version"), f"Contract {item['id']} requires a version")
        if item["id"] in production_contracts:
            document = yaml.safe_load((root / path).read_text(encoding="utf-8"))
            _require(
                document.get("schema_version") == "launchpad.redhat.com/v1alpha1",
                f"Production contract {item['id']} has an unsupported schema",
            )
            _require(document.get("kind"), f"Production contract {item['id']} requires a kind")
            _require(
                document.get("metadata", {}).get("version") == item["version"],
                f"Production contract {item['id']} version does not match registry",
            )

    pivot = delivery.get("pivot_policy") or {}
    _require(
        set(pivot.get("classes", {}))
        == {"stream-local", "contract", "product-capacity", "emergency-live"},
        "Pivot policy must define all four pivot classes",
    )
    _require(pivot.get("required_record_fields"), "Pivot records require stable fields")

    scenarios = matrix.get("scenarios") or []
    scenario_ids = [item.get("id") for item in scenarios]
    _require(all(scenario_ids), "Every convergence scenario requires an id")
    _require(len(scenario_ids) == len(set(scenario_ids)), "Convergence scenario ids must be unique")
    required_dimensions = {
        "usability",
        "security",
        "capacity",
        "performance",
        "operability",
        "data_governance",
        "fault_recovery",
        "cleanup",
    }
    _require(
        required_dimensions <= set(matrix.get("required_proof_dimensions", [])),
        "Convergence matrix omits production proof dimensions",
    )
    required_release_dimensions = {
        "product_value",
        "commercial_readiness",
        "service_ownership",
        "legal_compliance",
    }
    _require(
        required_release_dimensions <= set(matrix.get("release_required_dimensions", [])),
        "Convergence matrix omits product release dimensions",
    )
    for scenario in scenarios:
        scenario_id = scenario["id"]
        _require(scenario.get("owner") in streams, f"Scenario {scenario_id} has unknown owner")
        for participant in scenario.get("participating_streams", []):
            _require(
                participant in streams, f"Scenario {scenario_id} has unknown stream {participant}"
            )
        for contract_id in scenario.get("contracts", []):
            _require(
                contract_id in contracts,
                f"Scenario {scenario_id} has unknown contract {contract_id}",
            )
        methods = scenario.get("methods") or {}
        _require(set(methods) == METHODS, f"Scenario {scenario_id} must declare all proof methods")
        state = scenario.get("state")
        _require(state in STAGE_RANK, f"Scenario {scenario_id} has invalid state {state}")
        _require(
            all(value in STAGE_RANK for value in methods.values()),
            f"Scenario {scenario_id} has an invalid method state",
        )
        dimensions = set(scenario.get("proof_dimensions", []))
        _require(
            required_dimensions <= dimensions,
            f"Scenario {scenario_id} lacks required proof dimensions",
        )
        if state != "red":
            evidence = scenario.get("evidence") or []
            _require(evidence, f"Scenario {scenario_id} cannot be green without evidence")
            _require(
                all(STAGE_RANK[value] >= STAGE_RANK[state] for value in methods.values()),
                f"Scenario {scenario_id} method evidence is below its declared state",
            )
            for evidence_path in evidence:
                _require(
                    (root / evidence_path).exists(),
                    f"Scenario {scenario_id} evidence does not exist: {evidence_path}",
                )

    end_to_end = next(
        (item for item in scenarios if item.get("id") == "end-to-end-staged-release"), None
    )
    _require(end_to_end is not None, "End-to-end staged release scenario is required")
    _require(
        required_release_dimensions <= set(end_to_end.get("release_dimensions", [])),
        "End-to-end staged release lacks product release dimensions",
    )

    promotion = matrix.get("promotion_gates") or []
    expected = [
        "green-local",
        "green-integration",
        "green-canary",
        "green-staging",
        "green-production-limited",
        "green-production",
    ]
    _require(
        [item.get("stage") for item in promotion] == expected,
        "Promotion gates are missing or out of order",
    )
    _require(
        all(item.get("required_evidence") for item in promotion),
        "Every promotion gate requires evidence",
    )

    return {
        "valid": True,
        "stream_count": len(streams),
        "initial_active_count": len(active),
        "convergence_stream": convergence_id,
        "contract_count": len(contracts),
        "scenario_count": len(scenarios),
        "promotion_gate_count": len(promotion),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--streams", type=Path, default=ROOT / "contracts" / "delivery-streams-v1.yaml"
    )
    parser.add_argument(
        "--matrix", type=Path, default=ROOT / "certification" / "convergence-matrix-v1.yaml"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    delivery = yaml.safe_load(args.streams.read_text(encoding="utf-8"))
    matrix = yaml.safe_load(args.matrix.read_text(encoding="utf-8"))
    report = validate(delivery, matrix)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
