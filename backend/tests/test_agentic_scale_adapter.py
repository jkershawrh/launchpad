from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/agentic_scale_adapter.py"
spec = spec_from_file_location("agentic_scale_adapter", SCRIPT)
assert spec and spec.loader
adapter = module_from_spec(spec)
spec.loader.exec_module(adapter)


def _response() -> dict:
    return {
        "run_id": "server-run",
        "journey_id": "run-0001",
        "case_id": "S01",
        "selected_workflow": "lightweight",
        "total_latency_ms": 1250,
        "agents_involved": ["executor"],
        "steps": [{"status": "completed"}],
        "proof": {
            "evidence": {
                "status": "complete",
                "items": [{"evidence_type": "service_health"}],
            },
            "policy": {
                "evaluation_status": "evaluated",
                "result": "allow_recommendation",
                "disposition": "supported",
            },
            "inference": {
                "source_state": "live",
                "telemetry_status": "complete",
                "latency_ms": 900,
                "queue_ms": 20,
                "input_tokens": 100,
                "output_tokens": 40,
            },
            "human_review": {
                "required": True,
                "automatic_action_executed": False,
            },
        },
    }


def test_complete_live_proof_adapts_to_scoreable_result():
    result = adapter.adapt_workflow_response(_response(), "S01", "run-0001")

    assert result["status"] == "completed"
    assert result["evidence_types"] == ["service_health"]
    assert result["policy_result"] == "allow_recommendation"
    assert result["inference_latency_ms"] == 900
    assert result["automatic_action_executed"] is False


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("proof", "evidence", "status"), "incomplete", "evidence is not complete"),
        (("proof", "policy", "evaluation_status"), "not_evaluated", "not evaluated"),
        (("proof", "inference", "source_state"), "rehearsal", "not live"),
        (("proof", "inference", "telemetry_status"), "partial", "not complete"),
    ],
)
def test_incomplete_or_non_live_proof_is_rejected(path, value, message):
    response = _response()
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(adapter.AdapterError, match=message):
        adapter.adapt_workflow_response(response, "S01", "run-0001")


def test_mismatched_correlation_is_rejected():
    with pytest.raises(adapter.AdapterError, match="correlation"):
        adapter.adapt_workflow_response(_response(), "S01", "another-journey")
