import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agentic_scale_harness.py"
EVALUATION = ROOT / "evaluation/agentic-scale-v1.yaml"
EVALUATION_CONTRACT = ROOT / "contracts/agentic-scale-evaluation-set-v1.yaml"

spec = spec_from_file_location("agentic_scale_harness", SCRIPT)
assert spec and spec.loader
harness = module_from_spec(spec)
spec.loader.exec_module(harness)


def test_evaluation_set_is_balanced_and_contract_complete():
    evaluation = yaml.safe_load(EVALUATION.read_text())
    contract = yaml.safe_load(EVALUATION_CONTRACT.read_text())
    required = set(contract["case_contract"]["required_fields"])

    assert len(evaluation["cases"]) == 30
    assert len(evaluation["domains"]) == 5
    assert {case["complexity"] for case in evaluation["cases"]} == {
        "simple",
        "medium",
        "complex",
    }
    assert all(sum(case["complexity"] == level for case in evaluation["cases"]) == 10 for level in ("simple", "medium", "complex"))
    assert all(required <= set(case) for case in evaluation["cases"])
    harness.validate_evaluation_set(
        evaluation,
        yaml.safe_load((ROOT / "contracts/agentic-workload-scale-v1.yaml").read_text()),
    )


def test_planner_builds_deterministic_hashed_profiles():
    first = harness.build_plan("sustained", "run-501")
    second = harness.build_plan("sustained", "run-501")

    assert first == second
    assert first["mode"] == "plan"
    assert first["execution_enabled"] is False
    assert first["profile"]["agent_replicas"] == 2
    assert first["profile"]["concurrent_journeys"] == 5
    assert len(first["journeys"]) == 50
    assert len(first["evaluation_set"]["sha256"]) == 64
    assert len({journey["journey_id"] for journey in first["journeys"]}) == 50


def test_one_seat_plan_still_runs_the_complete_quality_set():
    plan = harness.build_plan("baseline", "baseline")

    assert len(plan["journeys"]) == 30
    assert {journey["case_id"] for journey in plan["journeys"]} == {
        case["id"] for case in yaml.safe_load(EVALUATION.read_text())["cases"]
    }


def test_live_execution_fails_closed_while_charter_is_disabled():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "baseline",
            "--run-id",
            "blocked",
            "--mode",
            "execute",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "live execution is disabled by the 501 workload charter" in result.stderr
